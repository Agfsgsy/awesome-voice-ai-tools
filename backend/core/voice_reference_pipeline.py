"""Precision reference-audio pipeline for consent-based voice cloning.

The pipeline accepts every media container FFmpeg can decode, verifies that it
contains a real audio stream, converts it to XTTS-friendly mono PCM, and scores
technical quality before a sample is admitted to a voice profile.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
import wave
from array import array
from pathlib import Path
from statistics import median
from typing import Any

from backend.plugins.builtin.audio_effects import _ffmpeg_executable

COMMON_MEDIA_SUFFIXES = {
    ".wav", ".wave", ".mp3", ".mp2", ".m4a", ".m4b", ".aac", ".flac",
    ".ogg", ".oga", ".opus", ".webm", ".weba", ".amr", ".3gp", ".3g2",
    ".mp4", ".mov", ".mkv", ".avi", ".mpeg", ".mpg", ".ts", ".mts",
    ".wma", ".wmv", ".aif", ".aiff", ".aifc", ".caf", ".ac3", ".eac3",
    ".alac", ".ape", ".mka", ".m4v", ".dv", ".voc", ".au", ".snd",
}


def _run(command: list[str], timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def ffmpeg_executable() -> str:
    executable = _ffmpeg_executable()
    if not executable:
        raise RuntimeError("FFmpeg غير موجود. ثبّته ليتمكن البرنامج من قراءة التسجيلات المختلفة.")
    return str(executable)


def ffprobe_executable() -> str | None:
    ffmpeg = Path(ffmpeg_executable())
    sibling = ffmpeg.with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
    if sibling.exists():
        return str(sibling)
    return shutil.which("ffprobe")


def probe_media(path: Path) -> dict[str, Any]:
    """Return trustworthy stream/container metadata and require an audio stream."""
    probe = ffprobe_executable()
    if probe:
        completed = _run(
            [
                probe,
                "-v", "error",
                "-show_entries",
                "format=format_name,duration,size,bit_rate:stream=index,codec_type,codec_name,sample_rate,channels,channel_layout,bit_rate",
                "-of", "json",
                str(path),
            ],
            timeout=120,
        )
        if completed.returncode != 0:
            raise ValueError((completed.stderr or "تعذر قراءة الملف بواسطة FFprobe.")[-1800:])
        try:
            payload = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("أعاد FFprobe بيانات غير صالحة.") from exc
        streams = payload.get("streams") or []
        audio_streams = [item for item in streams if item.get("codec_type") == "audio"]
        if not audio_streams:
            raise ValueError("الملف لا يحتوي مسارًا صوتيًا قابلًا للقراءة.")
        audio = audio_streams[0]
        fmt = payload.get("format") or {}
        try:
            duration = float(fmt.get("duration") or 0.0)
        except (TypeError, ValueError):
            duration = 0.0
        return {
            "container": str(fmt.get("format_name") or "unknown"),
            "duration": max(0.0, duration),
            "size": int(float(fmt.get("size") or path.stat().st_size)),
            "bit_rate": int(float(fmt.get("bit_rate") or audio.get("bit_rate") or 0)),
            "codec": str(audio.get("codec_name") or "unknown"),
            "sample_rate": int(float(audio.get("sample_rate") or 0)),
            "channels": int(audio.get("channels") or 0),
            "channel_layout": str(audio.get("channel_layout") or ""),
            "audio_stream_count": len(audio_streams),
        }

    # FFmpeg still performs a real decode check when ffprobe is unavailable.
    completed = _run([ffmpeg_executable(), "-hide_banner", "-i", str(path), "-f", "null", "-"], timeout=300)
    diagnostic = (completed.stderr or completed.stdout or "")[-4000:]
    if "Audio:" not in diagnostic:
        raise ValueError("تعذر اكتشاف مسار صوتي صالح داخل الملف.")
    return {
        "container": path.suffix.lower().lstrip(".") or "unknown",
        "duration": 0.0,
        "size": path.stat().st_size,
        "bit_rate": 0,
        "codec": "ffmpeg-detected",
        "sample_rate": 0,
        "channels": 0,
        "channel_layout": "",
        "audio_stream_count": 1,
    }


def _convert(source: Path, target: Path, filter_chain: str) -> subprocess.CompletedProcess[str]:
    return _run(
        [
            ffmpeg_executable(),
            "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source),
            "-map", "0:a:0",
            "-vn", "-sn", "-dn",
            "-af", filter_chain,
            "-ar", "24000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(target),
        ],
        timeout=1800,
    )


def transcode_reference(source: Path, target: Path) -> dict[str, Any]:
    """Decode common and uncommon recordings without aggressively changing identity."""
    metadata = probe_media(source)
    target.parent.mkdir(parents=True, exist_ok=True)

    preferred = (
        "highpass=f=45,lowpass=f=12000,"
        "adeclick=w=55:o=75:a=2:t=2:b=2,"
        "afftdn=nf=-32:tn=1,"
        "silenceremove=start_periods=1:start_duration=0.10:start_threshold=-50dB:"
        "stop_periods=-1:stop_duration=0.35:stop_threshold=-50dB,"
        "loudnorm=I=-21:TP=-2:LRA=11,alimiter=limit=0.98"
    )
    conservative = (
        "highpass=f=45,lowpass=f=12000,"
        "silenceremove=start_periods=1:start_duration=0.10:start_threshold=-50dB:"
        "stop_periods=-1:stop_duration=0.35:stop_threshold=-50dB,"
        "loudnorm=I=-21:TP=-2:LRA=11"
    )

    completed = _convert(source, target, preferred)
    processing_mode = "precision-clean"
    if completed.returncode != 0:
        target.unlink(missing_ok=True)
        completed = _convert(source, target, conservative)
        processing_mode = "identity-safe-fallback"
    if completed.returncode != 0 or not target.exists() or target.stat().st_size < 2048:
        target.unlink(missing_ok=True)
        raise ValueError((completed.stderr or completed.stdout or "تعذر تحويل التسجيل الصوتي.")[-2200:])

    metrics = analyze_wav(target)
    if metrics["duration"] < 1.8:
        raise ValueError("التسجيل أقصر من ثانيتين بعد إزالة الصمت ولا يكفي لاستخراج بصمة مستقرة.")
    if metrics["voiced_ratio"] < 0.08 or metrics["rms"] < 0.002:
        raise ValueError("لم يتم اكتشاف كلام بشري واضح داخل التسجيل.")
    return {**metadata, **metrics, "processing_mode": processing_mode}


def analyze_wav(path: Path) -> dict[str, Any]:
    """Analyze canonical PCM without optional scientific dependencies."""
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.getnframes()
        raw = handle.readframes(frames)
    if channels != 1 or width != 2 or rate <= 0:
        raise ValueError("صيغة WAV المعالجة غير متوقعة؛ المطلوب PCM 16-bit mono.")

    samples = array("h")
    samples.frombytes(raw)
    if os.sys.byteorder != "little":
        samples.byteswap()
    count = len(samples)
    if not count:
        raise ValueError("التسجيل المحول فارغ.")

    sum_sq = 0.0
    sum_value = 0.0
    peak = 0
    clipped = 0
    silent = 0
    crossings = 0
    previous = samples[0]
    frame_size = max(1, int(rate * 0.020))
    frame_rms: list[float] = []
    frame_sum = 0.0
    frame_count = 0

    for value in samples:
        absolute = abs(value)
        sum_sq += float(value) * float(value)
        sum_value += value
        peak = max(peak, absolute)
        clipped += int(absolute >= 32400)
        silent += int(absolute < 220)
        crossings += int((value >= 0) != (previous >= 0))
        previous = value
        frame_sum += float(value) * float(value)
        frame_count += 1
        if frame_count >= frame_size:
            frame_rms.append(math.sqrt(frame_sum / frame_count) / 32768.0)
            frame_sum = 0.0
            frame_count = 0
    if frame_count:
        frame_rms.append(math.sqrt(frame_sum / frame_count) / 32768.0)

    rms = math.sqrt(sum_sq / count) / 32768.0
    peak_ratio = peak / 32768.0
    dc_offset = abs(sum_value / count) / 32768.0
    ordered = sorted(frame_rms) or [0.0]
    quiet_count = max(1, len(ordered) // 5)
    noise_floor = max(1e-6, median(ordered[:quiet_count]))
    active = [item for item in frame_rms if item >= max(0.006, noise_floor * 2.5)]
    voiced_ratio = len(active) / max(1, len(frame_rms))
    signal_level = median(active) if active else rms
    snr_db = max(0.0, min(60.0, 20.0 * math.log10(max(signal_level, 1e-6) / noise_floor)))
    crest_db = 20.0 * math.log10(max(peak_ratio, 1e-6) / max(rms, 1e-6))

    metrics = {
        "duration": frames / rate,
        "sample_rate": rate,
        "channels": channels,
        "rms": rms,
        "peak": peak_ratio,
        "clipping_ratio": clipped / count,
        "silence_ratio": silent / count,
        "voiced_ratio": voiced_ratio,
        "snr_db_estimate": snr_db,
        "dc_offset": dc_offset,
        "zero_crossing_rate": crossings / count,
        "crest_factor_db": crest_db,
    }
    score, label, warnings = quality_score(metrics)
    return {**metrics, "quality_score": score, "quality_label": label, "warnings": warnings}


def quality_score(metrics: dict[str, Any]) -> tuple[int, str, list[str]]:
    score = 0.0
    warnings: list[str] = []
    duration = float(metrics.get("duration") or 0.0)
    rms = float(metrics.get("rms") or 0.0)
    clipping = float(metrics.get("clipping_ratio") or 0.0)
    silence = float(metrics.get("silence_ratio") or 0.0)
    voiced = float(metrics.get("voiced_ratio") or 0.0)
    snr = float(metrics.get("snr_db_estimate") or 0.0)
    dc = float(metrics.get("dc_offset") or 0.0)

    if 20 <= duration <= 120:
        score += 25
    elif 10 <= duration < 20 or 120 < duration <= 180:
        score += 18
    elif duration >= 3:
        score += 10
        warnings.append("يفضل استخدام 20–120 ثانية من الكلام الواضح.")

    if 0.025 <= rms <= 0.24:
        score += 18
    elif 0.010 <= rms <= 0.32:
        score += 10
        warnings.append("مستوى الصوت ليس مثاليًا لكنه قابل للمعالجة.")
    else:
        warnings.append("مستوى التسجيل منخفض جدًا أو مرتفع جدًا.")

    if clipping < 0.0005:
        score += 15
    elif clipping < 0.003:
        score += 8
        warnings.append("توجد قمم مشوهة قليلة في التسجيل.")
    else:
        warnings.append("يوجد تشويه Clipping واضح؛ أعد التسجيل بصوت أقل ارتفاعًا.")

    if silence < 0.42:
        score += 10
    elif silence < 0.62:
        score += 5
        warnings.append("التسجيل يحتوي صمتًا طويلًا نسبيًا.")
    else:
        warnings.append("نسبة الصمت مرتفعة جدًا.")

    if voiced >= 0.45:
        score += 12
    elif voiced >= 0.20:
        score += 7
    else:
        warnings.append("نسبة الكلام البشري الواضح منخفضة.")

    if snr >= 24:
        score += 15
    elif snr >= 14:
        score += 8
        warnings.append("توجد ضوضاء مسموعة في الخلفية.")
    else:
        warnings.append("نسبة الإشارة إلى الضوضاء منخفضة.")

    if dc < 0.003:
        score += 5
    else:
        warnings.append("يوجد انحراف DC غير طبيعي في التسجيل.")

    final = max(0, min(100, int(round(score))))
    label = "ممتازة" if final >= 88 else "جيدة جدًا" if final >= 76 else "جيدة" if final >= 62 else "مقبولة" if final >= 48 else "تحتاج إعادة تسجيل"
    return final, label, warnings


def select_best_references(records: list[dict[str, Any]], max_files: int = 5, max_total_seconds: float = 150.0) -> list[dict[str, Any]]:
    """Prefer clean, speech-dense references while retaining useful diversity."""
    ranked = sorted(
        records,
        key=lambda item: (
            float(item.get("quality_score") or 0),
            float(item.get("voiced_ratio") or 0),
            float(item.get("snr_db_estimate") or 0),
        ),
        reverse=True,
    )
    selected: list[dict[str, Any]] = []
    total = 0.0
    for record in ranked:
        duration = float(record.get("duration") or 0.0)
        if selected and total + duration > max_total_seconds:
            continue
        selected.append(record)
        total += duration
        if len(selected) >= max_files or total >= max_total_seconds:
            break
    return selected


def score_generated_media(path: Path) -> float:
    """Technical output score used instead of choosing a candidate by file size."""
    if not path.exists() or path.stat().st_size < 1024:
        return 0.0
    with tempfile.TemporaryDirectory(prefix="voice-score-") as temp:
        canonical = Path(temp) / "candidate.wav"
        try:
            _ = transcode_reference(path, canonical)
            metrics = analyze_wav(canonical)
            return round(float(metrics.get("quality_score") or 0.0) / 100.0, 6)
        except Exception:
            return 0.0
