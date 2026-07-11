"""أداة التقييم التلقائي لجودة الصوت"""
import wave
import struct
from typing import Dict, Any
from backend.core.logger import get_logger

logger = get_logger("audio_eval")

def evaluate_audio_quality(filepath: str) -> Dict[str, Any]:
    """
    يقيم جودة الصوت بشكل تلقائي.
    يفحص:
    1. هل الملف موجود وصالح (WAV).
    2. هل يحتوي على بيانات صوتية غير صامتة بالكامل (RMS Energy).
    3. مستوى الإشارة (نسبة الديسيبل).
    """
    try:
        with wave.open(filepath, "r") as wav_file:
            n_channels = wav_file.getnchannels()
            sampwidth = wav_file.getsampwidth()
            framerate = wav_file.getframerate()
            n_frames = wav_file.getnframes()

            if n_frames == 0:
                return {
                    "valid": False,
                    "reason": "Audio file is empty (0 frames)."
                }

            raw_data = wav_file.readframes(n_frames)

            if sampwidth == 2:
                # 16-bit PCM
                format_str = f"<{n_frames * n_channels}h"
                try:
                    import struct
                    samples = struct.unpack(format_str, raw_data)
                except struct.error:
                     return {"valid": False, "reason": "Corrupt audio data"}
            else:
                # Not doing complex decoding for other widths, just checking if raw data is all zeros
                samples = [int(b) for b in raw_data]

            import math
            # Calculate RMS
            sum_squares = sum((s / 32768.0) ** 2 for s in samples) if sampwidth == 2 else sum(s**2 for s in samples)
            rms = math.sqrt(sum_squares / len(samples)) if samples else 0.0

            # Simple check to see if it's dead silent
            is_silent = rms < 0.0001

            return {
                "valid": True,
                "silent": is_silent,
                "rms_energy": rms,
                "framerate": framerate,
                "channels": n_channels,
                "duration_seconds": n_frames / framerate
            }

    except Exception as e:
        logger.error(f"Error evaluating audio {filepath}: {e}")
        return {
            "valid": False,
            "reason": str(e)
        }
