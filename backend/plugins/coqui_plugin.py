"""Coqui TTS Plugin - Open Source multilingual TTS"""
from typing import Dict, List, Any
from pathlib import Path
from backend.plugins.tts_plugin_base import TTSPluginBase
from backend.core.logger import get_logger

logger = get_logger("plugin_coqui")


class CoquiPlugin(TTSPluginBase):
    name = "coqui"
    label = "Coqui TTS"
    description = "Multilingual TTS with XTTS-v2 voice cloning"
    homepage = "https://github.com/coqui-ai/TTS"
    is_open_source = True
    requires_gpu = False

    COQUI_MODELS = {
        "xtts_v2": {
            "model_name": "tts_models/multilingual/multi-dataset/xtts_v2",
            "languages": ["ar", "en", "fr", "de", "es", "it", "pt", "pl", "tr", "ru", "nl", "cs", "ar", "zh-cn", "hu", "ko", "ja", "hi"],
            "supports_cloning": True,
        },
        "glow_tts": {
            "model_name": "tts_models/en/ljspeech/glow-tts",
            "languages": ["en"],
            "supports_cloning": False,
        },
    }

    def check(self) -> bool:
        try:
            from TTS.api import TTS
            return True
        except ImportError:
            return False
        except Exception:
            return False

    def install(self) -> Dict[str, Any]:
        import subprocess, sys
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "TTS"])
            installed = self.check()
            return {"success": installed, "engine": self.name, "message": "Installed TTS" if installed else "Install failed"}
        except Exception as e:
            return {"success": False, "engine": self.name, "message": str(e)}

    def download_models(self, model_name: str = "xtts_v2") -> Dict[str, Any]:
        if model_name not in self.COQUI_MODELS:
            return {"success": False, "message": f"Unknown model: {model_name}"}
        if not self.check():
            return {"success": False, "message": "TTS not installed. Run install() first."}
        try:
            from TTS.api import TTS as CoquiTTS
            meta = self.COQUI_MODELS[model_name]
            model = CoquiTTS(model_name=meta["model_name"])
            # Model auto-downloaded on first use
            marker = self.models_dir / f"{model_name}.installed"
            marker.write_text("installed")
            return {"success": True, "model": model_name, "message": f"Model {meta['model_name']} downloaded"}
        except Exception as e:
            return {"success": False, "model": model_name, "message": str(e)}

    def list_models(self) -> List[Dict]:
        models = []
        for name, meta in self.COQUI_MODELS.items():
            marker = self.models_dir / f"{name}.installed"
            models.append({
                "name": name,
                "model_name": meta["model_name"],
                "languages": meta["languages"],
                "supports_cloning": meta["supports_cloning"],
                "downloaded": marker.exists(),
            })
        return models

    def list_voices(self) -> List[Dict]:
        return [
            {"name": "default", "model": "xtts_v2", "language": "ar"},
            {"name": "default", "model": "glow_tts", "language": "en"},
        ]

    async def generate(self, text: str, voice: str = "default",
                       language: str = "ar", speed: float = 1.0) -> Dict[str, Any]:
        if not self.check():
            return {"success": False, "engine": self.name, "message": "Coqui TTS not installed. Run install()."}
        try:
            from TTS.api import TTS as CoquiTTS
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model = CoquiTTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2", device=device)
            filepath = self._save_wav(None, text, 24000)
            model.tts_to_file(text=text, language=language, file_path=str(filepath))
            return {
                "success": True,
                "engine": self.name,
                "file": str(filepath),
                "url": f"/api/downloads/{filepath.name}",
                "message": f"Generated with Coqui XTTS-v2 ({language})",
            }
        except Exception as e:
            logger.error(f"Coqui generate failed: {e}")
            return {"success": False, "engine": self.name, "message": str(e)}


PLUGIN_CLASS = CoquiPlugin
PLUGIN_NAME = "Coqui TTS"
PLUGIN_DESCRIPTION = "Multilingual TTS with XTTS-v2 voice cloning"
