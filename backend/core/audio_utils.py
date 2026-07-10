"""Enhanced Audio Processing Utilities - Production Ready"""
import os
import wave
import struct
import math
import hashlib
from pathlib import Path
from typing import Optional, Union, List, Dict, Any, Tuple

from backend.core.config import settings
from backend.core.logger import get_logger

logger = get_logger("audio_utils")


def generate_sine_wave(frequency: float = 440.0, duration: float = 1.0,
                        sample_rate: int = 22050, amplitude: float = 0.5) -> bytes:
    """Generate a sine wave as raw audio bytes"""
    num_samples = int(duration * sample_rate)
    frames = []
    for i in range(num_samples):
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
    """Generate silence audio"""
    num_samples = int(duration * sample_rate)
    return b'\x00' * (num_samples * 2)


def save_audio(audio_data, filename: str, sample_rate: int = 22050, channels: int = 1) -> Path:
    """Save audio data to WAV file with format auto-detection"""
    filepath = settings.OUTPUTS_DIR / filename

    if isinstance(audio_data, bytes):
        with wave.open(str(filepath), 'w') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data)
    elif hasattr(audio_data, '__len__') and not isinstance(audio_data, (str, bytes)):
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

    logger.info(f"Saved audio: {filepath}")
    return filepath


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
                duration = wf.getnframes() / wf.getframerate() if wf.getframerate() > 0 else 0
                info.update({
                    "channels": wf.getnchannels(),
                    "sample_width": wf.getsampwidth(),
                    "sample_rate": wf.getframerate(),
                    "frames": wf.getnframes(),
                    "duration_seconds": round(duration, 2),
                    "duration_formatted": _format_duration(duration),
                })
        else:
            try:
                import soundfile as sf
                snd = sf.info(str(filepath))
                info.update({
                    "channels": snd.channels,
                    "sample_rate": snd.samplerate,
                    "duration_seconds": round(snd.duration, 2),
                    "duration_formatted": _format_duration(snd.duration),
                    "subtype": snd.subtype,
                })
            except ImportError:
                pass
    except Exception as e:
        info["error"] = str(e)

    return info


def _format_duration(seconds: float) -> str:
    """Format seconds as HH:MM:SS"""
    mins, secs = divmod(int(seconds), 60)
    hrs, mins = divmod(mins, 60)
    if hrs > 0:
        return f"{hrs}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def convert_format(input_path: Path, output_format: str = "wav",
                    sample_rate: Optional[int] = None) -> Path:
    """Convert audio format using FFmpeg or soundfile"""
    output_path = input_path.with_suffix(f".{output_format}")

    try:
        import subprocess
        cmd = ["ffmpeg", "-y", "-i", str(input_path)]
        if sample_rate:
            cmd.extend(["-ar", str(sample_rate)])
        cmd.append(str(output_path))
        subprocess.run(cmd, capture_output=True, check=True)
        return output_path
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    try:
        import soundfile as sf
        data, sr = sf.read(str(input_path))
        sf.write(str(output_path), data, sample_rate or sr)
        return output_path
    except ImportError:
        raise ValueError("Install FFmpeg or soundfile for format conversion")


def apply_effects(input_path: Path, preset: str = "studio") -> Path:
    """Apply audio effects preset"""
    output_path = settings.OUTPUTS_DIR / f"{input_path.stem}_{preset}{input_path.suffix}"

    presets = {
        "studio": ["-af", "highpass=f=80,lowpass=f=12000,loudnorm=I=-16:TP=-1.5:LRA=11"],
        "lecture": ["-af", "highpass=f=100,lowpass=f=8000,loudnorm=I=-14:TP=-1:LRA=7"],
        "mosque": ["-af", "aecho=0.8:0.9:1000:0.3,loudnorm=I=-16:TP=-1.5:LRA=11"],
        "deep_voice": ["-af", "asetrate=22050*0.9,loudnorm=I=-16:TP=-1.5:LRA=11"],
        "podcast": ["-af", "highpass=f=80,compand=attacks=0.02:decays=0.2,loudnorm=I=-16:TP=-1.5:LRA=11"],
        "video_commentary": ["-af", "highpass=f=80,loudnorm=I=-14:TP=-1:LRA=7,atempo=1.05"],
        "noise_reduction": ["-af", "afftdn=nf=-25"],
        "normalize": ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"],
        "trim_silence": ["-af", "silenceremove=start_periods=1:start_duration=0.1:start_threshold=-50dB"],
    }

    ffmpeg_params = presets.get(preset, presets["studio"])

    try:
        import subprocess
        cmd = ["ffmpeg", "-y", "-i", str(input_path)] + ffmpeg_params + [str(output_path)]
        subprocess.run(cmd, capture_output=True, check=True)
        logger.info(f"Applied {preset} effects to {input_path.name}")
        return output_path
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.warning(f"FFmpeg not available, returning original")
        return input_path


def mix_audio(audio_paths: List[Path], output_filename: str) -> Path:
    """Mix multiple audio files together"""
    output_path = settings.OUTPUTS_DIR / output_filename

    try:
        import subprocess
        inputs = []
        for p in audio_paths:
            inputs.extend(["-i", str(p)])
        filters = f"amix=inputs={len(audio_paths)}:duration=longest:dropout_transition=2,loudnorm"
        cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", filters, str(output_path)]
        subprocess.run(cmd, capture_output=True, check=True)
        return output_path
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise ValueError("FFmpeg required for audio mixing")


def concatenate_audio(audio_paths: List[Path], output_filename: str) -> Path:
    """Concatenate multiple audio files sequentially"""
    output_path = settings.OUTPUTS_DIR / output_filename

    try:
        import subprocess
        # Create concat list file
        list_file = settings.TEMP_DIR / "concat_list.txt"
        with open(list_file, "w") as f:
            for p in audio_paths:
                f.write(f"file '{p.absolute()}'\n")

        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
               "-acodec", "copy", str(output_path)]
        subprocess.run(cmd, capture_output=True, check=True)
        list_file.unlink()
        return output_path
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise ValueError("FFmpeg required for audio concatenation")


def compute_checksum(filepath: Path) -> str:
    """Compute SHA-256 checksum of audio file"""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()
