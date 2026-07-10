"""Kokoro TTS Plugin - Open Source lightweight TTS"""
from typing import Dict, List, Any
from pathlib import Path
from backend.plugins.tts_plugin_base import TTSPluginBase
from backend.core.logger import get_logger

logger = get_logger("plugin_kokoro")


class KokoroPlugin(TTSPluginBase):
    name = "kokoro"
    label = "Kokoro TTS"
    description = "Lightweight TTS with good quality, works on CPU"
    homepage = "https://github.com/hexgrad/kokoro"
    is_open_source = True
    requires_gpu = False

    KOKORO_VOICES = {
        "af": {"language": "en", "gender": "female"},
        "am": {"language": "en", "gender": "male"},
        "bf": {"language": "en", "gender": "female"},
        "bm": {"language": "en", "gender": "male"},
        "ar": {"language": "ar", "gender": "female"},
    }

    def check(self) -> bool:
        try:
            import kokoro
            return True
        except ImportError:
            return False
        except Exception:
            return False

    def install(self) -> Dict[str, Any]:
        import subprocess, sys
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "kokoro"])
            installed = self.check()
            return {"success": installed, "engine": self.name, "message": "Installed kokoro" if installed else "Install failed"}
        except Exception as e:
            return {"success": False, "engine": self.name, "message": str(e)}

    def download_models(self, model_name: str = "default") -> Dict[str, Any]:
        if not self.check():
            return {"success": False, "message": "kokoro not installed. Run install() first."}
        try:
            from kokoro import Kokoro
            model = Kokoro()
            marker = self.models_dir / "default.installed"
            marker.write_text("kokoro model auto-downloaded on first use")
            return {"success": True, "model": "default", "message": "Kokoro model ready (auto-downloads on first generate())"}
        except Exception as e:
            return {"success": False, "model": model_name, "message": str(e)}

    def list_models(self) -> List[Dict]:
        installed_marker = self.models_dir / "default.installed"
        return [{
            "name": "default",
            "language": "multi",
            "downloaded": self.check() or installed_marker.exists(),
        }]

    def list_voices(self) -> List[Dict]:
        voices = []
        for name, meta in self.KOKORO_VOICES.items():
            voices.append({
                "name": name,
                "language": meta["language"],
                "gender": meta["gender"],
            })
        return voices

    async def generate(self, text: str, voice: str = "af",
                       language: str = "ar", speed: float = 1.0) -> Dict[str, Any]:
        if not self.check():
            return {"success": False, "engine": self.name, "message": "Kokoro not installed. Run install()."}
        try:
            from kokoro import Kokoro
            model = Kokoro()
            audio = model.create(text, voice=voice, speed=speed)
            filepath = self._save_wav(audio, text, 24000)
            return {
                "success": True,
                "engine": self.name,
                "file": str(filepath),
                "url": f"/api/downloads/{filepath.name}",
                "message": f"Generated with Kokoro (voice={voice})",
            }
        except Exception as e:
            logger.error(f"Kokoro generate failed: {e}")
            return {"success": False, "engine": self.name, "message": str(e)}


PLUGIN_CLASS = KokoroPlugin
PLUGIN_NAME = "Kokoro TTS"
PLUGIN_DESCRIPTION = "Lightweight TTS with good quality, works on CPU"
