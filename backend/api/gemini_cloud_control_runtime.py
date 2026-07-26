"""Strict cloud-only policy and real per-key verification.

This runtime is loaded last. It enforces these invariants:
- Mechanical/free engines are never selected automatically.
- A Gemini key is usable only after both a real text request and a real audio request succeed.
- Temporary 429 windows never disconnect a previously verified key.
- Every key keeps an independent verification and transient-limit record.
"""
from __future__ import annotations

import asyncio
import base64
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException

from backend.api import (
    dialogue_safe_routes,
    dialogue_ultra_routes,
    gemini_retry_window_runtime,
    gemini_rotation_runtime,
    gemini_routes,
    gemini_stability_runtime,
    interview_pro_routes,
    producer_routes,
    routes,
    studio_pro_routes,
)
from backend.core import gemini_key_pool as pool
from backend.core.config import OUTPUTS_DIR
from backend.core.tts_registry import tts_registry
from backend.plugins.builtin.audio_effects import _ffmpeg_executable, process_audio

_ORIGINAL_STATUSES = pool.key_statuses
_ORIGINAL_SET_SELECTED = pool.set_selected_key
HARD_FAILURES = {"invalid", "forbidden"}
MECHANICAL_ENGINES = {"edge", "edge_fallback", "piper", "coqui", "kokoro", "melotts", "styletts2", "fallback"}


def _record_for(key: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    entries = pool.load_entries()
    keys = [item["key"] for item in entries]
    state = pool._state(keys)  # type: ignore[attr-defined]
    key_id = pool.fingerprint(key)
    record = dict((state.get("records") or {}).get(key_id) or {})
    return state, record, key_id


def _save_record(key: str, values: dict[str, Any], *, clear_active: bool = False) -> None:
    state, record, key_id = _record_for(key)
    record.update(values)
    state.setdefault("records", {})[key_id] = record
    if clear_active:
        if state.get("active_fp") == key_id:
            state["active_fp"] = ""
        if state.get("selected_fp") == key_id:
            state["selected_fp"] = ""
    state["updated_at"] = int(time.time())
    pool._write(pool.STATE_FILE, state)  # type: ignore[attr-defined]


def _is_verified_record(record: dict[str, Any]) -> bool:
    return bool(
        record.get("verified") is True
        and str(record.get("status") or "") == "working"
        and str(record.get("text_status") or "") == "working"
        and str(record.get("tts_status") or "") == "working"
    )


def strict_key_statuses() -> list[dict[str, Any]]:
    statuses = _ORIGINAL_STATUSES()
    entries = pool.load_entries()
    keys = [item["key"] for item in entries]
    state = pool._state(keys) if keys else {"records": {}, "selected_fp": "", "active_fp": ""}  # type: ignore[attr-defined]
    records = state.get("records") or {}
    active_id = str(state.get("active_fp") or "")
    selected_id = str(state.get("selected_fp") or "")
    for item in statuses:
        record = dict(records.get(item["id"]) or {})
        verified = _is_verified_record(record)
        enabled = bool(item.get("enabled", True))
        item.update(
            verified=verified,
            working=verified,
            usable=enabled and verified,
            active=enabled and verified and item["id"] == active_id,
            selected=enabled and item["id"] == selected_id,
            text_working=str(record.get("text_status") or "") == "working",
            tts_working=str(record.get("tts_status") or "") == "working",
            text_model=record.get("text_model", ""),
            tts_model=record.get("tts_model", ""),
            verified_at=record.get("verified_at"),
            temporary=bool(record.get("temporary", False)),
            retry_after_seconds=int(record.get("retry_after_seconds") or 0),
            last_transient_detail=record.get("last_transient_detail", ""),
        )
    return statuses


def strict_ordered_keys() -> list[str]:
    entries = [item for item in pool.load_entries() if item.get("enabled", True)]
    if not entries:
        return []
    all_keys = [item["key"] for item in pool.load_entries()]
    state = pool._state(all_keys)  # type: ignore[attr-defined]
    records = state.get("records") or {}
    selected = str(state.get("selected_fp") or state.get("active_fp") or "")
    now = time.time()
    ready: list[tuple[bool, str]] = []
    cooling: list[tuple[bool, str]] = []
    for item in entries:
        key = item["key"]
        key_id = pool.fingerprint(key)
        record = dict(records.get(key_id) or {})
        if not _is_verified_record(record):
            continue
        target = cooling if float(record.get("cooldown_until", 0) or 0) > now else ready
        target.append((key_id == selected, key))
    ordered = [key for preferred, key in sorted(ready, key=lambda row: not row[0])]
    ordered += [key for preferred, key in sorted(cooling, key=lambda row: not row[0])]
    return list(dict.fromkeys(ordered))


def guarded_set_active_key(key_id: str) -> dict[str, Any]:
    item = next((row for row in strict_key_statuses() if row["id"] == key_id), None)
    if not item:
        raise KeyError("key_not_found")
    if not item.get("enabled"):
        raise ValueError("key_disabled")
    if not item.get("verified"):
        raise ValueError("key_not_verified")
    result = _ORIGINAL_SET_SELECTED(key_id)
    pool.apply_environment(strict_ordered_keys(), str(pool.load_config().get("model_id") or ""))
    return result


def _detail(response: httpx.Response) -> str:
    return gemini_routes._error_detail(response)


async def _post_with_window_retry(
    client: httpx.AsyncClient,
    url: str,
    key: str,
    payload: dict[str, Any],
    attempts: int = 3,
) -> tuple[httpx.Response, int]:
    total_wait = 0
    for attempt in range(1, attempts + 1):
        response = await client.post(
            url,
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json=payload,
        )
        if response.status_code != 429:
            return response, total_wait
        wait = int(max(2, min(120, round(gemini_retry_window_runtime.retry_seconds(response=response, detail=_detail(response), attempt=attempt) + 1))))
        total_wait += wait
        if attempt < attempts:
            await asyncio.sleep(wait)
    return response, total_wait


def _temporary_result(key: str, number: int, detail: str, retry_after: int, text_ok: bool = False) -> dict[str, Any]:
    state, previous, _ = _record_for(key)
    was_verified = _is_verified_record(previous)
    message = f"حد طلبات مؤقت، وليس انتهاء الحصة. أعد المحاولة بعد نحو {retry_after} ثانية."
    values: dict[str, Any] = {
        "temporary": True,
        "retry_after_seconds": retry_after,
        "last_transient_detail": detail[:900],
        "last_transient_at": int(time.time()),
        "cooldown_until": int(time.time()) + retry_after,
        "detail": message,
        "checked_at": int(time.time()),
    }
    if was_verified:
        values.update(status="working", verified=True)
    else:
        values.update(status="rate_limited", verified=False)
        if text_ok:
            values.update(text_status="working")
    _save_record(key, values)
    return {
        "number": number,
        "ok": False,
        "verified": was_verified,
        "status": "rate_limited",
        "temporary": True,
        "retry_after_seconds": retry_after,
        "detail": message,
        "text_ok": text_ok,
        "tts_ok": False,
        "capabilities": [],
    }


async def strict_test_one(key: str, number: int = 1) -> dict[str, Any]:
    """Approve a key only after real text and real TTS responses both succeed."""
    outcome: dict[str, Any] = {
        "number": number,
        "ok": False,
        "verified": False,
        "status": "failed",
        "detail": "",
        "text_ok": False,
        "tts_ok": False,
        "text_model": "",
        "tts_model": "",
        "capabilities": [],
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(210.0, connect=30.0)) as client:
        text_errors: list[str] = []
        for model in (await gemini_routes._available_text_models(client, key))[:8]:
            payload = {
                "contents": [{"parts": [{"text": "أجب بهذه الكلمة فقط دون زيادة: جاهز"}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": 10},
            }
            try:
                response, waited = await _post_with_window_retry(
                    client,
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    key,
                    payload,
                )
            except Exception as exc:
                text_errors.append(f"{type(exc).__name__}: {exc}")
                continue
            if response.status_code == 429:
                retry_after = int(max(2, min(120, round(gemini_retry_window_runtime.retry_seconds(response=response, detail=_detail(response)) + 1))))
                return _temporary_result(key, number, _detail(response), retry_after)
            if response.status_code == 401:
                detail = _detail(response) or "المفتاح غير صحيح أو أُلغي."
                _save_record(key, {"status": "invalid", "verified": False, "detail": detail, "checked_at": int(time.time())}, clear_active=True)
                return {**outcome, "status": "invalid", "detail": detail}
            if response.status_code == 403:
                detail = _detail(response) or "الصلاحية أو المشروع أو الفوترة ترفض الطلب."
                _save_record(key, {"status": "forbidden", "verified": False, "detail": detail, "checked_at": int(time.time())}, clear_active=True)
                return {**outcome, "status": "forbidden", "detail": detail}
            if response.status_code in {400, 404}:
                text_errors.append(f"{model}: {_detail(response)}")
                continue
            if response.status_code >= 400:
                text_errors.append(f"{model}: HTTP {response.status_code} — {_detail(response)}")
                continue
            text = gemini_routes._extract_text(response.json()).strip()
            if text:
                outcome.update(text_ok=True, text_model=model)
                break
            text_errors.append(f"{model}: لم يرجع نصًا")

        if not outcome["text_ok"]:
            detail = "فشل اختبار النص الحقيقي: " + " | ".join(text_errors[-4:])
            _save_record(key, {"status": "failed", "verified": False, "text_status": "failed", "detail": detail, "checked_at": int(time.time())}, clear_active=True)
            return {**outcome, "status": "failed", "detail": detail}

        tts_errors: list[str] = []
        for model in gemini_routes._tts_models():
            payload = {
                "contents": [{"parts": [{"text": "اقرأ بصوت عربي واضح: تم التحقق من المفتاح بنجاح."}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "languageCode": "ar-XA",
                        "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}},
                    },
                },
            }
            try:
                response, waited = await _post_with_window_retry(
                    client,
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    key,
                    payload,
                )
            except Exception as exc:
                tts_errors.append(f"{type(exc).__name__}: {exc}")
                continue
            if response.status_code == 429:
                retry_after = int(max(2, min(120, round(gemini_retry_window_runtime.retry_seconds(response=response, detail=_detail(response)) + 1))))
                return _temporary_result(key, number, _detail(response), retry_after, text_ok=True)
            if response.status_code == 401:
                detail = _detail(response) or "المفتاح غير صحيح أو أُلغي."
                _save_record(key, {"status": "invalid", "verified": False, "detail": detail, "checked_at": int(time.time())}, clear_active=True)
                return {**outcome, "status": "invalid", "detail": detail}
            if response.status_code == 403:
                detail = _detail(response) or "الصلاحية أو المشروع أو الفوترة ترفض إنشاء الصوت."
                _save_record(key, {"status": "forbidden", "verified": False, "detail": detail, "checked_at": int(time.time())}, clear_active=True)
                return {**outcome, "status": "forbidden", "detail": detail}
            if response.status_code in {400, 404}:
                tts_errors.append(f"{model}: {_detail(response)}")
                continue
            if response.status_code >= 400:
                tts_errors.append(f"{model}: HTTP {response.status_code} — {_detail(response)}")
                continue
            audio = gemini_routes._extract_audio(response.json())
            if audio and len(audio) >= 1000:
                outcome.update(tts_ok=True, tts_model=model)
                break
            tts_errors.append(f"{model}: لم يرجع ملفًا صوتيًا صالحًا")

        if not outcome["tts_ok"]:
            detail = "نجح النص لكن فشل اختبار الصوت الحقيقي: " + " | ".join(tts_errors[-4:])
            _save_record(
                key,
                {
                    "status": "no_audio",
                    "verified": False,
                    "text_status": "working",
                    "tts_status": "failed",
                    "text_model": outcome["text_model"],
                    "detail": detail,
                    "checked_at": int(time.time()),
                },
                clear_active=True,
            )
            return {**outcome, "status": "no_audio", "detail": detail}

    now = int(time.time())
    detail = "نجح اختبار نص فعلي واختبار صوت فعلي. المفتاح مؤكد وجاهز لكل أدوات الاستوديو."
    _save_record(
        key,
        {
            "status": "working",
            "verified": True,
            "verified_at": now,
            "text_status": "working",
            "tts_status": "working",
            "text_model": outcome["text_model"],
            "tts_model": outcome["tts_model"],
            "temporary": False,
            "retry_after_seconds": 0,
            "cooldown_until": 0,
            "detail": detail,
            "checked_at": now,
        },
    )
    outcome.update(
        ok=True,
        verified=True,
        status="working",
        detail=detail,
        capabilities=["text", "rewrite", "sermons", "scripts", "tts", "single_voice", "interviews"],
    )
    return outcome


def _cloud_provider_order(req, turns) -> list[str]:
    requested = str(req.provider or "auto")
    all_ids = all(dialogue_ultra_routes._voice_id_for_role(role) for role, _ in turns)
    eleven_ready = bool(dialogue_ultra_routes._eleven_api_key() and all_ids)
    if requested == "auto":
        return (["eleven_dialogue"] if eleven_ready else []) + ["gemini_native"]
    if requested in {"eleven_dialogue", "gemini_native", "legacy_contextual", "edge_fallback"}:
        return [requested]
    raise HTTPException(status_code=400, detail="اختر محركًا معروفًا.")


def _strict_engine_order(requested: str) -> list[str]:
    return [requested]


async def strict_interview_render(req):
    segments = interview_pro_routes._parse(req.script)
    if not segments:
        raise HTTPException(status_code=400, detail="اكتب الحوار بصيغة اسم المتحدث: النص")
    requested = req.engine if req.engine in {"gemini", "edge", "elevenlabs"} else "gemini"
    if requested == "gemini" and not strict_ordered_keys():
        raise HTTPException(status_code=409, detail="لا يوجد مفتاح Gemini مؤكد نصًا وصوتًا. اختبر مفتاحًا من مركز الربط أولًا.")
    try:
        generated, _ = await interview_pro_routes._generate_segments(segments, requested, req.base_speed)
    except HTTPException as exc:
        raise HTTPException(status_code=502, detail=f"تعذر المحرك المختار {requested}، ولم يتم التحويل إلى أي محرك آخر: {exc.detail}")

    token = uuid.uuid4().hex[:10]
    work = OUTPUTS_DIR / f"ibn_alwaqadi_interview_{token}_parts"
    work.mkdir(parents=True, exist_ok=True)
    pause = work / "pause.wav"
    interview_pro_routes._silence(pause, req.pause_ms)
    files: list[Path] = []
    for index, source in enumerate(generated):
        files.append(source)
        if index < len(generated) - 1:
            files.append(pause)
    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        raise HTTPException(status_code=500, detail="FFmpeg غير متاح داخل البرنامج.")
    concat = work / "concat.txt"
    concat.write_text("\n".join("file '" + str(path).replace("'", "'\\''") + "'" for path in files), encoding="utf-8")
    raw = OUTPUTS_DIR / f"ibn_alwaqadi_interview_{token}.wav"
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "1", str(raw)]
    process = subprocess.run(command, capture_output=True, text=True, timeout=1200, check=False)
    if process.returncode != 0 or not raw.exists():
        raise HTTPException(status_code=500, detail=(process.stderr or "فشل دمج المقابلة")[-1200:])
    final = OUTPUTS_DIR / f"ibn_alwaqadi_podcast_{token}.mp3"
    output = final if process_audio(str(raw), str(final), req.master) else raw
    target = studio_pro_routes._desktop_exports() / output.name
    shutil.copy2(output, target)
    return {
        "success": True,
        "url": f"/api/downloads/{output.name}",
        "desktop_path": str(target),
        "segments": len(segments),
        "speakers": len({role for role, _ in segments}),
        "engine_requested": requested,
        "engine_used": requested,
        "fallback": False,
        "message": "تم إنتاج المقابلة بالمحرك الذي اخترته فقط، من دون أي تحويل تلقائي.",
    }


async def strict_api_tts(req):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="النص مطلوب.")
    requested = str(req.engine or "auto")
    if requested == "auto":
        if strict_ordered_keys():
            requested = "gemini"
        else:
            eleven = tts_registry.get_plugin("elevenlabs")
            try:
                requested = "elevenlabs" if eleven and eleven.check() else ""
            except Exception:
                requested = ""
        if not requested:
            raise HTTPException(status_code=409, detail="لا يوجد محرك سحابي مؤكد. لن ينتقل البرنامج إلى صوت مجاني تلقائيًا.")
    if requested == "gemini" and not strict_ordered_keys():
        raise HTTPException(status_code=409, detail="لا يوجد مفتاح Gemini مؤكد نصًا وصوتًا. اختبره وشغّله أولًا.")
    plugin = tts_registry.get_plugin(requested)
    if not plugin:
        raise HTTPException(status_code=503, detail=f"المحرك المختار {requested} غير متاح. لم يتم تشغيل أي محرك بديل.")
    result = await plugin.generate(text=req.text, voice=req.voice, language=req.language, speed=req.speed)
    if not result or not result.get("success"):
        raise HTTPException(status_code=502, detail=(result or {}).get("message", f"فشل المحرك {requested} من دون تحويل تلقائي."))
    result["engine_requested"] = requested
    result["engine_used"] = requested
    result["fallback"] = False
    return result


def _replace_route(router, path: str, endpoint) -> None:
    for route in getattr(router, "routes", []):
        if getattr(route, "path", "") == path:
            route.endpoint = endpoint
            if getattr(route, "dependant", None) is not None:
                route.dependant.call = endpoint


def _cloud_auto_select() -> str | None:
    if strict_ordered_keys():
        return "gemini"
    eleven = tts_registry.get_plugin("elevenlabs")
    try:
        if eleven and eleven.check():
            return "elevenlabs"
    except Exception:
        pass
    return None


def install() -> None:
    pool.BLOCKED = set(HARD_FAILURES)
    pool.key_statuses = strict_key_statuses
    pool.ordered_keys = strict_ordered_keys
    pool.set_selected_key = guarded_set_active_key
    pool.set_active_key = guarded_set_active_key

    gemini_routes._test_one = strict_test_one
    gemini_routes.key_statuses = strict_key_statuses
    gemini_routes.ordered_keys = strict_ordered_keys
    gemini_routes.set_active_key = guarded_set_active_key

    gemini_rotation_runtime.ordered_keys = strict_ordered_keys
    gemini_stability_runtime.stable_ordered_keys = strict_ordered_keys
    studio_pro_routes.ordered_keys = strict_ordered_keys
    dialogue_ultra_routes._gemini_keys = strict_ordered_keys
    dialogue_safe_routes._provider_order = _cloud_provider_order
    producer_routes._engine_order = _strict_engine_order

    tts_registry.auto_select_engine = _cloud_auto_select
    routes.tts_registry.auto_select_engine = _cloud_auto_select

    _replace_route(interview_pro_routes.router, "/api/interview-pro/render", strict_interview_render)
    _replace_route(routes.router, "/api/tts", strict_api_tts)
    _replace_route(routes.router, "/api/speech", strict_api_tts)

    pool.apply_environment(strict_ordered_keys(), str(pool.load_config().get("model_id") or ""))


install()
