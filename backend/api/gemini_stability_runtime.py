"""Additive stability fix for long Gemini audio/interview jobs.

Temporary 429/network errors no longer disconnect saved keys. Long interviews keep one
snapshot of the enabled key pool, use the documented generateContent multi-speaker TTS
endpoint, retry each key, and never force a mechanical fallback.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException

from backend.api import dashboard_routes, dialogue_safe_routes, dialogue_ultra_routes
from backend.api import gemini_routes, gemini_rotation_runtime, studio_pro_routes
from backend.core import gemini_key_pool as pool
from backend.core.config import OUTPUTS_DIR

HARD_BLOCKED = {"invalid", "forbidden"}
_original_record_result = pool.record_result
_original_safe_render_provider = dialogue_safe_routes._render_provider


def _detail(response: httpx.Response) -> str:
    try:
        data = response.json()
        if isinstance(data, dict):
            return str((data.get("error") or {}).get("message") or data.get("message") or response.text[:900])
    except Exception:
        pass
    return response.text[:900]


def _delay(response: httpx.Response | None, attempt: int) -> float:
    if response is not None:
        try:
            value = float(str(response.headers.get("retry-after", "")).strip())
            return max(1.0, min(18.0, value))
        except Exception:
            pass
    return min(15.0, 1.5 * (2 ** max(0, attempt - 1)))


def _repair_previous_false_disconnects() -> None:
    """Undo quota states created when the old wrapper marked every key after one failed job."""
    entries = pool.load_entries()
    if not entries:
        return
    state = pool._read(pool.STATE_FILE)  # type: ignore[attr-defined]
    records = state.get("records") if isinstance(state.get("records"), dict) else {}
    repaired_ids: list[str] = []
    for item in entries:
        if not item.get("enabled", True):
            continue
        key_id = pool.fingerprint(item["key"])
        record = dict(records.get(key_id) or {})
        if str(record.get("status") or "") == "quota":
            record.update(
                status="working",
                detail="تم إصلاح فصل مؤقت خاطئ. المفتاح ما يزال مفعّلًا وسيُعاد استخدامه تلقائيًا.",
                checked_at=int(time.time()),
                cooldown_until=0,
            )
            records[key_id] = record
            repaired_ids.append(key_id)
    if repaired_ids:
        selected = str(state.get("selected_fp") or "")
        if selected not in repaired_ids:
            selected = repaired_ids[0]
        state.update(selected_fp=selected, active_fp=selected, records=records, updated_at=int(time.time()))
        pool._write(pool.STATE_FILE, state)  # type: ignore[attr-defined]


def stable_record_result(key: str, status: str, detail: str = "", retry_after: float | None = None) -> None:
    """Hard failures disconnect; temporary failures keep the key enabled and selected."""
    status = str(status or "failed").lower()
    if status == "working" or status in HARD_BLOCKED:
        _original_record_result(key, status, detail)
        return

    entries = pool.load_entries()
    keys = [item["key"] for item in entries]
    if key not in keys:
        return
    state = pool._state(keys)  # type: ignore[attr-defined]
    key_id = pool.fingerprint(key)
    record = dict((state.get("records") or {}).get(key_id) or {})
    was_working = str(record.get("status") or "") == "working"
    wait = int(max(15, min(300, float(retry_after or (60 if status in {"quota", "rate_limited"} else 25)))))
    friendly = (
        f"حد طلبات مؤقت؛ المفتاح لم يُفصل وسيُعاد استخدامه تلقائيًا بعد نحو {wait} ثانية."
        if status in {"quota", "rate_limited"}
        else "مشكلة مؤقتة في هذا الطلب؛ المفتاح ما يزال مفعّلًا وسيُعاد استخدامه تلقائيًا."
    )
    record.update(
        status="working" if was_working else "untested",
        detail=friendly,
        last_transient_status=status,
        last_transient_detail=detail[:900],
        last_transient_at=int(time.time()),
        cooldown_until=int(time.time()) + wait,
    )
    state.setdefault("records", {})[key_id] = record
    pool._write(pool.STATE_FILE, state)  # type: ignore[attr-defined]


def stable_ordered_keys() -> list[str]:
    """Keep temporary states usable; prefer ready keys, then cooling keys."""
    entries = [item for item in pool.load_entries() if item.get("enabled", True)]
    if not entries:
        return []
    all_keys = [item["key"] for item in pool.load_entries()]
    state = pool._state(all_keys)  # type: ignore[attr-defined]
    records = state.get("records", {})
    selected = str(state.get("selected_fp") or state.get("active_fp") or "")
    now = time.time()
    ready: list[tuple[bool, str]] = []
    cooling: list[tuple[bool, str]] = []
    for item in entries:
        key = item["key"]
        key_id = pool.fingerprint(key)
        record = dict(records.get(key_id) or {})
        if str(record.get("status") or "untested") in HARD_BLOCKED:
            continue
        target = cooling if float(record.get("cooldown_until", 0) or 0) > now else ready
        target.append((key_id == selected, key))
    ordered = [key for selected_flag, key in sorted(ready, key=lambda x: not x[0])]
    ordered += [key for selected_flag, key in sorted(cooling, key=lambda x: not x[0])]
    return list(dict.fromkeys(ordered))


def _generate_content_payload(prompt: str, speech_config: list[dict[str, str]]) -> dict[str, Any]:
    speaker_voice_configs = []
    for item in speech_config:
        speaker = str(item.get("speaker") or "").strip()
        voice = str(item.get("voice") or "Kore").strip()
        if not speaker:
            continue
        speaker_voice_configs.append(
            {
                "speaker": speaker,
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}},
            }
        )
    return {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "languageCode": "ar-XA",
                "multiSpeakerVoiceConfig": {"speakerVoiceConfigs": speaker_voice_configs},
            },
        },
    }


async def stable_scene_audio(
    turns: list[tuple[str, str]],
    tone: str,
    dialect: str,
    preferred_model: str,
    session_keys: list[str] | None = None,
) -> tuple[bytes, str, int]:
    """Generate one scene through documented multi-speaker generateContent without disconnecting keys."""
    keys = list(session_keys or stable_ordered_keys())
    if not keys:
        raise HTTPException(status_code=400, detail="لا يوجد مفتاح Gemini مفعّل للمقابلة.")
    prompt, speech_config = dialogue_ultra_routes._gemini_scene_prompt(turns, tone, dialect)
    models = list(dict.fromkeys([preferred_model, *dialogue_ultra_routes.GEMINI_MODELS]))
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=httpx.Timeout(360.0, connect=35.0)) as client:
        for key_index, key in enumerate(keys, start=1):
            hard_failure = False
            for model in models:
                endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                payload = _generate_content_payload(prompt, speech_config)
                for attempt in (1, 2, 3):
                    response: httpx.Response | None = None
                    try:
                        response = await client.post(
                            endpoint,
                            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                            json=payload,
                        )
                        if response.status_code == 429:
                            wait = _delay(response, attempt)
                            if attempt < 3:
                                await asyncio.sleep(wait)
                                continue
                            stable_record_result(key, "rate_limited", _detail(response), wait)
                            errors.append(f"المفتاح {key_index}: حد مؤقت 429 — {_detail(response)[:220]}")
                            break
                        if response.status_code == 401:
                            stable_record_result(key, "invalid", _detail(response))
                            errors.append(f"المفتاح {key_index}: غير صحيح")
                            hard_failure = True
                            break
                        if response.status_code == 403:
                            stable_record_result(key, "forbidden", _detail(response))
                            errors.append(f"المفتاح {key_index}: الصلاحية أو الفوترة مرفوضة — {_detail(response)[:220]}")
                            hard_failure = True
                            break
                        if response.status_code in {400, 404}:
                            errors.append(f"{model}: غير متاح لهذا المشروع — {_detail(response)[:220]}")
                            break
                        if response.status_code >= 500:
                            if attempt < 3:
                                await asyncio.sleep(_delay(response, attempt))
                                continue
                            stable_record_result(key, "network", _detail(response), 25)
                            errors.append(f"المفتاح {key_index}: خطأ خادم مؤقت")
                            break
                        response.raise_for_status()
                        pcm = dialogue_ultra_routes._extract_interaction_audio(response.json())
                        if not pcm:
                            # generateContent uses candidates/content/parts/inlineData.
                            for candidate in response.json().get("candidates") or []:
                                for part in (candidate.get("content") or {}).get("parts") or []:
                                    inline = part.get("inlineData") or part.get("inline_data") or {}
                                    data = inline.get("data")
                                    if data:
                                        import base64
                                        pcm = base64.b64decode(data)
                                        break
                                if pcm:
                                    break
                        if pcm:
                            stable_record_result(key, "working", str(model))
                            return pcm, model, key_index
                        errors.append(f"{model}: نجح الطلب لكنه لم يرجع بيانات صوتية")
                        break
                    except Exception as exc:
                        if attempt < 3:
                            await asyncio.sleep(min(6.0, float(attempt) * 1.5))
                            continue
                        stable_record_result(key, "network", f"{type(exc).__name__}: {exc}", 25)
                        errors.append(f"المفتاح {key_index}: اتصال مؤقت — {type(exc).__name__}")
                if hard_failure:
                    break
    raise HTTPException(
        status_code=502,
        detail="تعذر مشهد Gemini السحابي من دون التحويل إلى صوت ميكانيكي. " + "; ".join(errors[-8:]),
    )


async def stable_safe_render_provider(provider: str, req, turns, token: str):
    """Freeze the key pool for the full interview and keep the successful key first."""
    if provider != "gemini_native":
        return await _original_safe_render_provider(provider, req, turns, token)
    session_keys = list(stable_ordered_keys())
    if not session_keys:
        raise HTTPException(status_code=400, detail="لا يوجد مفتاح Gemini مفعّل.")
    scene_paths: list[Path] = []
    models: list[str] = []
    for index, scene in enumerate(dialogue_ultra_routes._scene_chunks(turns)):
        pcm, model, key_index = await stable_scene_audio(scene, req.tone, req.dialect, req.gemini_model, session_keys)
        used_key = session_keys[max(0, key_index - 1)]
        session_keys = [used_key] + [key for key in session_keys if key != used_key]
        path = OUTPUTS_DIR / f"gemini_native_stable_{token}_{index}.wav"
        dialogue_ultra_routes._save_wav(path, pcm)
        scene_paths.append(path)
        models.append(model)
    raw = OUTPUTS_DIR / f"ibn_alwaqadi_gemini_native_stable_{token}.wav"
    dialogue_ultra_routes._concat_audio(scene_paths, raw, req.pause_ms)
    return raw, ",".join(dict.fromkeys(models))


def install() -> None:
    _repair_previous_false_disconnects()
    pool.BLOCKED = set(HARD_BLOCKED)
    pool.record_result = stable_record_result
    pool.ordered_keys = stable_ordered_keys

    gemini_routes.record_result = stable_record_result
    studio_pro_routes.record_result = stable_record_result
    studio_pro_routes.ordered_keys = stable_ordered_keys
    gemini_rotation_runtime.record_result = stable_record_result
    gemini_rotation_runtime.ordered_keys = stable_ordered_keys

    dialogue_ultra_routes._gemini_keys = stable_ordered_keys
    dialogue_ultra_routes._gemini_scene_audio = stable_scene_audio
    dialogue_safe_routes._render_provider = stable_safe_render_provider

    pool.apply_environment(stable_ordered_keys(), str(pool.load_config().get("model_id") or ""))


install()
