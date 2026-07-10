"""Piper TTS Plugin - Open Source neural TTS"""
from typing import Dict, List, Any
from pathlib import Path
from backend.plugins.tts_plugin_base import TTSPluginBase
from backend.core.logger import get_logger

logger = get_logger("plugin_piper")


class PiperPlugin(TTSPluginBase):
    name = "piper"
    label = "Piper TTS"
    description = "Fast, local neural TTS - works on CPU, ideal for Termux"
    homepage = "https://github.com/rhasspy/piper"
    is_open_source = True
    requires_gpu = False

    PIPER_MODELS = {
        "ar_JO-kareem-low": {
            "url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/ar/ar_JO/kareem/low/ar_JO-kareem-low.onnx",
            "config_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/ar/ar_JO/kareem/low/ar_JO-kareem-low.onnx.json",
            "language": "ar",
            "speaker": "kareem",
            "quality": "low",
        },
        "ar_JO-kareem-medium": {
            "url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/ar/ar_JO/kareem/medium/ar_JO-kareem-medium.onnx",
            "config_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/ar/ar_JO/kareem/medium/ar_JO-kareem-medium.onnx.json",
            "language": "ar",
            "speaker": "kareem",
            "quality": "medium",
        },
        "en_US-lessac-medium": {
            "url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
            "config_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
            "language": "en",
            "speaker": "lessac",
            "quality": "medium",
        },
    }

    def check(self) -> bool:
        try:
            from piper import PiperVoice
            return True
        except ImportError:
            try:
                import piper_tts
                return True
            except ImportError:
                return False
        except Exception:
            return False

    def install(self) -> Dict[str, Any]:
        import subprocess, sys
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "piper-tts"])
            installed = self.check()
            return {"success": installed, "engine": self.name, "message": "Installed piper-tts" if installed else "Install failed"}
        except Exception as e:
            return {"success": False, "engine": self.name, "message": str(e)}

    def download_models(self, model_name: str = "ar_JO-kareem-medium") -> Dict[str, Any]:
        import urllib.request
        if model_name not in self.PIPER_MODELS:
            return {"success": False, "message": f"Unknown model: {model_name}. Available: {list(self.PIPER_MODELS.keys())}"}
        meta = self.PIPER_MODELS[model_name]
        model_path = self.models_dir / f"{model_name}.onnx"
        config_path = self.models_dir / f"{model_name}.onnx.json"

        try:
            logger.info(f"Downloading Piper model: {model_name}")
            urllib.request.urlretrieve(meta["url"], str(model_path))
            urllib.request.urlretrieve(meta["config_url"], str(config_path))
            return {"success": True, "model": model_name, "path": str(model_path), "config": str(config_path)}
        except Exception as e:
            return {"success": False, "model": model_name, "message": str(e)}

    def list_models(self) -> List[Dict]:
        available = []
        for name, meta in self.PIPER_MODELS.items():
            model_path = self.models_dir / f"{name}.onnx"
            available.append({
                "name": name,
                "language": meta["language"],
                "speaker": meta["speaker"],
                "quality": meta["quality"],
                "downloaded": model_path.exists(),
                "path": str(model_path) if model_path.exists() else None,
            })
        return available

    def list_voices(self) -> List[Dict]:
        voices = []
        for model in self.list_models():
            if model["downloaded"]:
                voices.append({
                    "name": model["speaker"],
                    "model": model["name"],
                    "language": model["language"],
                })
        return voices

    async def generate(self, text: str, voice: str = "kareem",
                       language: str = "ar", speed: float = 1.0) -> Dict[str, Any]:
        if not self.check():
            return {"success": False, "engine": self.name, "message": "Piper not installed. Run install()."}

        # Find downloaded model
        models = self.list_models()
        downloaded = [m for m in models if m["downloaded"] and m["language"] == language]
        if not downloaded:
            return {"success": False, "engine": self.name, "message": f"No downloaded model for language '{language}'. Run download_models()."}
        model = downloaded[0]

        try:
            import wave
            from piper import PiperVoice
            model_path = Path(model["path"])
            config_path = model_path.with_suffix(".onnx.json")
            voice_obj = PiperVoice.load(str(model_path), config_path=str(config_path))
            filepath = self._save_wav(b"", text, 22050)

            with wave.open(str(filepath), "wb") as wav_file:
                voice_obj.synthesize_wav(text, wav_file, length_scale=1.0/speed)

            return {
                "success": True,
                "engine": self.name,
                "file": str(filepath),
                "url": f"/api/downloads/{filepath.name}",
                "message": f"Generated with Piper ({model['name']})",
            }
        except Exception as e:
            logger.error(f"Piper generate failed: {e}")
            return {"success": False, "engine": self.name, "message": str(e)}


PLUGIN_CLASS = PiperPlugin
PLUGIN_NAME = "Piper TTS"
PLUGIN_DESCRIPTION = "Fast, local neural TTS - works on CPU, ideal for Termux"
