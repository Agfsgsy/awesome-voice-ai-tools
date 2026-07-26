"""Apply the persistent Gemini key pool to every Gemini audio path.

This is additive and loaded after the existing plugins/routes. It prevents stale environment
keys and records the key that actually succeeds so the next request starts with another key.
"""
from __future__ import annotations

import os

from fastapi import HTTPException

from backend.api import dialogue_ultra_routes as dialogue
from backend.core.gemini_key_pool import ordered_keys, record_result
from backend.plugins import gemini_tts_plugin


_original_generate = gemini_tts_plugin.GeminiTTSPlugin.generate


async def _generate_with_live_pool(self, *args, **kwargs):
    keys = ordered_keys()
    previous_many = os.environ.get("GEMINI_API_KEYS")
    previous_one = os.environ.get("GEMINI_API_KEY")
    if keys:
        os.environ["GEMINI_API_KEYS"] = "||".join(keys)
        os.environ["GEMINI_API_KEY"] = keys[0]
    try:
        result = await _original_generate(self, *args, **kwargs)
    finally:
        if previous_many is None:
            os.environ.pop("GEMINI_API_KEYS", None)
        else:
            os.environ["GEMINI_API_KEYS"] = previous_many
        if previous_one is None:
            os.environ.pop("GEMINI_API_KEY", None)
        else:
            os.environ["GEMINI_API_KEY"] = previous_one
    if result and result.get("success") and keys:
        number = int(result.get("key_used", 1) or 1)
        if 1 <= number <= len(keys):
            record_result(keys[number - 1], "working", str(result.get("model", "")))
    elif result and result.get("all_keys_exhausted"):
        for key in keys:
            record_result(key, "quota", "TTS returned 429")
    return result


gemini_tts_plugin.GeminiTTSPlugin.generate = _generate_with_live_pool


_original_scene_audio = dialogue._gemini_scene_audio


async def _scene_audio_with_live_pool(turns, tone, dialect, preferred_model):
    keys = ordered_keys()
    original_loader = dialogue._gemini_keys
    dialogue._gemini_keys = ordered_keys
    try:
        pcm, model, key_index = await _original_scene_audio(turns, tone, dialect, preferred_model)
        if keys and 1 <= int(key_index) <= len(keys):
            record_result(keys[int(key_index) - 1], "working", str(model))
        return pcm, model, key_index
    except HTTPException as exc:
        detail = str(exc.detail)
        if "429" in detail or "quota" in detail.lower() or "حصة" in detail:
            for key in keys:
                record_result(key, "quota", detail)
        raise
    finally:
        dialogue._gemini_keys = original_loader


dialogue._gemini_keys = ordered_keys
dialogue._gemini_scene_audio = _scene_audio_with_live_pool
