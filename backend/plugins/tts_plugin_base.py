"""Base class لجميع إضافات TTS"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from pathlib import Path
from backend.core.logger import get_logger
from backend.core.config import MODELS_DIR, VOICES_DIR, OUTPUTS_DIR

logger = get_logger("tts_plugin")


class TTSPluginBase(ABC):
    """قاعدة موحدة لجميع إضافات محركات TTS"""

    name: str = "base"
    label: str = "Base TTS"
    description: str = ""
    homepage: str = ""
    is_open_source: bool = True
    requires_gpu: bool = False

    def __init__(self):
        self.models_dir = MODELS_DIR / self.name
        self.voices_dir = VOICES_DIR / self.name
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.voices_dir.mkdir(parents=True, exist_ok=True)

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
    def list_voices(self) -> List[Dict]:
        """قائمة الأصوات المتاحة"""
        pass

    @abstractmethod
    async def generate(self, text: str, voice: str = "default",
                       language: str = "ar", speed: float = 1.0) -> Dict[str, Any]:
        """توليد صوت من نص"""
        pass

    def health(self) -> Dict[str, Any]:
        """فحص صحة المحرك"""
        installed = self.check()
        models = self.list_models()
        voices = self.list_voices()
        return {
            "name": self.name,
            "label": self.label,
            "installed": installed,
            "models_count": len(models),
            "voices_count": len(voices),
            "ready": installed and len(models) > 0,
            "requires_gpu": self.requires_gpu,
            "is_open_source": self.is_open_source,
        }

    def _save_wav(self, audio_data, filename: str, sample_rate: int = 22050) -> Path:
        """حفظ بيانات الصوت"""
        import hashlib
        name_hash = hashlib.md5(filename.encode()).hexdigest()[:8]
        out_name = f"{self.name}_{name_hash}.wav"
        filepath = OUTPUTS_DIR / out_name

        if isinstance(audio_data, bytes):
            import wave, struct
            with wave.open(str(filepath), 'w') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio_data)
        elif hasattr(audio_data, '__len__'):
            import numpy as np
            data = np.array(audio_data, dtype=np.float32)
            try:
                import soundfile as sf
                sf.write(str(filepath), data, sample_rate)
            except ImportError:
                data_int = (data * 32767).astype('<i2').tobytes()
                with wave.open(str(filepath), 'w') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sample_rate)
                    wf.writeframes(data_int)
        else:
            raise ValueError(f"Unsupported audio type: {type(audio_data)}")

        return filepath
