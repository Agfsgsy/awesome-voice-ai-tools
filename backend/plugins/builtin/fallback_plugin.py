from typing import Dict, List, Any
from backend.plugins.tts_plugin_base import TTSPluginBase
from backend.core.logger import get_logger

logger = get_logger("plugin_fallback")

class FallbackPlugin(TTSPluginBase):
    name = "fallback"
    label = "Fallback TTS"
    description = "A basic fallback engine using Google Translate TTS"
    homepage = "https://pypi.org/project/gTTS/"
    is_open_source = True
    requires_gpu = False

    def check(self) -> bool:
        try:
            import gtts
            return True
        except ImportError:
            return False

    def install(self) -> Dict[str, Any]:
        import subprocess, sys
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "gtts"])
            installed = self.check()
            return {"success": installed, "engine": self.name, "message": "Installed gTTS" if installed else "Install failed"}
        except Exception as e:
            return {"success": False, "engine": self.name, "message": str(e)}

    def download_models(self, model_name: str = "default") -> Dict[str, Any]:
        return {"success": True, "model": model_name, "message": "No download required for fallback"}

    def list_models(self) -> List[Dict]:
        return [{"name": "default", "downloaded": True}]

    def list_voices(self) -> List[Dict]:
        return [{"name": "default", "model": "default", "language": "ar"}]

    async def generate(self, text: str, voice: str = "default",
                       language: str = "ar", speed: float = 1.0) -> Dict[str, Any]:
        if not self.check():
            res = self.install()
            if not res.get("success"):
                return {"success": False, "engine": self.name, "message": "gTTS not installed and failed to install."}
        try:
            from gtts import gTTS
            tts = gTTS(text=text, lang=language.split("-")[0])
            import hashlib
            from backend.core.config import OUTPUTS_DIR
            name_hash = hashlib.md5(text.encode()).hexdigest()[:8]
            out_name = f"{self.name}_{name_hash}.mp3"
            filepath = OUTPUTS_DIR / out_name
            tts.save(str(filepath))

            return {
                "success": True,
                "engine": self.name,
                "file": str(filepath),
                "url": f"/api/downloads/{filepath.name}",
                "message": f"Generated with Fallback ({language})",
            }
        except Exception as e:
            logger.error(f"Fallback generate failed: {e}")
            return {"success": False, "engine": self.name, "message": str(e)}

PLUGIN_CLASS = FallbackPlugin
PLUGIN_NAME = "Fallback TTS"
PLUGIN_DESCRIPTION = "Basic fallback engine"
