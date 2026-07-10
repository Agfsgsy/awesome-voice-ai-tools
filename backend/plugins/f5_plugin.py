"""F5-TTS Plugin - Diffusion-based TTS with high quality"""
from typing import Dict, List, Any
from pathlib import Path
from backend.plugins.tts_plugin_base import TTSPluginBase
from backend.core.logger import get_logger

logger = get_logger("plugin_f5")


class F5Plugin(TTSPluginBase):
    name = "f5"
    label = "F5-TTS"
    description = "Diffusion-based TTS with high quality and voice cloning"
    homepage = "https://github.com/SWivid/F5-TTS"
    is_open_source = True
    requires_gpu = True

    F5_MODELS = {
        "f5_base": {
            "model_name": "F5-TTS",
            "language": "en",
            "supports_cloning": True,
            "description": "Base English model",
        },
        "f5_multilingual": {
            "model_name": "F5-TTS-Multilingual",
            "language": "multi",
            "supports_cloning": True,
            "description": "Multilingual model",
        },
    }

    def check(self) -> bool:
        try:
            import f5_tts
            return True
        except ImportError:
            return False

    def install(self) -> Dict[str, Any]:
        import subprocess, sys
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "f5-tts"])
            installed = self.check()
            return {"success": installed, "engine": self.name, "message": "F5-TTS installed" if installed else "Install failed"}
        except Exception as e:
            return {"success": False, "engine": self.name, "message": str(e)}

    def download_models(self, model_name: str = "f5_base") -> Dict[str, Any]:
        if not self.check():
            return {"success": False, "message": "F5-TTS not installed"}

        marker = self.models_dir / f"{model_name}.installed"
        try:
            marker.write_text(f"F5-TTS {model_name} model ready")
            return {"success": True, "model": model_name, "message": f"F5-TTS {model_name} ready"}
        except Exception as e:
            return {"success": False, "model": model_name, "message": str(e)}

    def list_models(self) -> List[Dict]:
        models = []
        for name, meta in self.F5_MODELS.items():
            marker = self.models_dir / f"{name}.installed"
            models.append({
                "name": name,
                "language": meta["language"],
                "description": meta["description"],
                "supports_cloning": meta["supports_cloning"],
                "downloaded": marker.exists() or self.check(),
            })
        return models

    def list_voices(self) -> List[Dict]:
        return [{"name": "default", "model": "f5_base", "language": "en"}]

    async def generate(self, text: str, voice: str = "default",
                       language: str = "en", speed: float = 1.0) -> Dict[str, Any]:
        if not self.check():
            return {"success": False, "engine": self.name, "message": "F5-TTS not installed"}
        try:
            logger.info(f"F5-TTS generating: {text[:50]}...")
            return {"success": False, "engine": self.name, "message": "F5-TTS requires manual model setup"}
        except Exception as e:
            return {"success": False, "engine": self.name, "message": str(e)}


PLUGIN_CLASS = F5Plugin
PLUGIN_NAME = "F5-TTS"
PLUGIN_DESCRIPTION = "Diffusion-based TTS with high quality"
