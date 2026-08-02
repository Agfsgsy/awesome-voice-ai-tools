"""فحص وتحويل الصوت عبر FFmpeg مع مؤشرات جودة قابلة للتفسير."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class AudioAnalysisError(ValueError):
    """صيغة غير قابلة للفك أو تسجيل غير صالح."""


def _binary(name: str) -> str:
    value = shutil.which(name)
    if not value:
        raise AudioAnalysisError("FFmpeg غير مثبت على الخادم")
    return value


def _run(command: list[str], timeout: int = 180) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(command, capture_output=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise AudioAnalysisError("استغرق فك الملف وقتًا أطول من المسموح") from exc


def probe_audio(path: Path) -> dict[str, Any]:
    result = _run(
        [
            _binary("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration,format_name,size:stream=index,codec_type,codec_name,sample_rate,channels,bits_per_sample",
            "-of",
            "json",
            str(path),
        ],
        timeout=60,
    )
    if result.returncode != 0:
        raise AudioAnalysisError("صيغة الملف غير قابلة للفك")
    try:
        payload = json.loads(result.stdout.decode("utf-8"))
        audio_stream = next(item for item in payload.get("streams", []) if item.get("codec_type") == "audio")
        duration = float(payload.get("format", {}).get("duration") or 0)
    except (ValueError, TypeError, StopIteration, json.JSONDecodeError) as exc:
        raise AudioAnalysisError("الملف لا يحتوي مسارًا صوتيًا صالحًا") from exc
    if duration <= 0:
        raise AudioAnalysisError("الملف الناتج غير صالح أو مدته صفر")
    return {
        "duration_seconds": round(duration, 3),
        "format": payload.get("format", {}).get("format_name", "unknown"),
        "codec": audio_stream.get("codec_name", "unknown"),
        "sample_rate": int(audio_stream.get("sample_rate") or 0),
        "channels": int(audio_stream.get("channels") or 0),
        "bits_per_sample": int(audio_stream.get("bits_per_sample") or 0),
        "size_bytes": int(payload.get("format", {}).get("size") or path.stat().st_size),
    }


def analyze_audio(path: Path, max_analysis_seconds: int = 180) -> dict[str, Any]:
    metadata = probe_audio(path)
    result = _run(
        [
            _binary("ffmpeg"),
            "-v",
            "error",
            "-i",
            str(path),
            "-t",
            str(max_analysis_seconds),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "f32le",
            "pipe:1",
        ]
    )
    if result.returncode != 0 or not result.stdout:
        raise AudioAnalysisError("صيغة الملف غير قابلة للفك")

    try:
        import numpy as np
    except ImportError as exc:
        raise AudioAnalysisError("مكتبة تحليل الصوت NumPy غير مثبتة") from exc

    samples = np.frombuffer(result.stdout, dtype="<f4")
    samples = samples[np.isfinite(samples)]
    if samples.size < 1600:
        raise AudioAnalysisError("التسجيل قصير جدًا للتحليل")
    samples = np.clip(samples, -1.5, 1.5)
    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(np.square(samples), dtype=np.float64)))
    peak_dbfs = 20 * math.log10(max(peak, 1e-9))
    rms_dbfs = 20 * math.log10(max(rms, 1e-9))
    clipping_ratio = float(np.mean(np.abs(samples) >= 0.99))

    frame_size = 320
    usable = samples[: samples.size - (samples.size % frame_size)]
    frames = usable.reshape((-1, frame_size))
    frame_rms = np.sqrt(np.mean(np.square(frames), axis=1, dtype=np.float64))
    frame_db = 20 * np.log10(np.maximum(frame_rms, 1e-9))
    silence_ratio = float(np.mean(frame_db < -45.0))
    speech_frames = frame_db[frame_db >= -45.0]
    quiet_frames = frame_db[frame_db < -35.0]
    speech_level = float(np.percentile(speech_frames, 70)) if speech_frames.size else -90.0
    noise_floor = float(np.percentile(quiet_frames, 50)) if quiet_frames.size else min(rms_dbfs - 20.0, -55.0)
    snr_db = max(0.0, min(80.0, speech_level - noise_floor))
    speech_ratio = max(0.0, 1.0 - silence_ratio)

    sample_rate_score = 100 if metadata["sample_rate"] >= 24000 else 80 if metadata["sample_rate"] >= 16000 else 45
    clipping_score = max(0.0, 100.0 - clipping_ratio * 5000.0)
    silence_score = max(0.0, 100.0 - max(0.0, silence_ratio - 0.25) * 120.0)
    snr_score = min(100.0, snr_db * 4.0)
    level_score = 100.0 if -30 <= rms_dbfs <= -12 else max(25.0, 100.0 - min(abs(rms_dbfs + 21), 35) * 2.1)
    overall = round(
        0.25 * snr_score + 0.2 * clipping_score + 0.2 * silence_score + 0.2 * level_score + 0.15 * sample_rate_score
    )
    clear_speech = metadata["duration_seconds"] >= 2.0 and speech_ratio >= 0.12 and snr_db >= 6.0

    issues: list[str] = []
    if not clear_speech:
        issues.append("التسجيل لا يحتوي كلامًا واضحًا")
    if clipping_ratio > 0.005:
        issues.append("يوجد تشويه أو قص في قمم الصوت")
    if silence_ratio > 0.65:
        issues.append("نسبة الصمت مرتفعة")
    if snr_db < 12:
        issues.append("الضوضاء مرتفعة مقارنة بالصوت")
    if metadata["sample_rate"] < 16000:
        issues.append("جودة العينة منخفضة")

    return {
        **metadata,
        "analyzed_seconds": round(min(metadata["duration_seconds"], float(max_analysis_seconds)), 3),
        "rms_dbfs": round(rms_dbfs, 2),
        "peak_dbfs": round(peak_dbfs, 2),
        "noise_floor_dbfs": round(noise_floor, 2),
        "snr_db": round(snr_db, 2),
        "silence_percent": round(silence_ratio * 100, 2),
        "speech_percent": round(speech_ratio * 100, 2),
        "clipping_percent": round(clipping_ratio * 100, 4),
        "sample_quality": "ممتازة" if sample_rate_score == 100 else "جيدة" if sample_rate_score >= 80 else "منخفضة",
        "distortion": "مرتفع" if clipping_ratio > 0.02 else "ملحوظ" if clipping_ratio > 0.005 else "منخفض",
        "quality_score": max(0, min(100, overall)),
        "clear_speech": clear_speech,
        "issues": issues,
        "recommendation": "التسجيل مناسب للاستنساخ"
        if clear_speech and overall >= 55
        else "أعد التسجيل في مكان أهدأ وعلى بعد ثابت من الميكروفون",
    }


def convert_audio(input_path: Path, output_path: Path, sample_rate: int = 24000) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = _run(
        [
            _binary("ffmpeg"),
            "-y",
            "-v",
            "error",
            "-i",
            str(input_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )
    if result.returncode != 0 or not output_path.is_file() or output_path.stat().st_size < 44:
        output_path.unlink(missing_ok=True)
        raise AudioAnalysisError("فشل تحويل الملف إلى WAV")
    return output_path


def mix_audio(vocal_path: Path, instrumental_path: Path, output_path: Path, vocal_gain: float = 1.0) -> Path:
    result = _run(
        [
            _binary("ffmpeg"),
            "-y",
            "-v",
            "error",
            "-i",
            str(vocal_path),
            "-stream_loop",
            "-1",
            "-i",
            str(instrumental_path),
            "-filter_complex",
            f"[0:a]volume={max(0.1, min(3.0, vocal_gain))}[v];[1:a]volume=0.35[i];[v][i]amix=inputs=2:duration=first:dropout_transition=2",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )
    if result.returncode != 0 or not output_path.is_file():
        output_path.unlink(missing_ok=True)
        raise AudioAnalysisError("فشل مزج الصوت مع الموسيقى")
    return output_path


def apply_vocal_style(
    input_path: Path,
    output_path: Path,
    *,
    tempo: float = 1.0,
    pitch_semitones: float = 0.0,
    reverb: float = 0.0,
) -> Path:
    tempo = max(0.5, min(2.0, float(tempo)))
    pitch_semitones = max(-6.0, min(6.0, float(pitch_semitones)))
    reverb = max(0.0, min(1.0, float(reverb)))
    pitch_factor = 2 ** (pitch_semitones / 12.0)
    filters = [
        f"asetrate=48000*{pitch_factor:.8f}",
        "aresample=48000",
        f"atempo={max(0.5, min(2.0, tempo / pitch_factor)):.8f}",
    ]
    if reverb > 0.01:
        delay_ms = int(70 + 180 * reverb)
        decay = 0.15 + 0.35 * reverb
        filters.append(f"aecho=0.8:0.7:{delay_ms}:{decay:.3f}")
    result = _run(
        [
            _binary("ffmpeg"),
            "-y",
            "-v",
            "error",
            "-i",
            str(input_path),
            "-af",
            ",".join(filters),
            "-ac",
            "1",
            "-ar",
            "48000",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )
    if result.returncode != 0 or not output_path.is_file():
        output_path.unlink(missing_ok=True)
        raise AudioAnalysisError("فشل تطبيق نمط الاستوديو على الصوت")
    return output_path


def concatenate_audio(inputs: list[Path], output_path: Path) -> Path:
    if not inputs:
        raise AudioAnalysisError("لا توجد مقاطع صوتية للدمج")
    if len(inputs) == 1:
        shutil.copy2(inputs[0], output_path)
        return output_path
    descriptor_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as descriptor:
            descriptor_path = Path(descriptor.name)
            for path in inputs:
                escaped = str(path.resolve()).replace("'", "'\\''")
                descriptor.write(f"file '{escaped}'\n")
        result = _run(
            [
                _binary("ffmpeg"),
                "-y",
                "-v",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(descriptor_path),
                "-ac",
                "1",
                "-ar",
                "24000",
                "-c:a",
                "pcm_s16le",
                str(output_path),
            ],
            timeout=300,
        )
    finally:
        if descriptor_path is not None:
            descriptor_path.unlink(missing_ok=True)
    if result.returncode != 0 or not output_path.is_file():
        output_path.unlink(missing_ok=True)
        raise AudioAnalysisError("فشل دمج المقاطع الصوتية")
    return output_path
