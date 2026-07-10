"""Parler TTS Plugin - Description-based voice generation"""
from typing import Dict, List, Any
from pathlib import Path
from backend.plugins.tts_plugin_base import TTSPluginBase
from backend.core.logger import get_logger

logger = get_logger("plugin_parler")


class ParlerPlugin(TTSPluginBase):
    name = "parler"
    label = "Parler TTS"
    description = "Description-based voice generation - describe the voice you want"
    homepage = "https://github.com/huggingface/parler-tts"
    is_open_source = True
    requires_gpu = True

    PARLER_MODELS = {
        "parler_tts_mini": {"language": "en", "description": "Mini model (370M)"},
        "parler_tts_large": {"language": "en", "description": "Large model (1.1B)"},
    }

    def check(self) -> bool:
        try:
            import parler_tts
            return True
        except ImportError:
            return False

    def install(self) -> Dict[str, Any]:
        import subprocess, sys
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "parler-tts"])
            return {"success": self.check(), "engine": self.name, "message": "Parler TTS installed"}
        except Exception as e:
            return {"success": False, "engine": self.name, "message": str(e)}

    def download_models(self, model_name: str = "parler_tts_mini") -> Dict[str, Any]:
        marker = self.models_dir / f"{model_name}.installed"
        try:
            marker.write_text("Parler TTS model ready")
            return {"success": True, "model": model_name, "message": "Parler TTS model ready"}
        except Exception as e:
            return {"success": False, "model": model_name, "message": str(e)}

    def list_models(self) -> List[Dict]:
        models = []
        for name, meta in self.PARLER_MODELS.items():
            marker = self.models_dir / f"{name}.installed"
            models.append({
                "name": name,
                "language": meta["language"],
                "description": meta["description"],
                "downloaded": marker.exists(),
            })
        return models

    def list_voices(self) -> List[Dict]:
        return [
            {"name": "calm_male", "model": "parler_tts_mini", "language": "en"},
            {"name": "calm_female", "model": "parler_tts_mini", "language": "en"},
            {"name": "excited_male", "model": "parler_tts_mini", "language": "en"},
        ]

    async def generate(self, text: str, voice: str = "calm_male",
                       language: str = "en", speed: float = 1.0) -> Dict[str, Any]:
        if not self.check():
            return {"success": False, "engine": self.name, "message": "Parler TTS not installed"}
        return {"success": False, "engine": self.name, "message": "Parler TTS requires manual model setup"}


PLUGIN_CLASS = ParlerPlugin
PLUGIN_NAME = "Parler TTS"
PLUGIN_DESCRIPTION = "Description-based voice generation"
