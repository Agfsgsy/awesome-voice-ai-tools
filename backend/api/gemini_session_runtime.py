"""Persistent Gemini sessions, queued verification, and adaptive request pacing.

Loaded after the strict cloud-only runtime. Verified keys stay trusted across pages and app
restarts. Temporary 429 responses create cooldowns and background retries; they never disconnect
a verified key. No free/mechanical engine is selected automatically.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from backend.api import (
    dialogue_ultra_routes,
    gemini_cloud_control_runtime as cloud,
    gemini_retry_window_runtime,
    gemini_rotation_runtime,
    gemini_routes,
    gemini_stability_runtime,
    studio_pro_routes,
)
from backend.core import gemini_key_pool as pool
from backend.core.config import CONFIG_DIR, OUTPUTS_DIR
from backend.plugins.gemini_tts_plugin import GeminiTTSPlugin

router = APIRouter(prefix="/api/gemini-session", tags=["Gemini Session"])

SESSION_FILE = CONFIG_DIR / "gemini_session.json"
MIN_TTS_GAP_SECONDS = 7.0
MIN_TEXT_GAP_SECONDS = 2.0
MAX_BACKGROUND_VERIFY_ATTEMPTS = 8

_BASE_ORDERED_KEYS = cloud.strict_ordered_keys
_BASE_STATUSES = cloud.strict_key_statuses
_BASE_SCENE_AUDIO = gemini_stability_runtime.stable_scene_audio
_TTS_LOCK = asyncio.Lock()
_TEXT_LOCK = asyncio.Lock()
_VERIFY_TASKS: dict[str, asyncio.Task[Any]] = {}


def _read_json(path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _read_session() -> dict[str, Any]:
    value = _read_json(SESSION_FILE)
    value.setdefault("version", 2)
    value.setdefault("session_id", uuid.uuid4().hex)
    value.setdefault("active_fp", "")
    value.setdefault("created_at", int(time.time()))
    value.setdefault("updated_at", int(time.time()))
    value.setdefault("last_tts_request_at", 0.0)
    value.setdefault("last_text_request_at", 0.0)
    value.setdefault("keys", {})
    return value


def _write_session(value: dict[str, Any]) -> None:
    value["version"] = 2
    value["updated_at"] = int(time.time())
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = SESSION_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(SESSION_FILE)


def _session_key(session: dict[str, Any], key_id: str) -> dict[str, Any]:
    keys = session.setdefault("keys", {})
    item = keys.get(key_id)
    if not isinstance(item, dict):
        item = {}
        keys[key_id] = item
    item.setdefault("cooldown_until", 0.0)
    item.setdefault("last_success_at", 0)
    item.setdefault("last_request_at", 0.0)
    item.setdefault("request_count", 0)
    item.setdefault("consecutive_429", 0)
    return item


def _entry_for_id(key_id: str) -> tuple[int, dict[str, Any]] | None:
    for number, entry in enumerate(pool.load_entries(), start=1):
        if pool.fingerprint(entry["key"]) == key_id:
            return number, entry
    return None


def _record_for_key(key: str) -> dict[str, Any]:
    _, record, _ = cloud._record_for(key)  # type: ignore[attr-defined]
    return record


def _verified(key: str) -> bool:
    return cloud._is_verified_record(_record_for_key(key))  # type: ignore[attr-defined]


def _set_session_active(key: str) -> None:
    key_id = pool.fingerprint(key)
    session = _read_session()
    session["active_fp"] = key_id
    item = _session_key(session, key_id)
    item.update(last_success_at=int(time.time()), consecutive_429=0, cooldown_until=0.0)
    _write_session(session)

    entries = pool.load_entries()
    state = pool._state([entry["key"] for entry in entries])  # type: ignore[attr-defined]
    state["selected_fp"] = key_id
    state["active_fp"] = key_id
    pool._write(pool.STATE_FILE, state)  # type: ignore[attr-defined]


def _mark_verified(key: str, text_model: str = "", tts_model: str = "") -> None:
    now = int(time.time())
    previous = _record_for_key(key)
    cloud._save_record(  # type: ignore[attr-defined]
        key,
        {
            "status": "working",
            "verified": True,
            "verified_at": int(previous.get("verified_at") or now),
            "text_status": "working",
            "tts_status": "working",
            "text_model": text_model or previous.get("text_model", "gemini-2.5-flash"),
            "tts_model": tts_model or previous.get("tts_model", "gemini-2.5-flash-preview-tts"),
            "temporary": False,
            "verification_pending": False,
            "retry_after_seconds": 0,
            "cooldown_until": 0,
            "detail": "المفتاح مؤكد ومحفوظ. لن يعاد فحصه عند التنقل بين صفحات الاستوديو.",
            "checked_at": now,
        },
    )
    _set_session_active(key)


def _mark_hard_failure(key: str, status: str, detail: str) -> None:
    cloud._save_record(  # type: ignore[attr-defined]
        key,
        {
            "status": status,
            "verified": False,
            "verification_pending": False,
            "temporary": False,
            "detail": detail[:900],
            "checked_at": int(time.time()),
        },
        clear_active=True,
    )
    session = _read_session()
    if session.get("active_fp") == pool.fingerprint(key):
        session["active_fp"] = ""
    _write_session(session)


def _mark_cooldown(key: str, detail: str, seconds: int, *, pending: bool = False) -> None:
    seconds = int(max(2, min(300, seconds)))
    key_id = pool.fingerprint(key)
    session = _read_session()
    item = _session_key(session, key_id)
    item["cooldown_until"] = time.time() + seconds
    item["consecutive_429"] = int(item.get("consecutive_429") or 0) + 1
    _write_session(session)

    previous = _record_for_key(key)
    was_verified = cloud._is_verified_record(previous)  # type: ignore[attr-defined]
    cloud._save_record(  # type: ignore[attr-defined]
        key,
        {
            "status": "working" if was_verified else "rate_limited",
            "verified": bool(was_verified),
            "temporary": True,
            "verification_pending": bool(pending and not was_verified),
            "retry_after_seconds": seconds,
            "cooldown_until": int(time.time()) + seconds,
            "last_transient_detail": detail[:900],
            "last_transient_at": int(time.time()),
            "detail": f"حد مؤقت. المفتاح محفوظ ولم يُفصل. إعادة تلقائية بعد نحو {seconds} ثانية.",
            "checked_at": int(time.time()),
        },
    )


def session_key_statuses() -> list[dict[str, Any]]:
    statuses = _BASE_STATUSES()
    now = time.time()
    for item in statuses:
        match = _entry_for_id(str(item.get("id") or ""))
        if not match:
            continue
        record = _record_for_key(match[1]["key"])
        cooldown = max(0, int(float(record.get("cooldown_until") or 0) - now))
        item["verification_pending"] = bool(record.get("verification_pending", False))
        item["retry_after_seconds"] = cooldown or int(record.get("retry_after_seconds") or 0)
        item["session_active"] = item.get("id") == _read_session().get("active_fp")
    return statuses


def session_ordered_keys() -> list[str]:
    """Keep one verified key sticky; rotate only after a real cooldown or hard failure."""
    base = list(_BASE_ORDERED_KEYS())
    if not base:
        return []
    session = _read_session()
    active_id = str(session.get("active_fp") or "")
    now = time.time()
    ready: list[str] = []
    cooling: list[tuple[float, str]] = []
    for key in base:
        until = float(_session_key(session, pool.fingerprint(key)).get("cooldown_until") or 0.0)
        (cooling if until > now else ready).append((until, key) if until > now else key)  # type: ignore[arg-type]
    ready = [key for key in ready if isinstance(key, str)]
    ready.sort(key=lambda key: pool.fingerprint(key) != active_id)
    cooling_rows = [row for row in cooling if isinstance(row, tuple)]
    cooling_rows.sort(key=lambda row: row[0])
    ordered = ready + [key for _, key in cooling_rows]
    if ordered and not active_id:
        session["active_fp"] = pool.fingerprint(ordered[0])
        _write_session(session)
    return list(dict.fromkeys(ordered))


async def _paced_post(client: httpx.AsyncClient, url: str, key: str, payload: dict[str, Any], *, kind: str) -> httpx.Response:
    lock = _TTS_LOCK if kind == "tts" else _TEXT_LOCK
    gap = MIN_TTS_GAP_SECONDS if kind == "tts" else MIN_TEXT_GAP_SECONDS
    field = "last_tts_request_at" if kind == "tts" else "last_text_request_at"
    async with lock:
        session = _read_session()
        remaining = gap - (time.time() - float(session.get(field) or 0.0))
        if remaining > 0:
            await asyncio.sleep(remaining)
        session = _read_session()
        session[field] = time.time()
        item = _session_key(session, pool.fingerprint(key))
        item["last_request_at"] = time.time()
        item["request_count"] = int(item.get("request_count") or 0) + 1
        _write_session(session)
        return await client.post(url, headers={"x-goog-api-key": key, "Content-Type": "application/json"}, json=payload)


def _retry_seconds(response: httpx.Response, attempt: int = 1) -> int:
    value = gemini_retry_window_runtime.retry_seconds(
        response=response,
        detail=gemini_routes._error_detail(response),
        attempt=attempt,
    )
    return int(max(2, min(300, round(value + 1))))


async def _verify_text(key: str) -> tuple[str, str, int]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(80.0, connect=25.0)) as client:
        for model in (await gemini_routes._available_text_models(client, key))[:5]:
            payload = {"contents": [{"parts": [{"text": "أجب بهذه الكلمة فقط: جاهز"}]}], "generationConfig": {"temperature": 0, "maxOutputTokens": 8}}
            response = await _paced_post(client, f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", key, payload, kind="text")
            if response.status_code == 429:
                return "rate_limited", gemini_routes._error_detail(response), _retry_seconds(response)
            if response.status_code == 401:
                return "invalid", gemini_routes._error_detail(response), 0
            if response.status_code == 403:
                return "forbidden", gemini_routes._error_detail(response), 0
            if response.status_code in {400, 404}:
                continue
            if response.status_code >= 500:
                await asyncio.sleep(2)
                continue
            if response.status_code < 400 and gemini_routes._extract_text(response.json()).strip():
                return "working", model, 0
    return "failed", "لم يرجع اختبار النص نتيجة صالحة.", 0


async def _verify_audio(key: str) -> tuple[str, str, int]:
    payload = {
        "contents": [{"parts": [{"text": "حوّل النص التالي إلى صوت عربي واضح. النص المنطوق: تم التحقق بنجاح."}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"languageCode": "ar-XA", "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}},
        },
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=30.0)) as client:
        for model in gemini_routes._tts_models():
            for attempt in (1, 2):
                response = await _paced_post(client, f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", key, payload, kind="tts")
                if response.status_code == 429:
                    return "rate_limited", gemini_routes._error_detail(response), _retry_seconds(response, attempt)
                if response.status_code == 401:
                    return "invalid", gemini_routes._error_detail(response), 0
                if response.status_code == 403:
                    return "forbidden", gemini_routes._error_detail(response), 0
                if response.status_code in {400, 404}:
                    break
                if response.status_code >= 500:
                    if attempt == 1:
                        await asyncio.sleep(2.5)
                        continue
                    break
                if response.status_code < 400:
                    audio = gemini_routes._extract_audio(response.json())
                    if audio and len(audio) >= 700:
                        return "working", model, 0
                    if attempt == 1:
                        await asyncio.sleep(2)
                        continue
                break
    return "no_audio", "لم يرجع نموذج الصوت بيانات صوتية صالحة بعد محاولتين.", 0


def _cached_result(key: str, number: int, *, fresh: bool = False) -> dict[str, Any]:
    record = _record_for_key(key)
    return {
        "number": number,
        "ok": True,
        "verified": True,
        "cached": not fresh,
        "status": "working",
        "detail": "نجح اختبار النص والصوت وحُفظت الجلسة." if fresh else "الفحص محفوظ؛ لم نرسل طلبات جديدة ولم نستهلك الحصة.",
        "text_ok": True,
        "tts_ok": True,
        "text_model": record.get("text_model", ""),
        "tts_model": record.get("tts_model", ""),
        "capabilities": ["text", "rewrite", "sermons", "scripts", "tts", "single_voice", "interviews"],
    }


def _pending_result(key: str, number: int, seconds: int) -> dict[str, Any]:
    record = _record_for_key(key)
    return {
        "number": number,
        "ok": False,
        "verified": False,
        "pending": True,
        "temporary": True,
        "status": "rate_limited",
        "retry_after_seconds": seconds,
        "detail": f"فحص الصوت في الانتظار، وسيعاد تلقائيًا بعد نحو {seconds} ثانية.",
        "text_ok": str(record.get("text_status") or "") == "working",
        "tts_ok": False,
        "text_model": record.get("text_model", ""),
        "tts_model": "",
        "capabilities": [],
    }


async def _verify_cycle(key: str, number: int, *, schedule_on_limit: bool) -> dict[str, Any]:
    if _verified(key):
        _set_session_active(key)
        return _cached_result(key, number)

    record = _record_for_key(key)
    text_model = str(record.get("text_model") or "")
    if str(record.get("text_status") or "") != "working":
        status, detail, wait = await _verify_text(key)
        if status == "rate_limited":
            _mark_cooldown(key, detail, wait, pending=True)
            if schedule_on_limit:
                _queue_verify(key, number, wait)
            return _pending_result(key, number, wait)
        if status in {"invalid", "forbidden"}:
            _mark_hard_failure(key, status, detail)
            return {"number": number, "ok": False, "verified": False, "status": status, "detail": detail, "text_ok": False, "tts_ok": False, "capabilities": []}
        if status != "working":
            cloud._save_record(key, {"status": "failed", "verified": False, "text_status": "failed", "detail": detail, "checked_at": int(time.time())}, clear_active=True)  # type: ignore[attr-defined]
            return {"number": number, "ok": False, "verified": False, "status": "failed", "detail": detail, "text_ok": False, "tts_ok": False, "capabilities": []}
        text_model = detail
        cloud._save_record(key, {"text_status": "working", "text_model": text_model, "detail": "نجح النص؛ يبدأ فحص الصوت.", "checked_at": int(time.time())})  # type: ignore[attr-defined]

    status, detail, wait = await _verify_audio(key)
    if status == "working":
        _mark_verified(key, text_model, detail)
        return _cached_result(key, number, fresh=True)
    if status == "rate_limited":
        _mark_cooldown(key, detail, wait, pending=True)
        if schedule_on_limit:
            _queue_verify(key, number, wait)
        return _pending_result(key, number, wait)
    if status in {"invalid", "forbidden"}:
        _mark_hard_failure(key, status, detail)
        return {"number": number, "ok": False, "verified": False, "status": status, "detail": detail, "text_ok": True, "tts_ok": False, "capabilities": []}

    cloud._save_record(  # type: ignore[attr-defined]
        key,
        {"status": "no_audio", "verified": False, "text_status": "working", "tts_status": "failed", "text_model": text_model, "detail": detail, "checked_at": int(time.time())},
        clear_active=True,
    )
    return {"number": number, "ok": False, "verified": False, "status": "no_audio", "detail": detail, "text_ok": True, "tts_ok": False, "capabilities": []}


async def _background_verify(key: str, number: int, initial_delay: int) -> None:
    key_id = pool.fingerprint(key)
    delay = int(max(2, initial_delay))
    try:
        for _ in range(MAX_BACKGROUND_VERIFY_ATTEMPTS):
            await asyncio.sleep(delay)
            if not any(entry["key"] == key and entry.get("enabled", True) for entry in pool.load_entries()):
                return
            result = await _verify_cycle(key, number, schedule_on_limit=False)
            if result.get("verified") or result.get("status") in {"invalid", "forbidden"}:
                return
            if result.get("status") == "rate_limited":
                delay = int(result.get("retry_after_seconds") or 20)
            else:
                delay = min(120, max(15, delay * 2))
                _mark_cooldown(key, str(result.get("detail") or "فشل مؤقت"), delay, pending=True)
    finally:
        _VERIFY_TASKS.pop(key_id, None)


def _queue_verify(key: str, number: int, seconds: int) -> None:
    key_id = pool.fingerprint(key)
    task = _VERIFY_TASKS.get(key_id)
    if task and not task.done():
        return
    try:
        _VERIFY_TASKS[key_id] = asyncio.create_task(_background_verify(key, number, seconds))
    except RuntimeError:
        pass


async def smart_test_one(key: str, number: int = 1) -> dict[str, Any]:
    if _verified(key):
        _set_session_active(key)
        return _cached_result(key, number)
    task = _VERIFY_TASKS.get(pool.fingerprint(key))
    if task and not task.done():
        return _pending_result(key, number, int(_record_for_key(key).get("retry_after_seconds") or 20))
    return await _verify_cycle(key, number, schedule_on_limit=True)


async def smart_activate_key(key_id: str):
    match = _entry_for_id(key_id)
    if not match:
        raise HTTPException(status_code=404, detail="المفتاح غير موجود.")
    number, entry = match
    result = await smart_test_one(entry["key"], number)
    activated = bool(result.get("verified"))
    if activated:
        cloud.guarded_set_active_key(key_id)
        _set_session_active(entry["key"])
    payload = gemini_routes._key_payload()
    payload.update({"activated": activated, "result": result, "message": "تم تثبيت المفتاح للجلسة من دون إعادة فحص." if result.get("cached") and activated else result.get("detail", "اكتمل الفحص.")})
    return payload


async def smart_test_single_key(key_id: str):
    match = _entry_for_id(key_id)
    if not match:
        raise HTTPException(status_code=404, detail="المفتاح غير موجود.")
    number, entry = match
    result = await smart_test_one(entry["key"], number)
    payload = gemini_routes._key_payload()
    payload.update({"result": result, "message": result.get("detail", "اكتمل الفحص.")})
    return payload


async def smart_generate(self: GeminiTTSPlugin, text: str, voice: str = "default", language: str = "ar", speed: float = 1.0) -> dict[str, Any]:
    keys = session_ordered_keys()
    if not keys:
        return {"success": False, "engine": self.name, "fallback": False, "message": "لا يوجد مفتاح Gemini مؤكد. سيعيد البرنامج فحص المفاتيح المعلقة تلقائيًا."}
    clean_text = "\n".join(line.strip() for line in (text or "").splitlines() if line.strip())
    if not clean_text:
        return {"success": False, "engine": self.name, "fallback": False, "message": "النص فارغ."}
    if len(clean_text) > 12000:
        return {"success": False, "engine": self.name, "fallback": False, "message": "النص أطول من 12000 حرف. قسّمه إلى أجزاء أقصر."}

    raw_voice, profile = (voice or "Kore"), "human_ultra"
    if "|" in raw_voice:
        raw_voice, profile = raw_voice.split("|", 1)
    selected_voice = raw_voice if raw_voice in self.VOICES else "Kore"
    preferred = self._model() if self._model() in self.MODELS else "gemini-2.5-flash-preview-tts"
    models = list(dict.fromkeys([preferred, "gemini-2.5-flash-preview-tts", "gemini-3.1-flash-tts-preview", "gemini-2.5-pro-preview-tts"]))
    guidance = self.PROFILES.get(profile, self.PROFILES["human_ultra"])
    speed_note = "متوسطة" if 0.9 <= speed <= 1.1 else ("بطيئة قليلًا" if speed < 0.9 else "سريعة قليلًا")
    prompt = f"{guidance}\nالسرعة: {speed_note}. افهم المعنى ثم انطق النص فقط:\n\n{clean_text}"
    digest = hashlib.sha256(f"gemini-session-v420|{preferred}|{selected_voice}|{profile}|{speed}|{clean_text}".encode()).hexdigest()[:18]
    output = OUTPUTS_DIR / f"gemini_{profile}_{digest}.wav"
    if output.exists() and output.stat().st_size > 44:
        return {"success": True, "engine": self.name, "url": f"/api/downloads/{output.name}", "file": str(output), "fallback": False, "message": "تم تحميل الصوت من الذاكرة المؤقتة دون طلب جديد."}

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"languageCode": "ar-XA", "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": selected_voice}}}},
    }
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=35.0)) as client:
        for number, key in enumerate(keys, start=1):
            session = _read_session()
            cooldown = float(_session_key(session, pool.fingerprint(key)).get("cooldown_until") or 0) - time.time()
            if cooldown > 0 and len(keys) > 1:
                errors.append(f"المفتاح {number}: ينتظر {int(cooldown)} ثانية")
                continue
            hard_failure = False
            for model in models:
                last_status = 0
                for attempt in (1, 2):
                    try:
                        response = await _paced_post(client, f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", key, payload, kind="tts")
                        last_status = response.status_code
                    except Exception as exc:
                        if attempt == 1:
                            await asyncio.sleep(2)
                            continue
                        errors.append(f"المفتاح {number}: اتصال مؤقت {type(exc).__name__}")
                        break
                    if last_status == 429:
                        wait = _retry_seconds(response, attempt)
                        _mark_cooldown(key, gemini_routes._error_detail(response), wait)
                        if len(keys) == 1 and attempt == 1 and wait <= 120:
                            await asyncio.sleep(wait)
                            continue
                        errors.append(f"المفتاح {number}: حد مؤقت {wait} ثانية")
                        break
                    if last_status == 401:
                        _mark_hard_failure(key, "invalid", gemini_routes._error_detail(response))
                        errors.append(f"المفتاح {number}: غير صحيح")
                        hard_failure = True
                        break
                    if last_status == 403:
                        _mark_hard_failure(key, "forbidden", gemini_routes._error_detail(response))
                        errors.append(f"المفتاح {number}: الصلاحية أو المشروع مرفوض")
                        hard_failure = True
                        break
                    if last_status in {400, 404}:
                        errors.append(f"{model}: غير متاح لهذا المشروع")
                        break
                    if last_status >= 500:
                        if attempt == 1:
                            await asyncio.sleep(3)
                            continue
                        errors.append(f"{model}: خطأ خادم مؤقت")
                        break
                    if last_status >= 400:
                        errors.append(f"{model}: HTTP {last_status}")
                        break
                    pcm = self._extract_audio(response.json())
                    if not pcm:
                        if attempt == 1:
                            await asyncio.sleep(2)
                            continue
                        errors.append(f"{model}: لم يرجع صوتًا")
                        break
                    self._save_wav(output, pcm)
                    _mark_verified(key, str(_record_for_key(key).get("text_model") or "gemini-2.5-flash"), model)
                    pool.apply_environment(session_ordered_keys(), preferred)
                    return {
                        "success": True,
                        "engine": self.name,
                        "model": model,
                        "voice": selected_voice,
                        "profile": profile,
                        "key_used": number,
                        "file": str(output),
                        "url": f"/api/downloads/{output.name}",
                        "fallback": False,
                        "session_id": _read_session().get("session_id"),
                        "message": f"تم إنشاء الصوت بالمفتاح المؤكد رقم {number}. الجلسة محفوظة.",
                    }
                if hard_failure or last_status == 429:
                    break
            if hard_failure:
                continue
    return {"success": False, "engine": self.name, "fallback": False, "message": "تعذر Gemini مؤقتًا ولم يتم التحويل إلى صوت مجاني. " + " | ".join(errors[-6:])}


async def paced_scene_audio(*args, **kwargs):
    keys = session_ordered_keys()
    mutable_args = list(args)
    if len(mutable_args) >= 5:
        mutable_args[4] = keys
    else:
        kwargs["session_keys"] = keys
    async with _TTS_LOCK:
        session = _read_session()
        remaining = MIN_TTS_GAP_SECONDS - (time.time() - float(session.get("last_tts_request_at") or 0.0))
        if remaining > 0:
            await asyncio.sleep(remaining)
        session["last_tts_request_at"] = time.time()
        _write_session(session)
        result = await _BASE_SCENE_AUDIO(*mutable_args, **kwargs)
    try:
        _, model, key_number = result
        current = session_ordered_keys()
        if current and 1 <= int(key_number) <= len(current):
            key = current[int(key_number) - 1]
            _mark_verified(key, str(_record_for_key(key).get("text_model") or "gemini-2.5-flash"), str(model))
    except Exception:
        pass
    return result


def _replace_route(path: str, endpoint) -> None:
    for route in getattr(gemini_routes.router, "routes", []):
        if getattr(route, "path", "") == path:
            route.endpoint = endpoint
            if getattr(route, "dependant", None) is not None:
                route.dependant.call = endpoint


def _resume_pending() -> None:
    now = time.time()
    for number, entry in enumerate(pool.load_entries(), start=1):
        record = _record_for_key(entry["key"])
        if not entry.get("enabled", True) or not record.get("verification_pending"):
            continue
        delay = max(2, int(float(record.get("cooldown_until") or 0) - now))
        _queue_verify(entry["key"], number, delay)


@router.get("/status")
async def session_status():
    _resume_pending()
    session = _read_session()
    statuses = session_key_statuses()
    active = next((item for item in statuses if item.get("active") and item.get("verified")), None)
    return {
        "success": True,
        "session_id": session.get("session_id"),
        "active_id": active.get("id") if active else "",
        "active_label": active.get("label") if active else "",
        "verified_keys": sum(1 for item in statuses if item.get("verified")),
        "pending_verifications": sum(1 for item in statuses if item.get("verification_pending")),
        "last_tts_request_at": session.get("last_tts_request_at", 0),
        "message": "الجلسة محفوظة وثابتة بين جميع صفحات الاستوديو.",
    }


@router.post("/resume")
async def resume_verification():
    _resume_pending()
    return await session_status()


def install() -> None:
    cloud.strict_ordered_keys = session_ordered_keys
    cloud.strict_key_statuses = session_key_statuses
    pool.ordered_keys = session_ordered_keys
    pool.key_statuses = session_key_statuses
    gemini_routes.ordered_keys = session_ordered_keys
    gemini_routes.key_statuses = session_key_statuses
    gemini_rotation_runtime.ordered_keys = session_ordered_keys
    gemini_stability_runtime.stable_ordered_keys = session_ordered_keys
    studio_pro_routes.ordered_keys = session_ordered_keys
    dialogue_ultra_routes._gemini_keys = session_ordered_keys

    gemini_routes._test_one = smart_test_one
    GeminiTTSPlugin.generate = smart_generate
    gemini_stability_runtime.stable_scene_audio = paced_scene_audio

    _replace_route("/api/gemini/keys/{key_id}/activate", smart_activate_key)
    _replace_route("/api/gemini/keys/{key_id}/test", smart_test_single_key)

    pool.apply_environment(session_ordered_keys(), str(pool.load_config().get("model_id") or "gemini-2.5-flash-preview-tts"))


install()
