"""إعدادات المشروع المركزية"""
import os
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = BASE_DIR / "backend"
PLUGINS_DIR = BACKEND_DIR / "plugins" / "builtin"
FRONTEND_DIR = BASE_DIR / "frontend"

MODELS_DIR = BASE_DIR / "models"
VOICES_DIR = BASE_DIR / "voices"
DOWNLOADS_DIR = BASE_DIR / "downloads"
UPLOADS_DIR = BASE_DIR / "uploads"
OUTPUTS_DIR = BASE_DIR / "outputs"
CACHE_DIR = BASE_DIR / "cache"
LOGS_DIR = BASE_DIR / "logs"
CONFIG_DIR = BASE_DIR / "config"

for d in [MODELS_DIR, VOICES_DIR, DOWNLOADS_DIR, UPLOADS_DIR, OUTPUTS_DIR, CACHE_DIR, LOGS_DIR, CONFIG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

APP_NAME = "Voice AI Studio Arabic"
APP_VERSION = "2.0.0"
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
APP_DEBUG = os.getenv("APP_DEBUG", "false").lower() == "true"

IS_TERMUX = os.path.exists("/data/data/com.termux/files/usr")
IS_ANDROID = IS_TERMUX
IS_COLAB = os.path.exists("/content")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
SUPPORTED_AUDIO_FORMATS = [".wav", ".mp3", ".flac", ".ogg", ".m4a"]

ENGINE_PRIORITY = ["kokoro", "piper", "gemini", "xtts", "f5", "bark", "melotts", "fish"]
