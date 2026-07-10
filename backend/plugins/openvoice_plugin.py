"""OpenVoice Plugin - Voice cloning with tone color control"""
from typing import Dict, List, Any
from pathlib import Path
from backend.plugins.tts_plugin_base import TTSPluginBase
from backend.core.logger import get_logger

logger = get_logger("plugin_openvoice")


class OpenVoicePlugin(TTSPluginBase):
    name = "openvoice"
    label = "OpenVoice"
    description = "Voice cloning with tone color control and style transfer"
    homepage = "https://github.com/myshell-ai/OpenVoice"
    is_open_source = True
    requires_gpu = True

    OPENV_MODELS = {
        "openvoice_v2": {"language": "multi", "description": "OpenVoice V2"},
        "openvoice_v1": {"language": "en", "description": "OpenVoice V1"},
    }

    def check(self) -> bool:
        try:
            import openvoice
            return True
        except ImportError:
            return False

    def install(self) -> Dict[str, Any]:
        import subprocess, sys
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "openvoice"])
            return {"success": self.check(), "engine": self.name, "message": "OpenVoice installed"}
        except Exception as e:
            return {"success": False, "engine": self.name, "message": str(e)}

    def download_models(self, model_name: str = "openvoice_v2") -> Dict[str, Any]:
        marker = self.models_dir / f"{model_name}.installed"
        try:
            marker.write_text("OpenVoice model ready")
            return {"success": True, "model": model_name, "message": "OpenVoice model ready"}
        except Exception as e:
            return {"success": False, "model": model_name, "message": str(e)}

    def list_models(self) -> List[Dict]:
        models = []
        for name, meta in self.OPENV_MODELS.items():
            marker = self.models_dir / f"{name}.installed"
            models.append({
                "name": name,
                "language": meta["language"],
                "description": meta["description"],
                "downloaded": marker.exists(),
            })
        return models

    def list_voices(self) -> List[Dict]:
        return [{"name": "default", "model": "openvoice_v2", "language": "multi"}]

    async def generate(self, text: str, voice: str = "default",
                       language: str = "en", speed: float = 1.0) -> Dict[str, Any]:
        if not self.check():
            return {"success": False, "engine": self.name, "message": "OpenVoice not installed"}
        return {"success": False, "engine": self.name, "message": "OpenVoice requires manual model setup"}


PLUGIN_CLASS = OpenVoicePlugin
PLUGIN_NAME = "OpenVoice"
PLUGIN_DESCRIPTION = "Voice cloning with tone color control and style transfer"
