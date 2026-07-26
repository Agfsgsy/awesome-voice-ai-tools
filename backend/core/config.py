"""إعدادات المشروع المركزية مع دعم التشغيل العادي والنسخة المجمعة لويندوز."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _resource_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parent.parent.parent


def _data_dir() -> Path:
    override = os.getenv("VOICE_AI_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        local_app_data = os.getenv("LOCALAPPDATA")
        root = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return root / "VoiceAIStudioArabic"
    return _resource_dir()


RESOURCE_DIR = _resource_dir()
BASE_DIR = RESOURCE_DIR
DATA_DIR = _data_dir()
BACKEND_DIR = RESOURCE_DIR / "backend"
PLUGINS_DIR = BACKEND_DIR / "plugins" / "builtin"
FRONTEND_DIR = RESOURCE_DIR / "frontend"
MODELS_DIR = DATA_DIR / "models"
VOICES_DIR = DATA_DIR / "voices"
DOWNLOADS_DIR = DATA_DIR / "downloads"
UPLOADS_DIR = DATA_DIR / "uploads"
OUTPUTS_DIR = DATA_DIR / "outputs"
CACHE_DIR = DATA_DIR / "cache"
LOGS_DIR = DATA_DIR / "logs"
CONFIG_DIR = DATA_DIR / "config"
for directory in [DATA_DIR, MODELS_DIR, VOICES_DIR, DOWNLOADS_DIR, UPLOADS_DIR, OUTPUTS_DIR, CACHE_DIR, LOGS_DIR, CONFIG_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

APP_NAME = "استوديو ابن الواقدي"
APP_VERSION = "3.1.0"
APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
APP_DEBUG = os.getenv("APP_DEBUG", "false").lower() == "true"
IS_TERMUX = os.path.exists("/data/data/com.termux/files/usr")
IS_ANDROID = IS_TERMUX
IS_COLAB = os.path.exists("/content")
IS_FROZEN = bool(getattr(sys, "frozen", False))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")
ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "80"))
SUPPORTED_AUDIO_FORMATS = [".wav", ".mp3", ".flac", ".ogg", ".m4a"]
ENGINE_PRIORITY = ["gemini", "elevenlabs", "edge", "piper", "coqui", "kokoro", "melotts", "styletts2"]
