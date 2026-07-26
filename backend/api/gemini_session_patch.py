"""Final synchronization patch for the persistent Gemini session runtime."""
from __future__ import annotations

import asyncio
import time

from backend.api import (
    dialogue_ultra_routes,
    gemini_cloud_control_runtime as cloud,
    gemini_rotation_runtime,
    gemini_routes,
    gemini_session_runtime as session,
    gemini_stability_runtime,
    studio_pro_routes,
)
from backend.core import gemini_key_pool as pool
from backend.plugins.gemini_tts_plugin import GeminiTTSPlugin

_BASE_ORDER = session.session_ordered_keys
_BASE_GENERATE = session.smart_generate


def synchronized_ordered_keys() -> list[str]:
    keys = list(_BASE_ORDER())
    if not keys:
        return []
    first = keys[0]
    first_id = pool.fingerprint(first)
    current = str(session._read_session().get("active_fp") or "")  # type: ignore[attr-defined]
    if first_id != current:
        session._set_session_active(first)  # type: ignore[attr-defined]
    return keys


async def generate_with_cooldown_wait(self, text: str, voice: str = "default", language: str = "ar", speed: float = 1.0):
    keys = synchronized_ordered_keys()
    if len(keys) == 1:
        state = session._read_session()  # type: ignore[attr-defined]
        item = session._session_key(state, pool.fingerprint(keys[0]))  # type: ignore[attr-defined]
        remaining = float(item.get("cooldown_until") or 0) - time.time()
        if remaining > 0:
            await asyncio.sleep(min(300.0, remaining))
    return await _BASE_GENERATE(self, text=text, voice=voice, language=language, speed=speed)


def install() -> None:
    session.session_ordered_keys = synchronized_ordered_keys
    cloud.strict_ordered_keys = synchronized_ordered_keys
    pool.ordered_keys = synchronized_ordered_keys
    gemini_routes.ordered_keys = synchronized_ordered_keys
    gemini_rotation_runtime.ordered_keys = synchronized_ordered_keys
    gemini_stability_runtime.stable_ordered_keys = synchronized_ordered_keys
    studio_pro_routes.ordered_keys = synchronized_ordered_keys
    dialogue_ultra_routes._gemini_keys = synchronized_ordered_keys
    GeminiTTSPlugin.generate = generate_with_cooldown_wait
    pool.apply_environment(synchronized_ordered_keys(), str(pool.load_config().get("model_id") or "gemini-2.5-flash-preview-tts"))


install()
