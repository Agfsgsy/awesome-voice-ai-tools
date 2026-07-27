"""Single-request Gemini verification and production-first activation.

This additive runtime is loaded after the persistent-session layer.
It reduces verification traffic by using one very short TTS request only. A successful
TTS response proves that the request text was accepted and that real audio was returned,
so the key is marked text+audio verified in one operation.

Unverified enabled keys may be tried by the user's first real production request. Success
verifies and pins the key. Temporary 429 responses create a cooldown and never select a
free/mechanical engine.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from backend.api import (
    dialogue_ultra_routes,
    gemini_cloud_control_runtime as cloud,
    gemini_retry_window_runtime,
    gemini_rotation_runtime,
    gemini_routes,
    gemini_session_runtime as session,
    gemini_stability_runtime,
    studio_pro_routes,
)
from backend.core import gemini_key_pool as pool

MAX_AUTOMATIC_PROBES = 3
EXTRA_COOLDOWN_SECONDS = 5


def _candidate_ordered_keys() -> list[str]:
    """Verified keys first, then enabled unverified keys ready for production-first verification."""
    entries = [entry for entry in pool.load_entries() if entry.get("enabled", True)]
    if not entries:
        return []

    stored = session._read_session()  # type: ignore[attr-defined]
    active_id = str(stored.get("active_fp") or "")
    now = time.time()
    verified_ready: list[tuple[bool, str]] = []
    trial_ready: list[tuple[bool, str]] = []

    for entry in entries:
        key = entry["key"]
        key_id = pool.fingerprint(key)
        record = session._record_for_key(key)  # type: ignore[attr-defined]
        status = str(record.get("status") or "untested")
        if status in {"invalid", "forbidden"}:
            continue

        item = session._session_key(stored, key_id)  # type: ignore[attr-defined]
        cooldown = max(float(item.get("cooldown_until") or 0), float(record.get("cooldown_until") or 0))
        if cooldown > now:
            continue

        row = (key_id == active_id, key)
        if session._verified(key):  # type: ignore[attr-defined]
            verified_ready.append(row)
        else:
            trial_ready.append(row)

    verified_ready.sort(key=lambda row: not row[0])
    trial_ready.sort(key=lambda row: not row[0])
    return list(dict.fromkeys([key for _, key in verified_ready + trial_ready]))


def _configured_tts_models() -> list[str]:
    configured = str(pool.load_config().get("model_id") or "").strip()
    models = [configured] if configured and "tts" in configured.lower() else []
    models.extend(gemini_routes._tts_models())
    return list(dict.fromkeys(model for model in models if model))


async def _single_audio_probe(key: str) -> tuple[str, str, int]:
    """One tiny real-audio request. No separate text request is sent."""
    payload = {
        "contents": [{"parts": [{"text": "انطق كلمة واحدة فقط: جاهز"}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "languageCode": "ar-XA",
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}},
            },
        },
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=30.0)) as client:
        for model in _configured_tts_models():
            try:
                response = await session._paced_post(  # type: ignore[attr-defined]
                    client,
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    key,
                    payload,
                    kind="tts",
                )
            except Exception as exc:
                return "network", f"{type(exc).__name__}: {exc}", 30

            if response.status_code == 429:
                wait = gemini_retry_window_runtime.retry_seconds(
                    response=response,
                    detail=gemini_routes._error_detail(response),
                    attempt=1,
                )
                return "rate_limited", gemini_routes._error_detail(response), int(max(10, min(300, round(wait + EXTRA_COOLDOWN_SECONDS))))
            if response.status_code == 401:
                return "invalid", gemini_routes._error_detail(response), 0
            if response.status_code == 403:
                return "forbidden", gemini_routes._error_detail(response), 0
            if response.status_code in {400, 404}:
                continue
            if response.status_code >= 500:
                return "network", gemini_routes._error_detail(response), 35
            if response.status_code >= 400:
                return "failed", gemini_routes._error_detail(response), 0

            audio = gemini_routes._extract_audio(response.json())
            if audio and len(audio) >= 500:
                return "working", model, 0
            return "no_audio", f"النموذج {model} لم يرجع بيانات صوتية صالحة.", 0

    return "model_unavailable", "لا يوجد نموذج TTS متاح لهذا المشروع حاليًا.", 0


def _pending_result(key: str, number: int, seconds: int) -> dict[str, Any]:
    return {
        "number": number,
        "ok": False,
        "verified": False,
        "pending": True,
        "temporary": True,
        "status": "rate_limited",
        "retry_after_seconds": max(1, int(seconds)),
        "detail": f"حد مؤقت. سيُرسل طلب صوت قصير واحد فقط بعد نحو {max(1, int(seconds))} ثانية. يمكنك أيضًا بدء إنتاجك الحقيقي؛ نجاحه يعتمد المفتاح مباشرة.",
        "text_ok": False,
        "tts_ok": False,
        "capabilities": [],
    }


async def _one_probe_cycle(key: str, number: int, *, schedule_on_limit: bool) -> dict[str, Any]:
    if session._verified(key):  # type: ignore[attr-defined]
        session._set_session_active(key)  # type: ignore[attr-defined]
        return session._cached_result(key, number)  # type: ignore[attr-defined]

    stored = session._read_session()  # type: ignore[attr-defined]
    key_item = session._session_key(stored, pool.fingerprint(key))  # type: ignore[attr-defined]
    record = session._record_for_key(key)  # type: ignore[attr-defined]
    remaining = int(max(0, max(float(key_item.get("cooldown_until") or 0), float(record.get("cooldown_until") or 0)) - time.time()))
    if remaining > 0:
        session._mark_cooldown(key, str(record.get("last_transient_detail") or "حد مؤقت"), remaining, pending=True)  # type: ignore[attr-defined]
        if schedule_on_limit:
            _queue_one_probe(key, number, remaining)
        return _pending_result(key, number, remaining)

    status, detail, wait = await _single_audio_probe(key)
    if status == "working":
        session._mark_verified(key, detail, detail)  # type: ignore[attr-defined]
        stored = session._read_session()  # type: ignore[attr-defined]
        item = session._session_key(stored, pool.fingerprint(key))  # type: ignore[attr-defined]
        item["automatic_probe_attempts"] = 0
        session._write_session(stored)  # type: ignore[attr-defined]
        pool.apply_environment(_candidate_ordered_keys(), detail)
        return session._cached_result(key, number, fresh=True)  # type: ignore[attr-defined]

    if status == "rate_limited":
        session._mark_cooldown(key, detail, wait, pending=True)  # type: ignore[attr-defined]
        if schedule_on_limit:
            _queue_one_probe(key, number, wait)
        return _pending_result(key, number, wait)

    if status in {"invalid", "forbidden"}:
        session._mark_hard_failure(key, status, detail)  # type: ignore[attr-defined]
        return {
            "number": number,
            "ok": False,
            "verified": False,
            "status": status,
            "detail": detail,
            "text_ok": False,
            "tts_ok": False,
            "capabilities": [],
        }

    if status == "network":
        session._mark_cooldown(key, detail, wait or 30, pending=True)  # type: ignore[attr-defined]
        if schedule_on_limit:
            _queue_one_probe(key, number, wait or 30)
        return _pending_result(key, number, wait or 30)

    cloud._save_record(  # type: ignore[attr-defined]
        key,
        {
            "status": status,
            "verified": False,
            "verification_pending": False,
            "text_status": "untested",
            "tts_status": "failed",
            "detail": detail,
            "checked_at": int(time.time()),
        },
        clear_active=True,
    )
    return {
        "number": number,
        "ok": False,
        "verified": False,
        "status": status,
        "detail": detail,
        "text_ok": False,
        "tts_ok": False,
        "capabilities": [],
    }


async def _one_background_probe(key: str, number: int, initial_delay: int) -> None:
    key_id = pool.fingerprint(key)
    next_delay = 0
    try:
        await asyncio.sleep(max(2, int(initial_delay)))
        if not any(entry["key"] == key and entry.get("enabled", True) for entry in pool.load_entries()):
            return

        stored = session._read_session()  # type: ignore[attr-defined]
        item = session._session_key(stored, key_id)  # type: ignore[attr-defined]
        attempts = int(item.get("automatic_probe_attempts") or 0)
        if attempts >= MAX_AUTOMATIC_PROBES:
            return
        item["automatic_probe_attempts"] = attempts + 1
        session._write_session(stored)  # type: ignore[attr-defined]

        result = await _one_probe_cycle(key, number, schedule_on_limit=False)
        if result.get("status") == "rate_limited" and attempts + 1 < MAX_AUTOMATIC_PROBES:
            next_delay = max(30, int(result.get("retry_after_seconds") or 30))
    finally:
        session._VERIFY_TASKS.pop(key_id, None)  # type: ignore[attr-defined]
        if next_delay:
            _queue_one_probe(key, number, next_delay)


def _queue_one_probe(key: str, number: int, seconds: int) -> None:
    key_id = pool.fingerprint(key)
    task = session._VERIFY_TASKS.get(key_id)  # type: ignore[attr-defined]
    if task and not task.done():
        return
    try:
        session._VERIFY_TASKS[key_id] = asyncio.create_task(  # type: ignore[attr-defined]
            _one_background_probe(key, number, max(2, int(seconds)))
        )
    except RuntimeError:
        pass


async def single_probe_test_one(key: str, number: int = 1) -> dict[str, Any]:
    if session._verified(key):  # type: ignore[attr-defined]
        session._set_session_active(key)  # type: ignore[attr-defined]
        return session._cached_result(key, number)  # type: ignore[attr-defined]

    task = session._VERIFY_TASKS.get(pool.fingerprint(key))  # type: ignore[attr-defined]
    if task and not task.done():
        record = session._record_for_key(key)  # type: ignore[attr-defined]
        remaining = max(1, int(float(record.get("cooldown_until") or 0) - time.time()))
        return _pending_result(key, number, remaining)
    return await _one_probe_cycle(key, number, schedule_on_limit=True)


def install() -> None:
    # One real production request may verify an enabled key, so candidates are not blocked by a
    # separate preflight request. Cooldown and hard-failure rules still apply.
    session.session_ordered_keys = _candidate_ordered_keys
    cloud.strict_ordered_keys = _candidate_ordered_keys
    pool.ordered_keys = _candidate_ordered_keys
    gemini_routes.ordered_keys = _candidate_ordered_keys
    gemini_rotation_runtime.ordered_keys = _candidate_ordered_keys
    gemini_stability_runtime.stable_ordered_keys = _candidate_ordered_keys
    studio_pro_routes.ordered_keys = _candidate_ordered_keys
    dialogue_ultra_routes._gemini_keys = _candidate_ordered_keys

    session._verify_cycle = _one_probe_cycle
    session._background_verify = _one_background_probe
    session._queue_verify = _queue_one_probe
    session.smart_test_one = single_probe_test_one
    gemini_routes._test_one = single_probe_test_one

    pool.apply_environment(_candidate_ordered_keys(), str(pool.load_config().get("model_id") or "gemini-2.5-flash-preview-tts"))


install()
