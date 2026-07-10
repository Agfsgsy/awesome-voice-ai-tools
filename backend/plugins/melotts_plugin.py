"""MeloTTS Plugin - Open Source multilingual TTS by MyShell"""
from typing import Dict, List, Any
from pathlib import Path
from backend.plugins.tts_plugin_base import TTSPluginBase
from backend.core.logger import get_logger

logger = get_logger("plugin_melotts")


class MeloTTSPlugin(TTSPluginBase):
    name = "melotts"
    label = "MeloTTS"
    description = "Multilingual TTS with Arabic support, fast on CPU"
    homepage = "https://github.com/myshell-ai/MeloTTS"
    is_open_source = True
    requires_gpu = False

    MELO_LANGUAGES = {
        "ar": {"name": "Arabic", "available": True},
        "en": {"name": "English", "available": True},
        "zh": {"name": "Chinese", "available": True},
        "fr": {"name": "French", "available": True},
        "ja": {"name": "Japanese", "available": True},
        "kr": {"name": "Korean", "available": True},
    }

    def check(self) -> bool:
        try:
            from melotts import TTS as MeloTTS_api
            return True
        except ImportError:
            try:
                import melo
                from melo.api import TTS as MeloAPI
                return True
            except ImportError:
                return False
        except Exception:
            return False

    def install(self) -> Dict[str, Any]:
        import subprocess, sys
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "git+https://github.com/myshell-ai/MeloTTS.git"])
            installed = self.check()
            return {"success": installed, "engine": self.name, "message": "Installed MeloTTS" if installed else "Install failed"}
        except Exception as e:
            return {"success": False, "engine": self.name, "message": str(e)}

    def download_models(self, model_name: str = "default") -> Dict[str, Any]:
        if not self.check():
            return {"success": False, "message": "MeloTTS not installed. Run install() first."}
        try:
            from melo.api import TTS as MeloAPI
            model = MeloAPI(language="AR", device="cpu")
            marker = self.models_dir / "arabic.installed"
            marker.write_text("MeloTTS Arabic model ready")
            return {"success": True, "model": "arabic", "message": "MeloTTS Arabic model ready (auto-downloads on init)"}
        except Exception as e:
            return {"success": False, "model": model_name, "message": str(e)}

    def list_models(self) -> List[Dict]:
        marker = self.models_dir / "arabic.installed"
        models = []
        for lang_code, lang_meta in self.MELO_LANGUAGES.items():
            models.append({
                "name": f"melo_{lang_code}",
                "language": lang_code,
                "language_name": lang_meta["name"],
                "downloaded": marker.exists() if lang_code == "ar" else False,
            })
        return models

    def list_voices(self) -> List[Dict]:
        return [
            {"name": "AR-Default", "model": "melo_ar", "language": "ar"},
            {"name": "EN-Default", "model": "melo_en", "language": "en"},
            {"name": "EN-BR", "model": "melo_en", "language": "en"},
            {"name": "EN-UD", "model": "melo_en", "language": "en"},
        ]

    async def generate(self, text: str, voice: str = "AR-Default",
                       language: str = "ar", speed: float = 1.0) -> Dict[str, Any]:
        if not self.check():
            return {"success": False, "engine": self.name, "message": "MeloTTS not installed. Run install()."}
        try:
            from melo.api import TTS as MeloAPI
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"

            melo_lang = "AR" if language == "ar" else "EN"
            model = MeloAPI(language=melo_lang, device=device)
            speaker_ids = model.hps.data.spk2id

            filepath = self._save_wav(None, text, 44100)
            speaker_id = speaker_ids.get(voice, list(speaker_ids.values())[0])
            audio = model.tts_to_file(text, speaker_id, output_path=str(filepath), speed=speed)
            return {
                "success": True,
                "engine": self.name,
                "file": str(filepath),
                "url": f"/api/downloads/{filepath.name}",
                "message": f"Generated with MeloTTS ({language})",
            }
        except Exception as e:
            logger.error(f"MeloTTS generate failed: {e}")
            return {"success": False, "engine": self.name, "message": str(e)}


PLUGIN_CLASS = MeloTTSPlugin
PLUGIN_NAME = "MeloTTS"
PLUGIN_DESCRIPTION = "Multilingual TTS with Arabic support, fast on CPU"
