"""Understand Gemini temporary rate windows and wait for the advertised retry delay.

This additive runtime keeps working keys connected. A 429 with a short retry delay is treated
as a per-minute/window limit, not as exhausted daily quota. Tests and audio generation wait and
retry the same key before rotation.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx

from backend.api import gemini_routes, gemini_stability_runtime
from backend.core import gemini_key_pool as pool
from backend.plugins import gemini_tts_plugin

_original_test_one = gemini_routes._test_one
_original_stability_delay = gemini_stability_runtime._delay
_original_plugin_delay = gemini_tts_plugin.GeminiTTSPlugin._retry_delay


def _seconds_from_text(value: str) -> float | None:
    text = str(value or "")
    patterns = (
        r"retry\s+in\s+([0-9]+(?:\.[0-9]+)?)\s*s",
        r"retryDelay[^0-9]*([0-9]+(?:\.[0-9]+)?)\s*s",
        r"retry-after[^0-9]*([0-9]+(?:\.[0-9]+)?)",
        r"أعد\s+المحاولة[^0-9]*([0-9]+(?:\.[0-9]+)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            try:
                return max(1.0, min(120.0, float(match.group(1))))
            except Exception:
                pass
    return None


def retry_seconds(response: httpx.Response | None = None, detail: str = "", attempt: int = 1) -> float:
    if response is not None:
        header = str(response.headers.get("retry-after", "")).strip()
        try:
            if header:
                return max(1.0, min(120.0, float(header)))
        except Exception:
            pass
        try:
            payload: Any = response.json()
            if isinstance(payload, dict):
                error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
                for item in error.get("details") or []:
                    if not isinstance(item, dict):
                        continue
                    raw = item.get("retryDelay") or item.get("retry_delay")
                    parsed = _seconds_from_text(str(raw or ""))
                    if parsed is not None:
                        return parsed
                detail = str(error.get("message") or payload.get("message") or detail)
        except Exception:
            if not detail:
                try:
                    detail = response.text
                except Exception:
                    pass
    parsed = _seconds_from_text(detail)
    if parsed is not None:
        return parsed
    return min(30.0, float(_original_stability_delay(response, attempt)))


def _smart_stability_delay(response: httpx.Response | None, attempt: int) -> float:
    return retry_seconds(response=response, attempt=attempt)


def _smart_plugin_delay(response: httpx.Response, attempt: int) -> float:
    return retry_seconds(response=response, attempt=attempt)


async def _test_one_with_retry_window(key: str, number: int = 1) -> dict:
    result = await _original_test_one(key, number)
    waits: list[int] = []
    for _ in range(2):
        if str(result.get("status") or "") not in {"quota", "rate_limited"}:
            break
        detail = str(result.get("detail") or "")
        wait = retry_seconds(detail=detail)
        # A short advertised delay means RPM/window throttling, not daily exhaustion.
        if wait > 120:
            break
        seconds = int(max(2, min(120, round(wait + 1))))
        waits.append(seconds)
        gemini_stability_runtime.stable_record_result(
            key,
            "rate_limited",
            detail,
            seconds,
        )
        await asyncio.sleep(seconds)
        result = await _original_test_one(key, number)
    if str(result.get("status") or "") in {"quota", "rate_limited"}:
        detail = str(result.get("detail") or "")
        next_wait = int(max(2, min(120, round(retry_seconds(detail=detail) + 1))))
        result["status"] = "rate_limited"
        result["temporary"] = True
        result["retry_after_seconds"] = next_wait
        result["detail"] = (
            f"حد طلبات مؤقت، وليس انتهاء الحصة. أبقينا المفتاح متصلًا. "
            f"أعد المحاولة بعد نحو {next_wait} ثانية."
        )
        gemini_stability_runtime.stable_record_result(key, "rate_limited", detail, next_wait)
    elif result.get("ok") and waits:
        result["detail"] = f"انتظر البرنامج تلقائيًا {sum(waits)} ثانية ثم نجح اختبار النص والصوت."
    return result


def install() -> None:
    gemini_stability_runtime._delay = _smart_stability_delay
    gemini_tts_plugin.GeminiTTSPlugin._retry_delay = staticmethod(_smart_plugin_delay)
    gemini_routes._test_one = _test_one_with_retry_window
    # Temporary limits must never block or disconnect a saved key.
    pool.BLOCKED = {"invalid", "forbidden"}


install()
