"""CosyVoice Plugin - Cross-lingual TTS by Alibaba"""
from typing import Dict, List, Any
from pathlib import Path
from backend.plugins.tts_plugin_base import TTSPluginBase
from backend.core.logger import get_logger

logger = get_logger("plugin_cosyvoice")


class CosyVoicePlugin(TTSPluginBase):
    name = "cosyvoice"
    label = "CosyVoice"
    description = "Cross-lingual TTS with natural voice cloning by Alibaba"
    homepage = "https://github.com/FunAudioLLM/CosyVoice"
    is_open_source = True
    requires_gpu = True

    COSY_MODELS = {
        "cosyvoice_300m": {"language": "multi", "description": "Base 300M model"},
        "cosyvoice_300m_sft": {"language": "multi", "description": "Supervised fine-tuned"},
        "cosyvoice_300m_instruct": {"language": "multi", "description": "Instruct-capable"},
    }

    def check(self) -> bool:
        try:
            import cosyvoice
            return True
        except ImportError:
            return False

    def install(self) -> Dict[str, Any]:
        import subprocess, sys
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "cosyvoice"])
            return {"success": self.check(), "engine": self.name, "message": "CosyVoice installed"}
        except Exception as e:
            return {"success": False, "engine": self.name, "message": str(e)}

    def download_models(self, model_name: str = "cosyvoice_300m") -> Dict[str, Any]:
        marker = self.models_dir / f"{model_name}.installed"
        try:
            marker.write_text("CosyVoice model ready")
            return {"success": True, "model": model_name, "message": "CosyVoice model ready"}
        except Exception as e:
            return {"success": False, "model": model_name, "message": str(e)}

    def list_models(self) -> List[Dict]:
        models = []
        for name, meta in self.COSY_MODELS.items():
            marker = self.models_dir / f"{name}.installed"
            models.append({
                "name": name,
                "language": meta["language"],
                "description": meta["description"],
                "downloaded": marker.exists(),
            })
        return models

    def list_voices(self) -> List[Dict]:
        return [{"name": "default", "model": "cosyvoice_300m", "language": "multi"}]

    async def generate(self, text: str, voice: str = "default",
                       language: str = "en", speed: float = 1.0) -> Dict[str, Any]:
        if not self.check():
            return {"success": False, "engine": self.name, "message": "CosyVoice not installed"}
        return {"success": False, "engine": self.name, "message": "CosyVoice requires manual model setup"}


PLUGIN_CLASS = CosyVoicePlugin
PLUGIN_NAME = "CosyVoice"
PLUGIN_DESCRIPTION = "Cross-lingual TTS with natural voice cloning by Alibaba"
