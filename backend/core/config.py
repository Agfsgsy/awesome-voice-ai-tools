"""Project Central Configuration - Production Ready"""
import os
from pathlib import Path
from typing import Optional, List, Dict
from pydantic import Field
from pydantic_settings import BaseSettings


class AppConfig(BaseSettings):
    """Application configuration with environment variable support"""
    
    # Application
    APP_NAME: str = Field(default="Voice AI Studio Arabic", description="Application name")
    APP_VERSION: str = Field(default="3.0.0", description="Application version")
    APP_HOST: str = Field(default="0.0.0.0", description="Server host")
    APP_PORT: int = Field(default=8000, description="Server port")
    APP_DEBUG: bool = Field(default=False, description="Debug mode")
    APP_ENV: str = Field(default="production", description="Environment: development, staging, production")
    
    # Security
    SECRET_KEY: str = Field(default="", description="Secret key for JWT/signing")
    API_KEY_HEADER: str = Field(default="X-API-Key", description="API key header name")
    ENABLE_AUTH: bool = Field(default=False, description="Enable authentication")
    CORS_ORIGINS: str = Field(default="*", description="Comma-separated CORS origins")
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True)
    CORS_ALLOW_METHODS: str = Field(default="*")
    CORS_ALLOW_HEADERS: str = Field(default="*")
    
    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = Field(default=True, description="Enable rate limiting")
    RATE_LIMIT_REQUESTS: int = Field(default=100, description="Requests per window")
    RATE_LIMIT_WINDOW: int = Field(default=60, description="Window in seconds")
    
    # Upload
    MAX_UPLOAD_MB: int = Field(default=50, description="Max upload size in MB")
    MAX_BATCH_SIZE: int = Field(default=10, description="Max batch items")
    SUPPORTED_AUDIO_FORMATS: List[str] = Field(default=[".wav", ".mp3", ".flac", ".ogg", ".m4a"])
    
    # TTS
    ENGINE_PRIORITY: List[str] = Field(default=["kokoro", "piper", "gemini", "xtts", "f5", "bark", "melotts", "fish"])
    DEFAULT_ENGINE: str = Field(default="kokoro", description="Default TTS engine")
    DEFAULT_LANGUAGE: str = Field(default="ar", description="Default language")
    DEFAULT_VOICE: str = Field(default="default", description="Default voice")
    DEFAULT_SPEED: float = Field(default=1.0, description="Default speech speed")
    DEFAULT_PITCH: float = Field(default=0.0, description="Default pitch")
    
    # Gemini
    GEMINI_API_KEY: str = Field(default="", description="Google Gemini API key")
    GEMINI_TTS_MODEL: str = Field(default="gemini-3.1-flash-tts-preview", description="Gemini TTS model")
    
    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    
    @property
    def BACKEND_DIR(self) -> Path:
        return self.BASE_DIR / "backend"
    
    @property
    def PLUGINS_DIR(self) -> Path:
        return self.BACKEND_DIR / "plugins" / "builtin"
    
    @property
    def FRONTEND_DIR(self) -> Path:
        return self.BASE_DIR / "frontend"
    
    @property
    def MODELS_DIR(self) -> Path:
        return self.BASE_DIR / "models"
    
    @property
    def VOICES_DIR(self) -> Path:
        return self.BASE_DIR / "voices"
    
    @property
    def DOWNLOADS_DIR(self) -> Path:
        return self.BASE_DIR / "downloads"
    
    @property
    def UPLOADS_DIR(self) -> Path:
        return self.BASE_DIR / "uploads"
    
    @property
    def OUTPUTS_DIR(self) -> Path:
        return self.BASE_DIR / "outputs"
    
    @property
    def CACHE_DIR(self) -> Path:
        return self.BASE_DIR / "cache"
    
    @property
    def LOGS_DIR(self) -> Path:
        return self.BASE_DIR / "logs"
    
    @property
    def CONFIG_DIR(self) -> Path:
        return self.BASE_DIR / "config"
    
    @property
    def DATASETS_DIR(self) -> Path:
        return self.BASE_DIR / "datasets"
    
    @property
    def TEMP_DIR(self) -> Path:
        return self.BASE_DIR / "temp"
    
    @property
    def PLUGINS_STATE_FILE(self) -> Path:
        return self.CONFIG_DIR / "plugins_state.json"
    
    @property
    def SETTINGS_FILE(self) -> Path:
        return self.CONFIG_DIR / "settings.json"
    
    @property
    def VOICE_LIBRARY_FILE(self) -> Path:
        return self.CONFIG_DIR / "voice_library.json"
    
    @property
    def MODEL_REGISTRY_FILE(self) -> Path:
        return self.CONFIG_DIR / "model_registry.json"
    
    @property
    def TASKS_DB_FILE(self) -> Path:
        return self.CONFIG_DIR / "tasks.json"
    
    @property
    def CORS_ORIGINS_LIST(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global configuration instance
settings = AppConfig()

# Ensure all directories exist
for d in [
    settings.MODELS_DIR, settings.VOICES_DIR, settings.DOWNLOADS_DIR,
    settings.UPLOADS_DIR, settings.OUTPUTS_DIR, settings.CACHE_DIR,
    settings.LOGS_DIR, settings.CONFIG_DIR, settings.DATASETS_DIR,
    settings.TEMP_DIR,
]:
    d.mkdir(parents=True, exist_ok=True)

# Legacy compatibility aliases
APP_NAME = settings.APP_NAME
APP_VERSION = settings.APP_VERSION
APP_HOST = settings.APP_HOST
APP_PORT = settings.APP_PORT
APP_DEBUG = settings.APP_DEBUG
IS_TERMUX = os.path.exists("/data/data/com.termux/files/usr")
IS_ANDROID = IS_TERMUX
IS_COLAB = os.path.exists("/content")
GEMINI_API_KEY = settings.GEMINI_API_KEY
GEMINI_TTS_MODEL = settings.GEMINI_TTS_MODEL
MODELS_DIR = settings.MODELS_DIR
VOICES_DIR = settings.VOICES_DIR
DOWNLOADS_DIR = settings.DOWNLOADS_DIR
UPLOADS_DIR = settings.UPLOADS_DIR
OUTPUTS_DIR = settings.OUTPUTS_DIR
CACHE_DIR = settings.CACHE_DIR
LOGS_DIR = settings.LOGS_DIR
CONFIG_DIR = settings.CONFIG_DIR
PLUGINS_DIR = settings.PLUGINS_DIR
FRONTEND_DIR = settings.FRONTEND_DIR
ENGINE_PRIORITY = settings.ENGINE_PRIORITY
MAX_UPLOAD_MB = settings.MAX_UPLOAD_MB
SUPPORTED_AUDIO_FORMATS = settings.SUPPORTED_AUDIO_FORMATS
BASE_DIR = settings.BASE_DIR


class GPUConfig:
    """GPU Configuration and Detection"""
    
    @staticmethod
    def has_cuda() -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False
    
    @staticmethod
    def get_cuda_info() -> Dict:
        try:
            import torch
            if torch.cuda.is_available():
                return {
                    "available": True,
                    "device_count": torch.cuda.device_count(),
                    "device_name": torch.cuda.get_device_name(0),
                    "memory_total_mb": torch.cuda.get_device_properties(0).total_memory // (1024**2),
                    "memory_allocated_mb": torch.cuda.memory_allocated(0) // (1024**2),
                    "memory_reserved_mb": torch.cuda.memory_reserved(0) // (1024**2),
                }
        except ImportError:
            pass
        return {"available": False}
    
    @staticmethod
    def has_mps() -> bool:
        try:
            import torch
            return torch.backends.mps.is_available()
        except ImportError:
            return False
    
    @staticmethod
    def get_device() -> str:
        if GPUConfig.has_cuda():
            return "cuda"
        if GPUConfig.has_mps():
            return "mps"
        return "cpu"
