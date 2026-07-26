"""Microsoft Edge neural TTS plugin with Arabic-first voice defaults."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List

from backend.core.config import OUTPUTS_DIR
from backend.core.logger import get_logger
from backend.plugins.tts_plugin_base import TTSPluginBase

logger = get_logger("plugin_edge")


class EdgeTTSPlugin(TTSPluginBase):
    name = "edge"
    label = "Microsoft Edge Neural TTS"
    description = "High-quality neural speech with Arabic and multilingual voices"
    homepage = "https://github.com/rany2/edge-tts"
    is_open_source = True
    requires_gpu = False

    VOICES = {
        "ar-SA-HamedNeural": {"language": "ar", "gender": "male"},
        "ar-SA-ZariyahNeural": {"language": "ar", "gender": "female"},
        "ar-EG-ShakirNeural": {"language": "ar", "gender": "male"},
        "ar-EG-SalmaNeural": {"language": "ar", "gender": "female"},
        "en-US-GuyNeural": {"language": "en", "gender": "male"},
        "en-US-JennyNeural": {"language": "en", "gender": "female"},
    }
    DEFAULT_BY_LANGUAGE = {
        "ar": "ar-SA-HamedNeural",
        "en": "en-US-GuyNeural",
    }

    def check(self) -> bool:
        try:
            import edge_tts  # noqa: F401
            return True
        except Exception:
            return False

    def install(self) -> Dict[str, Any]:
        import subprocess
        import sys

        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "edge-tts>=7,<8"])
            return {
                "success": self.check(),
                "engine": self.name,
                "message": "edge-tts installed successfully",
            }
        except Exception as exc:
            return {"success": False, "engine": self.name, "message": str(exc)}

    def download_models(self, model_name: str = "default") -> Dict[str, Any]:
        return {
            "success": self.check(),
            "model": "cloud-neural",
            "message": "Edge voices are streamed and require no model download.",
        }

    def list_models(self) -> List[Dict[str, Any]]:
        return [{
            "name": "cloud-neural",
            "language": "multi",
            "downloaded": self.check(),
        }]

    def list_voices(self) -> List[Dict[str, str]]:
        return [
            {"name": name, **metadata}
            for name, metadata in self.VOICES.items()
        ]

    async def generate(
        self,
        text: str,
        voice: str = "default",
        language: str = "ar",
        speed: float = 1.0,
    ) -> Dict[str, Any]:
        if not self.check():
            return {"success": False, "engine": self.name, "message": "edge-tts is not installed."}
        text = (text or "").strip()
        if not text:
            return {"success": False, "engine": self.name, "message": "Text is empty."}
        if len(text) > 5000:
            return {"success": False, "engine": self.name, "message": "Text exceeds 5000 characters."}
        if not 0.5 <= speed <= 2.0:
            return {"success": False, "engine": self.name, "message": "Speed must be between 0.5 and 2.0."}

        import edge_tts

        selected_voice = self.DEFAULT_BY_LANGUAGE.get(language, "ar-SA-HamedNeural") if voice in {"", "default", None} else voice
        rate = round((speed - 1.0) * 100)
        digest = hashlib.sha256(f"{selected_voice}|{speed}|{text}".encode("utf-8")).hexdigest()[:16]
        filepath = OUTPUTS_DIR / f"edge_{digest}.mp3"
        try:
            if not filepath.exists():
                communication = edge_tts.Communicate(
                    text=text,
                    voice=selected_voice,
                    rate=f"{rate:+d}%",
                )
                await communication.save(str(filepath))
            return {
                "success": True,
                "engine": self.name,
                "file": str(filepath),
                "url": f"/api/downloads/{filepath.name}",
                "message": f"Generated professional neural speech ({selected_voice}).",
            }
        except Exception as exc:
            logger.exception("Edge TTS generation failed")
            return {"success": False, "engine": self.name, "message": str(exc)}


PLUGIN_CLASS = EdgeTTSPlugin
PLUGIN_NAME = "Microsoft Edge Neural TTS"
PLUGIN_DESCRIPTION = "High-quality Arabic and multilingual neural speech"
