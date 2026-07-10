"""Enhanced Audio Processing Utilities - Production Ready"""
import os
import io
import wave
import struct
import math
import hashlib
import tempfile
from pathlib import Path
from typing import Optional, Union, List, Dict, Any, Tuple
import asyncio

from backend.core.config import settings
from backend.core.logger import get_logger

logger = get_logger("audio_utils")


def generate_sine_wave(frequency: float = 440.0, duration: float = 1.0, 
                        sample_rate: int = 22050, amplitude: float = 0.5) -> bytes:
    """Generate a sine wave as raw audio bytes"""
    num_samples = int(duration * sample_rate)
    frames = []
    for i in range(num_samples):
        # Add fade in/out
        fade_duration = min(int(sample_rate * 0.01), num_samples // 4)
        fade = 1.0
        if i < fade_duration:
            fade = i / fade_duration
        elif i > num_samples - fade_duration:
            fade = (num_samples - i) / fade_duration
        
        value = int(32767 * amplitude * fade * math.sin(2 * math.pi * frequency * i / sample_rate))
        frames.append(struct.pack('<h', value))
    return b''.join(frames)


def generate_silence(duration: float = 1.0, sample_rate: int = 22050) -> bytes:
    """Generate silence"""
    num_samples = int(duration * sample_rate)
    return b'\x00' * (num_samples * 2)


def save_audio(audio_data: Union[bytes, list, Any], filename: str, 
               sample_rate: int = 22050, channels: int = 1) -> Path:
    """Save audio data to a WAV file with enhanced format support"""
    filepath = settings.OUTPUTS_DIR / filename
    
    if isinstance(audio_data, bytes):
        # Raw bytes - write as WAV
        with wave.open(str(filepath), 'w') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data)
    
    elif hasattr(audio_data, 'tobytes'):
        # NumPy array
        try:
            import numpy as np
            import soundfile as sf
            sf.write(str(filepath), audio_data, sample_rate)
        except ImportError:
            audio_data = np.array(audio_data, dtype=np.float32)
            data_int = (audio_data * 32767).astype('<i2').tobytes()
            with wave.open(str(filepath), 'w') as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(data_int)
    
    elif isinstance(audio_data, list):
        # Python list
        import numpy as np
        data = np.array(audio_data, dtype=np.float32)
        try:
            import soundfile as sf
            sf.write(str(filepath), data, sample_rate)
        except ImportError:
            data_int = (data * 32767).astype('<i2').tobytes()
            with wave.open(str(filepath), 'w') as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(data_int)
    
    else:
        raise ValueError(f"Unsupported audio data type: {type(audio_data)}")
    
    logger.info(f"Saved audio: {filepath} ({filepath.stat().st_size} bytes)")
    return filepath


def read_audio(filepath: Path) -> Tuple[bytes, int, int]:
    """Read audio file and return (data, sample_rate, channels)"""
    ext = filepath.suffix.lower()
    
    if ext == ".wav":
        with wave.open(str(filepath), 'r') as wf:
            data = wf.readframes(wf.getnframes())
            return data, wf.getframerate(), wf.getnchannels()
    
    # Try soundfile for other formats
    try:
        import soundfile as sf
        data, sr = sf.read(str(filepath))
        return data.tobytes(), sr, 1
    except ImportError:
        raise ValueError(f"Cannot read {ext} files. Install soundfile.")


def get_audio_info(filepath: Path) -> Dict[str, Any]:
    """Get audio file information"""
    if not filepath.exists():
        return {"error": "File not found"}
    
    info = {
        "filename": filepath.name,
        "path": str(filepath),
        "size_bytes": filepath.stat().st_size,
        "extension": filepath.suffix.lower(),
    }
    
    try:
        ext = filepath.suffix.lower()
        if ext == ".wav":
            with wave.open(str(filepath), 'r') as wf:
                info.update({
                    "channels": wf.getnchannels(),
                    "sample_width": wf.getsampwidth(),
                    "sample_rate": wf.getframerate(),
                    "frames": wf.getnframes(),
                    "duration_seconds": wf.getnframes() / wf.getframerate(),
                })
        else:
            try:
                import soundfile as sf
                snd = sf.info(str(filepath))
                info.update({
                    "channels": snd.channels,
                    "sample_rate": snd.samplerate,
                    "duration_seconds": snd.duration,
                    "subtype": snd.subtype,
                })
            except ImportError:
                pass
    except Exception as e:
        info["error"] = str(e)
    
    return info


def convert_format(input_path: Path, output_format: str = "wav", 
                    sample_rate: Optional[int] = None) -> Path:
    """Convert audio to different format using FFmpeg or soundfile"""
    output_path = input_path.with_suffix(f".{output_format}")
    
    # Try FFmpeg first
    try:
        import subprocess
        cmd = ["ffmpeg", "-y", "-i", str(input_path), "-ar", str(sample_rate or 22050)] if sample_rate else ["ffmpeg", "-y", "-i", str(input_path)]
        cmd.append(str(output_path))
        subprocess.run(cmd, capture_output=True, check=True)
        logger.info(f"Converted {input_path.name} -> {output_path.name}")
        return output_path
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    # Fallback to soundfile
    try:
        import soundfile as sf
        data, sr = sf.read(str(input_path))
        out_sr = sample_rate or sr
        sf.write(str(output_path), data, out_sr)
        logger.info(f"Converted {input_path.name} -> {output_path.name}")
        return output_path
    except ImportError:
        raise ValueError("Install FFmpeg or soundfile for format conversion")


def apply_effects(input_path: Path, preset: str = "studio") -> Path:
    """Apply audio effects using FFmpeg"""
    output_path = settings.OUTPUTS_DIR / f"{input_path.stem}_{preset}{input_path.suffix}"
    
    presets = {
        "studio": ["-af", "highpass=f=80,lowpass=f=12000,loudnorm=I=-16:TP=-1.5:LRA=11"],
        "lecture": ["-af", "highpass=f=100,lowpass=f=8000,loudnorm=I=-14:TP=-1:LRA=7"],
        "mosque": ["-af", "aecho=0.8:0.9:1000:0.3,loudnorm=I=-16:TP=-1.5:LRA=11"],
        "deep_voice": ["-af", "asetrate=22050*0.9,loudnorm=I=-16:TP=-1.5:LRA=11"],
        "podcast": ["-af", "highpass=f=80,compand=attacks=0.02:decays=0.2:points=-80/-80|-50/-30|-20/-10|0/0,loudnorm=I=-16:TP=-1.5:LRA=11"],
        "video_commentary": ["-af", "highpass=f=80,loudnorm=I=-14:TP=-1:LRA=7,atempo=1.05"],
    }
    
    ffmpeg_params = presets.get(preset, presets["studio"])
    
    try:
        import subprocess
        cmd = ["ffmpeg", "-y", "-i", str(input_path)] + ffmpeg_params + [str(output_path)]
        subprocess.run(cmd, capture_output=True, check=True)
        logger.info(f"Applied {preset} effects to {input_path.name}")
        return output_path
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.warning(f"FFmpeg not available, skipping effects for {input_path.name}")
        return input_path


def remove_noise(input_path: Path, output_path: Optional[Path] = None) -> Path:
    """Remove noise from audio using FFmpeg afftdn"""
    out = output_path or settings.OUTPUTS_DIR / f"{input_path.stem}_denoised{input_path.suffix}"
    
    try:
        import subprocess
        cmd = ["ffmpeg", "-y", "-i", str(input_path), "-af", "afftdn=nf=-25", str(out)]
        subprocess.run(cmd, capture_output=True, check=True)
        return out
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.warning("FFmpeg not available for noise removal")
        return input_path


def normalize_audio(input_path: Path, output_path: Optional[Path] = None,
                    target_level: float = -16.0) -> Path:
    """Normalize audio loudness"""
    out = output_path or settings.OUTPUTS_DIR / f"{input_path.stem}_normalized{input_path.suffix}"
    
    try:
        import subprocess
        cmd = ["ffmpeg", "-y", "-i", str(input_path), "-af", 
               f"loudnorm=I={target_level}:TP=-1.5:LRA=11", str(out)]
        subprocess.run(cmd, capture_output=True, check=True)
        return out
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.warning("FFmpeg not available for normalization")
        return input_path


def trim_silence(input_path: Path, output_path: Optional[Path] = None,
                 threshold: float = -50.0) -> Path:
    """Trim silence from start and end"""
    out = output_path or settings.OUTPUTS_DIR / f"{input_path.stem}_trimmed{input_path.suffix}"
    
    try:
        import subprocess
        cmd = ["ffmpeg", "-y", "-i", str(input_path), "-af", 
               f"silenceremove=start_periods=1:start_duration=0.1:start_threshold={threshold}dB: