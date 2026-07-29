"""Safe audio validation, analysis, preprocessing, and lightweight scoring."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from backend.core.config import CACHE_DIR, OUTPUTS_DIR, UPLOADS_DIR, VOICES_DIR

ALLOWED_ROOTS = (UPLOADS_DIR.resolve(), VOICES_DIR.resolve(), CACHE_DIR.resolve(), OUTPUTS_DIR.resolve())
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".webm"}


def safe_resolve_audio(path: str | Path, extra_roots: Sequence[Path] = ()) -> Path:
    resolved = Path(path).expanduser().resolve()
    roots = tuple(ALLOWED_ROOTS) + tuple(Path(root).resolve() for root in extra_roots)
    if not resolved.is_file():
        raise FileNotFoundError("REFERENCE_AUDIO_NOT_FOUND")
    if resolved.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError("UNSUPPORTED_AUDIO_FORMAT")
    if not any(_is_relative_to(resolved, root) for root in roots):
        raise PermissionError("INVALID_FILE_PATH")
    return resolved


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ffprobe_audio(path: Path) -> Dict[str, Any]:
    if not shutil.which("ffprobe"):
        return {}
    command = [
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,sample_rate,channels,duration:format=duration,format_name",
        "-of", "json", str(path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    if completed.returncode != 0:
        raise ValueError("INVALID_REFERENCE_AUDIO")
    return json.loads(completed.stdout or "{}")


def convert_to_wav(path: Path, sample_rate: int = 24_000, trim_silence: bool = False) -> Path:
    output = CACHE_DIR / f"reference_{sha256_file(path)[:16]}_{sample_rate}.wav"
    if output.exists() and output.stat().st_size > 1_024:
        return output
    if not shutil.which("ffmpeg"):
        if path.suffix.lower() == ".wav":
            return path
        raise RuntimeError("FFMPEG_NOT_INSTALLED")
    filters: List[str] = []
    if trim_silence:
        filters.append("silenceremove=start_periods=1:start_silence=0.15:start_threshold=-48dB:stop_periods=1:stop_silence=0.25:stop_threshold=-48dB")
    command = ["ffmpeg", "-y", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sample_rate)]
    if filters:
        command.extend(["-af", ",".join(filters)])
    command.extend(["-c:a", "pcm_s16le", str(output)])
    completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    if completed.returncode != 0 or not output.exists():
        raise RuntimeError(f"AUDIO_CONVERSION_FAILED: {completed.stderr[-500:]}")
    return output


def analyze_audio(path: Path) -> Dict[str, Any]:
    probe = ffprobe_audio(path)
    result: Dict[str, Any] = {
        "file_hash": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "duration_seconds": None,
        "sample_rate": None,
        "channels": None,
        "peak": None,
        "rms": None,
        "silence_ratio": None,
        "clipping_ratio": None,
        "f0_mean": None,
        "f0_min": None,
        "f0_max": None,
        "spectral_centroid": None,
        "quality_score": None,
        "warnings": [],
    }
    streams = probe.get("streams") or []
    stream = streams[0] if streams else {}
    fmt = probe.get("format") or {}
    duration = stream.get("duration") or fmt.get("duration")
    result["duration_seconds"] = float(duration) if duration else None
    result["sample_rate"] = int(stream["sample_rate"]) if stream.get("sample_rate") else None
    result["channels"] = int(stream["channels"]) if stream.get("channels") else None

    try:
        import librosa
        import numpy as np

        samples, sr = librosa.load(str(path), sr=None, mono=True)
        if samples.size == 0:
            raise ValueError("REFERENCE_AUDIO_SILENT")
        abs_samples = np.abs(samples)
        result["sample_rate"] = int(sr)
        result["duration_seconds"] = float(len(samples) / sr)
        result["peak"] = float(abs_samples.max())
        result["rms"] = float(np.sqrt(np.mean(samples**2)))
        result["silence_ratio"] = float(np.mean(abs_samples < 10 ** (-50 / 20)))
        result["clipping_ratio"] = float(np.mean(abs_samples >= 0.999))
        centroid = librosa.feature.spectral_centroid(y=samples, sr=sr)
        result["spectral_centroid"] = float(np.nanmean(centroid))
        f0 = librosa.yin(samples, fmin=50, fmax=min(1_000, sr // 2 - 1), sr=sr)
        voiced = f0[np.isfinite(f0)]
        if voiced.size:
            result["f0_mean"] = float(np.mean(voiced))
            result["f0_min"] = float(np.percentile(voiced, 5))
            result["f0_max"] = float(np.percentile(voiced, 95))
    except ImportError:
        result["warnings"].append("librosa غير مثبت؛ التحليل الطيفي محدود")
    except Exception as exc:
        result["warnings"].append(f"تعذر التحليل المتقدم: {exc}")

    duration_value = result.get("duration_seconds") or 0.0
    if duration_value < 3.0:
        result["warnings"].append("التسجيل قصير جدًا؛ يفضل 20–60 ثانية من كلام واضح")
    if duration_value > 600:
        result["warnings"].append("التسجيل طويل؛ سيجري اختيار مقاطع مناسبة")
    if (result.get("rms") or 0.0) < 0.005:
        result["warnings"].append("مستوى الصوت منخفض جدًا")
    if (result.get("clipping_ratio") or 0.0) > 0.005:
        result["warnings"].append("يوجد قص صوتي clipping")
    if (result.get("silence_ratio") or 0.0) > 0.65:
        result["warnings"].append("نسبة الصمت مرتفعة")

    penalties = 0.0
    penalties += min(0.5, len(result["warnings"]) * 0.08)
    if duration_value < 3:
        penalties += 0.35
    if (result.get("clipping_ratio") or 0.0) > 0.02:
        penalties += 0.25
    result["quality_score"] = round(max(0.0, 1.0 - penalties), 4)
    return result


def validate_generated_audio(path: Path) -> Dict[str, Any]:
    if not path.exists() or path.stat().st_size < 1_024:
        raise RuntimeError("OUTPUT_AUDIO_INVALID")
    report = analyze_audio(path)
    if (report.get("duration_seconds") or 0.0) <= 0.1:
        raise RuntimeError("OUTPUT_AUDIO_INVALID")
    if report.get("rms") is not None and report["rms"] < 0.0005:
        raise RuntimeError("OUTPUT_AUDIO_SILENT")
    return report


def basic_frequency_similarity(reference: Dict[str, Any], generated: Dict[str, Any]) -> Optional[float]:
    keys = ("f0_mean", "spectral_centroid")
    scores: List[float] = []
    for key in keys:
        left = reference.get(key)
        right = generated.get(key)
        if left and right:
            ratio = min(float(left), float(right)) / max(float(left), float(right))
            scores.append(max(0.0, min(1.0, ratio)))
    return round(sum(scores) / len(scores), 4) if scores else None


def unique_output(prefix: str, suffix: str = ".wav") -> Path:
    return OUTPUTS_DIR / f"{prefix}_{uuid.uuid4().hex}{suffix}"
