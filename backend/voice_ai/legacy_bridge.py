"""Compatibility bridge for the original `/api/audio/clone` implementation."""
from __future__ import annotations

from functools import wraps
from typing import Any, Dict

from backend.core.logger import get_logger

from .audio import safe_resolve_audio

logger = get_logger("voice_ai_legacy_bridge")
_INSTALLED = False


def install_legacy_clone_bridge() -> None:
    """Normalize aliases and protect paths without deleting the original route."""
    global _INSTALLED
    if _INSTALLED:
        return
    from backend.core.tts_engine import tts

    original = tts.clone_voice

    @wraps(original)
    async def guarded_clone_voice(
        reference_audio_path: str,
        text: str,
        engine: str = "xtts",
        language: str = "ar",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        aliases = {
            "coqui": "xtts",
            "coqui-tts": "xtts",
            "coqui_xtts": "xtts",
            "xtts-v2": "xtts",
            "xtts_v2": "xtts",
        }
        normalized = aliases.get((engine or "xtts").strip().lower(), (engine or "xtts").strip().lower())
        try:
            safe_reference = safe_resolve_audio(reference_audio_path)
        except Exception as exc:
            logger.warning("Rejected unsafe legacy clone path: %s", exc)
            return {
                "success": False,
                "engine": normalized,
                "file": None,
                "url": None,
                "message": str(exc),
                "error_code": "INVALID_FILE_PATH",
            }
        return await original(
            reference_audio_path=str(safe_reference),
            text=text,
            engine=normalized,
            language=language,
        )

    tts.clone_voice = guarded_clone_voice  # type: ignore[method-assign]
    _INSTALLED = True
    logger.info("Installed protected legacy voice-clone bridge")
