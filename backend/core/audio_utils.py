"""أدوات الصوت المساعدة"""
import os
import wave
import struct
import hashlib
from pathlib import Path
from typing import Optional

from backend.core.config import OUTPUTS_DIR
from backend.core.logger import get_logger

logger = get_logger("audio_utils")


def generate_sine_wave(frequency: float = 440.0, duration: float = 1.0, sample_rate: int = 22050) -> bytes:
    """توليد موجة جيبية بسيطة (محرك احتياطي)"""
    import math
    num_samples = int(duration * sample_rate)
    frames = []
    for i in range(num_samples):
        value = int(32767 * 0.5 * math.sin(2 * math.pi * frequency * i / sample_rate))
        frames.append(struct.pack('<h', value))
    return b''.join(frames)


def save_audio(audio_data: bytes, filename: str, sample_rate: int = 22050) -> Path:
    """حفظ بيانات الصوت في ملف WAV"""
    if isinstance(audio_data, bytes):
        filepath = OUTPUTS_DIR / filename
        with wave.open(str(filepath), 'w') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            if isinstance(audio_data, bytes):
                wf.writeframes(audio_data)
        logger.info(f"Saved audio: {filepath}")
        return filepath
    elif hasattr(audio_data, '__len__'):
        import numpy as np
        filepath = OUTPUTS_DIR / filename
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
        logger.info(f"Saved audio: {filepath}")
        return filepath
    else:
        raise ValueError(f"Unsupported audio data type: {type(audio_data)}")
