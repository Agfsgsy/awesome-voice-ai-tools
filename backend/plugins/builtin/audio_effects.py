"""مؤثرات صوتية احترافية للمواعظ والبودكاست والتعليق العربي."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict

__version__ = "2.1.0"
PLUGIN_NAME = "Audio Effects Pro"
PLUGIN_DESCRIPTION = "تنقية وتحسين وضغط وصدى ودفء ووضوح للصوت العربي"

PRESETS: Dict[str, Dict[str, Any]] = {
    "clean_voice": {"label": "تنقية ووضوح", "high_pass": 70, "low_pass": 12000, "compressor": True, "normalize": True, "clarity": 2, "fade": 35},
    "studio": {"label": "استوديو احترافي", "high_pass": 65, "low_pass": 14000, "compressor": True, "normalize": True, "clarity": 1.5, "gain": 1},
    "sermon_calm": {"label": "واعظ هادئ", "high_pass": 70, "low_pass": 10500, "compressor": True, "normalize": True, "warmth": 2, "reverb": "light", "fade": 80},
    "sermon_powerful": {"label": "خطيب قوي", "high_pass": 75, "low_pass": 12500, "compressor": True, "normalize": True, "bass": 3, "clarity": 2.5, "gain": 2, "reverb": "light"},
    "dua_emotional": {"label": "دعاء مؤثر", "high_pass": 60, "low_pass": 9500, "compressor": True, "normalize": True, "warmth": 3, "reverb": "medium", "gain": -1, "fade": 180},
    "mosque": {"label": "مسجد واسع", "high_pass": 65, "low_pass": 11000, "normalize": True, "reverb": "heavy", "warmth": 2},
    "lecture": {"label": "محاضرة واضحة", "high_pass": 85, "low_pass": 11500, "compressor": True, "normalize": True, "clarity": 2},
    "deep_voice": {"label": "صوت عميق", "pitch": -2, "compressor": True, "normalize": True, "bass": 4},
    "podcast": {"label": "بودكاست", "high_pass": 75, "low_pass": 13500, "compressor": True, "normalize": True, "clarity": 1.5},
    "documentary": {"label": "وثائقي رزين", "high_pass": 60, "low_pass": 12000, "compressor": True, "normalize": True, "bass": 2, "warmth": 1.5, "gain": 1},
    "radio": {"label": "إذاعي", "high_pass": 100, "low_pass": 8000, "compressor": True, "normalize": True, "clarity": 3},
    "echo": {"label": "صدى واضح", "normalize": True, "reverb": "echo"},
    "video_commentary": {"label": "تعليق فيديو", "high_pass": 80, "low_pass": 12500, "compressor": True, "normalize": True, "clarity": 2, "gain": 1.5},
}


def register() -> None:
    return None


def get_presets() -> Dict[str, Dict[str, Any]]:
    return PRESETS


def _ffmpeg_executable() -> str | None:
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _audio_segment():
    from pydub import AudioSegment

    executable = _ffmpeg_executable()
    if executable:
        AudioSegment.converter = executable
    return AudioSegment


def _load_audio(path: str):
    """Load audio without requiring a separate ffprobe executable.

    imageio-ffmpeg bundles ffmpeg but not ffprobe. Pydub normally calls ffprobe
    for compressed files, so decode them to a temporary WAV first.
    """
    AudioSegment = _audio_segment()
    source = Path(path)
    extension = source.suffix.lower()
    if extension == ".wav":
        return AudioSegment.from_wav(str(source))

    executable = _ffmpeg_executable()
    if not executable:
        raise RuntimeError("FFmpeg غير متوفر. ثبّت imageio-ffmpeg أو ffmpeg.")

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        completed = subprocess.run(
            [
                executable,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-vn",
                "-acodec",
                "pcm_s16le",
                str(temp_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or "تعذر فك ترميز الملف الصوتي").strip()
            raise RuntimeError(detail)
        return AudioSegment.from_wav(str(temp_path))
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)


def _pitch_shift(audio, semitones: float):
    if not semitones:
        return audio
    new_rate = int(audio.frame_rate * (2.0 ** (semitones / 12.0)))
    return audio._spawn(audio.raw_data, overrides={"frame_rate": new_rate}).set_frame_rate(audio.frame_rate)


def _add_reverb(audio, strength: str):
    settings = {
        "light": [(85, -12), (170, -18)],
        "medium": [(110, -10), (230, -16), (360, -22)],
        "heavy": [(140, -8), (290, -13), (470, -18), (700, -24)],
        "echo": [(220, -8), (440, -14), (660, -20)],
    }
    result = audio
    for delay, attenuation in settings.get(strength, []):
        delayed = audio.apply_gain(attenuation)
        result = result.overlay(delayed, position=delay)
    return result


def _tone_layer(audio, cutoff: int, gain: float, high: bool = False):
    layer = audio.high_pass_filter(cutoff) if high else audio.low_pass_filter(cutoff)
    return audio.overlay(layer.apply_gain(gain))


def edit_audio(input_path: str, output_path: str, trim_start_ms: int = None, trim_end_ms: int = None) -> bool:
    """قص ملف صوتي مع إخراج WAV متوافق."""
    try:
        audio = _load_audio(input_path)
        start = max(0, int(trim_start_ms or 0))
        end = max(0, int(trim_end_ms or 0))
        if start:
            audio = audio[start:]
        if end:
            audio = audio[:-end] if end < len(audio) else audio[:0]
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        audio.export(output_path, format="wav")
        return True
    except Exception as exc:
        print(f"Error editing audio: {exc}")
        return False


def process_audio(input_path: str, output_path: str, preset_name: str) -> bool:
    """تطبيق إعداد احترافي على WAV أو MP3 أو M4A أو FLAC أو OGG."""
    preset = PRESETS.get(preset_name)
    if not preset:
        print(f"Unknown effect preset: {preset_name}")
        return False

    try:
        from pydub.effects import compress_dynamic_range, normalize

        audio = _load_audio(input_path)
        if not audio:
            return False

        if preset.get("high_pass"):
            audio = audio.high_pass_filter(int(preset["high_pass"]))
        if preset.get("low_pass"):
            audio = audio.low_pass_filter(int(preset["low_pass"]))
        if preset.get("pitch"):
            audio = _pitch_shift(audio, float(preset["pitch"]))
        if preset.get("compressor"):
            audio = compress_dynamic_range(audio, threshold=-20.0, ratio=4.0, attack=5.0, release=80.0)
        if preset.get("bass"):
            audio = _tone_layer(audio, 220, float(preset["bass"]), high=False)
        if preset.get("warmth"):
            audio = _tone_layer(audio, 500, float(preset["warmth"]), high=False)
        if preset.get("clarity"):
            audio = _tone_layer(audio, 2600, float(preset["clarity"]), high=True)
        if preset.get("reverb"):
            audio = _add_reverb(audio, str(preset["reverb"]))
        if preset.get("normalize"):
            audio = normalize(audio, headroom=1.0)
        if preset.get("gain"):
            audio = audio.apply_gain(float(preset["gain"]))
        if preset.get("fade"):
            fade = min(int(preset["fade"]), max(0, len(audio) // 4))
            audio = audio.fade_in(fade).fade_out(fade)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        audio.set_sample_width(2).export(output_path, format="wav")
        return True
    except Exception as exc:
        print(f"Error processing audio: {exc}")
        return False
