"""Professional FFmpeg mastering presets for Arabic speech, sermons and podcasts."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

__version__ = "3.0.0"
PLUGIN_NAME = "Audio Effects Pro"
PLUGIN_DESCRIPTION = "تنقية وماسترينغ وضغط ودفء ووضوح وصدى احترافي للصوت العربي"

PRESETS: Dict[str, Dict[str, Any]] = {
    "human_master": {"label": "بشري فائق - ماستر", "filters": ["highpass=f=65", "lowpass=f=15500", "equalizer=f=130:t=q:w=1.0:g=1.4", "equalizer=f=3200:t=q:w=1.1:g=1.3", "equalizer=f=7200:t=q:w=1.2:g=0.5", "acompressor=threshold=-21dB:ratio=2.4:attack=12:release=150:makeup=1.8", "loudnorm=I=-16:TP=-1.3:LRA=7"]},
    "clean_voice": {"label": "تنقية ووضوح", "filters": ["highpass=f=75", "lowpass=f=14500", "equalizer=f=3000:t=q:w=1:g=1.8", "acompressor=threshold=-22dB:ratio=2.8:attack=8:release=120:makeup=1.5", "loudnorm=I=-17:TP=-1.5:LRA=8"]},
    "studio": {"label": "استوديو احترافي", "filters": ["highpass=f=65", "lowpass=f=16000", "equalizer=f=150:t=q:w=1:g=1", "equalizer=f=2800:t=q:w=1:g=1.5", "acompressor=threshold=-20dB:ratio=3:attack=8:release=120:makeup=2", "loudnorm=I=-15:TP=-1.2:LRA=6"]},
    "warm_broadcast": {"label": "إذاعي دافئ", "filters": ["highpass=f=70", "lowpass=f=14500", "equalizer=f=140:t=q:w=1:g=2.2", "equalizer=f=2600:t=q:w=1:g=1.2", "acompressor=threshold=-22dB:ratio=3.2:attack=6:release=130:makeup=2.5", "loudnorm=I=-14:TP=-1:LRA=5"]},
    "sermon_calm": {"label": "واعظ هادئ", "filters": ["highpass=f=65", "lowpass=f=12500", "equalizer=f=180:t=q:w=1.2:g=1.8", "acompressor=threshold=-23dB:ratio=2.3:attack=15:release=180:makeup=1.4", "aecho=0.8:0.55:95|190:0.08|0.04", "loudnorm=I=-17:TP=-1.5:LRA=8"]},
    "sermon_powerful": {"label": "خطيب قوي", "filters": ["highpass=f=72", "lowpass=f=14500", "equalizer=f=120:t=q:w=1:g=2.5", "equalizer=f=3000:t=q:w=1:g=2", "acompressor=threshold=-23dB:ratio=4:attack=5:release=105:makeup=3", "aecho=0.8:0.45:75|150:0.06|0.03", "loudnorm=I=-13.5:TP=-0.8:LRA=5"]},
    "cinematic_sermon": {"label": "موعظة سينمائية", "filters": ["highpass=f=60", "lowpass=f=15000", "equalizer=f=110:t=q:w=1:g=2", "equalizer=f=2200:t=q:w=1.2:g=1.4", "acompressor=threshold=-24dB:ratio=3.5:attack=10:release=180:makeup=2.2", "aecho=0.82:0.58:120|250|430:0.10|0.055|0.025", "loudnorm=I=-15:TP=-1:LRA=7"]},
    "dua_emotional": {"label": "دعاء مؤثر", "filters": ["highpass=f=58", "lowpass=f=12000", "equalizer=f=190:t=q:w=1.2:g=2", "acompressor=threshold=-25dB:ratio=2.1:attack=20:release=220:makeup=1.2", "aecho=0.82:0.62:130|280|470:0.11|0.055|0.025", "loudnorm=I=-18:TP=-1.8:LRA=9"]},
    "mosque": {"label": "صدى مسجد", "filters": ["highpass=f=62", "lowpass=f=12500", "aecho=0.84:0.68:145|300|510|760:0.14|0.085|0.045|0.02", "loudnorm=I=-17:TP=-1.5:LRA=8"]},
    "deep_voice": {"label": "صوت عميق قوي", "filters": ["highpass=f=55", "lowpass=f=13500", "asetrate=24000*0.955", "aresample=24000", "atempo=1.047", "equalizer=f=105:t=q:w=1:g=3", "acompressor=threshold=-22dB:ratio=3.2:attack=8:release=130:makeup=2", "loudnorm=I=-15:TP=-1:LRA=6"]},
    "documentary": {"label": "وثائقي رزين", "filters": ["highpass=f=60", "lowpass=f=14500", "equalizer=f=125:t=q:w=1:g=1.8", "equalizer=f=2400:t=q:w=1:g=1", "acompressor=threshold=-22dB:ratio=2.8:attack=12:release=160:makeup=1.8", "loudnorm=I=-16:TP=-1.2:LRA=7"]},
    "radio": {"label": "إذاعي قوي", "filters": ["highpass=f=100", "lowpass=f=9000", "equalizer=f=2500:t=q:w=0.9:g=2.8", "acompressor=threshold=-25dB:ratio=5:attack=3:release=80:makeup=4", "loudnorm=I=-13:TP=-0.8:LRA=4"]},
    "podcast": {"label": "بودكاست احترافي", "filters": ["highpass=f=72", "lowpass=f=15000", "equalizer=f=140:t=q:w=1:g=1.2", "equalizer=f=3200:t=q:w=1:g=1.4", "acompressor=threshold=-22dB:ratio=3:attack=9:release=140:makeup=2", "loudnorm=I=-16:TP=-1.2:LRA=6"]},
    "podcast_ultra": {"label": "بودكاست بشري فائق", "filters": ["highpass=f=62", "lowpass=f=15800", "equalizer=f=115:t=q:w=0.9:g=1.6", "equalizer=f=420:t=q:w=1.0:g=-0.7", "equalizer=f=2850:t=q:w=1.1:g=1.7", "equalizer=f=7600:t=q:w=1.3:g=0.6", "acompressor=threshold=-24dB:ratio=2.6:attack=14:release=190:makeup=2.1", "dynaudnorm=f=250:g=7:p=0.85", "loudnorm=I=-15:TP=-1.0:LRA=7"]},
    "podcast_truth": {"label": "True Podcast - طبيعي بلا صدى", "filters": ["highpass=f=55", "lowpass=f=17000", "equalizer=f=120:t=q:w=0.9:g=0.9", "equalizer=f=360:t=q:w=1.0:g=-0.5", "equalizer=f=2900:t=q:w=1.1:g=1.1", "equalizer=f=6800:t=q:w=1.3:g=0.35", "acompressor=threshold=-24dB:ratio=2.0:attack=24:release=230:makeup=1.25", "alimiter=limit=0.94:attack=8:release=90", "loudnorm=I=-16:TP=-1.2:LRA=8"]},
    "echo": {"label": "صدى واضح", "filters": ["aecho=0.8:0.6:220|440|660:0.18|0.09|0.045", "loudnorm=I=-17:TP=-1.5:LRA=8"]},
    "video_commentary": {"label": "تعليق فيديو قوي", "filters": ["highpass=f=78", "lowpass=f=14500", "equalizer=f=3000:t=q:w=1:g=2", "acompressor=threshold=-23dB:ratio=3.8:attack=5:release=100:makeup=2.8", "loudnorm=I=-14:TP=-0.9:LRA=5"]},
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
        executable = imageio_ffmpeg.get_ffmpeg_exe()
        return executable if Path(executable).exists() else None
    except Exception:
        return None


def _output_args(output_path: str) -> List[str]:
    extension = Path(output_path).suffix.lower()
    if extension == ".wav":
        return ["-c:a", "pcm_s16le", "-ar", "48000", "-ac", "1"]
    if extension == ".flac":
        return ["-c:a", "flac", "-ar", "48000", "-ac", "1"]
    return ["-c:a", "libmp3lame", "-b:a", "192k", "-ar", "48000", "-ac", "1"]


def _run_ffmpeg(input_path: str, output_path: str, filters: List[str], start_seconds: float | None = None, duration_seconds: float | None = None) -> bool:
    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        raise RuntimeError("أداة FFmpeg المرفقة غير متوفرة داخل البرنامج.")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    command: List[str] = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    if start_seconds and start_seconds > 0:
        command += ["-ss", f"{start_seconds:.3f}"]
    command += ["-i", str(input_path), "-vn"]
    if duration_seconds is not None and duration_seconds > 0:
        command += ["-t", f"{duration_seconds:.3f}"]
    if filters:
        command += ["-af", ",".join(filters)]
    command += _output_args(output_path)
    command.append(str(output_path))
    completed = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or "تعذر تنفيذ المعالجة الصوتية").strip())
    output = Path(output_path)
    return output.exists() and output.stat().st_size > 0


def edit_audio(input_path: str, output_path: str, trim_start_ms: int = None, trim_end_ms: int = None) -> bool:
    try:
        start = max(0, int(trim_start_ms or 0)) / 1000.0
        end = max(0, int(trim_end_ms or 0)) / 1000.0
        if end > 0:
            return _run_ffmpeg(input_path, output_path, [f"atrim=start={start}", f"areverse,atrim=start={end},areverse"])
        return _run_ffmpeg(input_path, output_path, [], start_seconds=start)
    except Exception as exc:
        print(f"Error editing audio: {exc}")
        return False


def process_audio(input_path: str, output_path: str, preset_name: str) -> bool:
    preset = PRESETS.get(preset_name)
    if not preset:
        print(f"Unknown effect preset: {preset_name}")
        return False
    try:
        return _run_ffmpeg(input_path, output_path, list(preset.get("filters", [])))
    except Exception as exc:
        print(f"Error processing audio: {exc}")
        return False