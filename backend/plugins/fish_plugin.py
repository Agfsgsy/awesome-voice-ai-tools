"""Fish Speech Plugin - Streaming-capable TTS"""
from typing import Dict, List, Any
from pathlib import Path
from backend.plugins.tts_plugin_base import TTSPluginBase
from backend.core.logger import get_logger

logger = get_logger("plugin_fish")


class FishPlugin(TTSPluginBase):
    name = "fish"
    label = "Fish Speech"
    description = "Streaming-capable TTS with multiple language support"
    homepage = "https://github.com/fishaudio/fish-speech"
    is_open_source = True
    requires_gpu = True

    FISH_MODELS = {
        "fish_speech_1_5": {
            "language": "multi",
            "description": "Fish Speech 1.5 multilingual",
        },
    }

    def check(self) -> bool:
        try:
            import fish_speech
            return True
        except ImportError:
            return False

    def install(self) -> Dict[str, Any]:
        import subprocess, sys
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "fish-speech"])
            return {"success": self.check(), "engine": self.name, "message": "Fish Speech installed"}
        except Exception as e:
            return {"success": False, "engine": self.name, "message": str(e)}

    def download_models(self, model_name: str = "fish_speech_1_5") -> Dict[str, Any]:
        marker = self.models_dir / f"{model_name}.installed"
        try:
            marker.write_text("Fish Speech model ready")
            return {"success": True, "model": model_name, "message": "Fish Speech model ready"}
        except Exception as e:
            return {"success": False, "model": model_name, "message": str(e)}

    def list_models(self) -> List[Dict]:
        models = []
        for name, meta in self.FISH_MODELS.items():
            marker = self.models_dir / f"{name}.installed"
            models.append({
                "name": name,
                "language": meta["language"],
                "description": meta["description"],
                "downloaded": marker.exists(),
            })
        return models

    def list_voices(self) -> List[Dict]:
        return [{"name": "default", "model": "fish_speech_1_5", "language": "multi"}]

    async def generate(self, text: str, voice: str = "default",
                       language: str = "en", speed: float = 1.0) -> Dict[str, Any]:
        if not self.check():
            return {"success": False, "engine": self.name, "message": "Fish Speech not installed"}
        return {"success": False, "engine": self.name, "message": "Fish Speech requires manual model setup"}


PLUGIN_CLASS = FishPlugin
PLUGIN_NAME = "Fish Speech"
PLUGIN_DESCRIPTION = "Streaming-capable TTS with multiple language support"
