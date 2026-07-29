"""Register restricted Google Cloud custom voice only when configured."""
from __future__ import annotations

from .engines import ENGINE_DEFINITIONS, HttpRuntimeEngine, voice_engine_registry


def register_google_custom_voice() -> None:
    """Expose Google Custom Voice as an optional runtime, never as free Gemini cloning."""
    name = "google_custom_voice"
    if name not in voice_engine_registry.engines:
        voice_engine_registry.engines[name] = HttpRuntimeEngine(ENGINE_DEFINITIONS[name])
