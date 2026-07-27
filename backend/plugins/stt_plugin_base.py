"""Base class لجميع إضافات STT"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any
from pathlib import Path
from backend.core.logger import get_logger
from backend.core.config import MODELS_DIR

logger = get_logger("stt_plugin")

class STTPluginBase(ABC):
    """قاعدة موحدة لجميع إضافات محركات تحويل الصوت إلى نص (STT)"""

    name: str = "base_stt"
    label: str = "Base STT"
    description: str = ""
    is_open_source: bool = True
    requires_gpu: bool = False

    def __init__(self):
        self.models_dir = MODELS_DIR / self.name
        self.models_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def check(self) -> bool:
        """هل المحرك مثبت ومتاح؟"""
        pass

    @abstractmethod
    def install(self) -> Dict[str, Any]:
        """تثبيت المحرك (pip install أو تحميل)"""
        pass

    @abstractmethod
    def download_models(self, model_name: str = "default") -> Dict[str, Any]:
        """تحميل النماذج المطلوبة"""
        pass

    @abstractmethod
    def list_models(self) -> List[Dict]:
        """قائمة النماذج المتاحة أو المحملة"""
        pass

    @abstractmethod
    async def transcribe(self, audio_path: str, language: str = "ar") -> Dict[str, Any]:
        """تحويل ملف صوتي إلى نص"""
        pass

    def health(self) -> Dict[str, Any]:
        """فحص صحة المحرك"""
        installed = self.check()
        models = self.list_models()
        return {
            "name": self.name,
            "label": self.label,
            "installed": installed,
            "models_count": len(models),
            "ready": installed and any(m.get("downloaded", False) for m in models) if models else False,
            "requires_gpu": self.requires_gpu,
            "is_open_source": self.is_open_source,
        }
