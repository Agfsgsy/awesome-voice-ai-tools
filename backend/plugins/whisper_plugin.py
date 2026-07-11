"""Whisper STT Plugin - Fast, open source transcription"""
import os
from typing import Dict, List, Any
from pathlib import Path
from backend.plugins.stt_plugin_base import STTPluginBase
from backend.core.logger import get_logger

logger = get_logger("plugin_whisper")


class WhisperPlugin(STTPluginBase):
    name = "whisper"
    label = "Whisper STT (OpenAI)"
    description = "Robust speech recognition, works well on CPU with small models."
    is_open_source = True
    requires_gpu = False

    MODELS = ["tiny", "base", "small"]

    def check(self) -> bool:
        try:
            import whisper
            return True
        except ImportError:
            return False

    def install(self) -> Dict[str, Any]:
        import subprocess, sys
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "openai-whisper"])
            installed = self.check()
            return {"success": installed, "engine": self.name, "message": "Installed openai-whisper" if installed else "Install failed"}
        except Exception as e:
            return {"success": False, "engine": self.name, "message": str(e)}

    def download_models(self, model_name: str = "tiny") -> Dict[str, Any]:
        if model_name not in self.MODELS:
             return {"success": False, "message": f"Unknown model: {model_name}. Available: {self.MODELS}"}
        if not self.check():
             return {"success": False, "message": "Whisper is not installed. Run install()."}

        import whisper
        try:
             logger.info(f"Downloading Whisper model: {model_name}")
             # Whisper handles its own download cache, we just trigger load to download it
             whisper.load_model(model_name, download_root=str(self.models_dir))
             return {"success": True, "model": model_name, "message": f"Model {model_name} ready."}
        except Exception as e:
             return {"success": False, "model": model_name, "message": str(e)}

    def list_models(self) -> List[Dict]:
        available = []
        for name in self.MODELS:
            # Check if model exists in download_root (whisper names them slightly differently sometimes, but mostly .pt)
            model_file = self.models_dir / f"{name}.pt"
            available.append({
                "name": name,
                "downloaded": model_file.exists(),
                "path": str(model_file) if model_file.exists() else None,
            })
        return available

    async def transcribe(self, audio_path: str, language: str = "ar") -> Dict[str, Any]:
        if not self.check():
            return {"success": False, "engine": self.name, "message": "Whisper not installed."}

        if not os.path.exists(audio_path):
             return {"success": False, "engine": self.name, "message": f"Audio file not found: {audio_path}"}

        # Use the first downloaded model, otherwise default to tiny (it will auto-download)
        models = self.list_models()
        downloaded = [m for m in models if m["downloaded"]]
        model_name = downloaded[0]["name"] if downloaded else "tiny"

        try:
            import whisper
            model = whisper.load_model(model_name, download_root=str(self.models_dir))

            # Whisper transcription can be CPU intensive, usually better to run in thread for async wrappers
            # but we'll do it sync here for simplicity unless it blocks
            result = model.transcribe(audio_path, language=language)

            return {
                "success": True,
                "engine": self.name,
                "text": result["text"].strip(),
                "language": result.get("language", language),
                "model_used": model_name
            }
        except Exception as e:
            logger.error(f"Whisper transcribe failed: {e}")
            return {"success": False, "engine": self.name, "message": str(e)}

PLUGIN_CLASS = WhisperPlugin
PLUGIN_NAME = "Whisper STT"
PLUGIN_DESCRIPTION = "Robust speech recognition, works well on CPU with small models."
