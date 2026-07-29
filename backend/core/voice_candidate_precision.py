"""Reference-aware candidate ranking for Voice Clone Pro.

This is an acoustic similarity aid, not biometric identity verification. It uses
canonical references already approved by the profile owner and combines robust
technical quality with conservative prosody/frequency features.
"""
from __future__ import annotations

import math
import os
import tempfile
import wave
from array import array
from pathlib import Path
from statistics import median
from typing import Any

from backend.core.voice_reference_pipeline import analyze_wav, transcode_reference


def _pcm(path: Path) -> tuple[array, int]:
    with wave.open(str(path), "rb") as handle:
        if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            raise ValueError("Pitch analysis requires mono PCM16.")
        rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    values = array("h")
    values.frombytes(raw)
    if os.sys.byteorder != "little":
        values.byteswap()
    return values, rate


def estimate_pitch_hz(path: Path) -> float | None:
    """Estimate median F0 from a bounded set of voiced frames using autocorrelation."""
    samples, rate = _pcm(path)
    if rate <= 0 or len(samples) < rate // 2:
        return None
    frame_size = max(480, int(rate * 0.040))
    hop = max(frame_size, len(samples) // 48)
    minimum_lag = max(1, int(rate / 420.0))
    maximum_lag = min(frame_size - 2, int(rate / 65.0))
    pitches: list[float] = []

    for start in range(0, max(1, len(samples) - frame_size), hop):
        frame = samples[start : start + frame_size]
        if len(frame) < frame_size:
            break
        mean = sum(frame) / frame_size
        centered = [float(value) - mean for value in frame]
        energy = sum(value * value for value in centered)
        rms = math.sqrt(energy / frame_size) / 32768.0
        if rms < 0.008:
            continue

        best_lag = 0
        best_correlation = 0.0
        for lag in range(minimum_lag, maximum_lag + 1):
            numerator = 0.0
            left_energy = 0.0
            right_energy = 0.0
            limit = frame_size - lag
            for index in range(limit):
                left = centered[index]
                right = centered[index + lag]
                numerator += left * right
                left_energy += left * left
                right_energy += right * right
            denominator = math.sqrt(max(left_energy * right_energy, 1e-12))
            correlation = numerator / denominator
            if correlation > best_correlation:
                best_correlation = correlation
                best_lag = lag
        if best_lag and best_correlation >= 0.32:
            frequency = rate / best_lag
            if 65.0 <= frequency <= 420.0:
                pitches.append(frequency)

    return float(median(pitches)) if pitches else None


def _bounded_similarity(left: float, right: float, scale: float) -> float:
    return max(0.0, 1.0 - abs(left - right) / max(scale, 1e-6))


def _pitch_similarity(left: float | None, right: float | None) -> float | None:
    if not left or not right or left <= 0 or right <= 0:
        return None
    semitone_distance = abs(12.0 * math.log2(left / right))
    return max(0.0, 1.0 - semitone_distance / 12.0)


def _reference_profile(paths: list[Path]) -> dict[str, float | None]:
    metrics = []
    pitches = []
    for path in paths:
        if not path.exists():
            continue
        report = analyze_wav(path)
        metrics.append(report)
        pitch = estimate_pitch_hz(path)
        if pitch:
            pitches.append(pitch)
    if not metrics:
        raise ValueError("No canonical references are available.")

    def med(key: str) -> float:
        return float(median(float(item.get(key) or 0.0) for item in metrics))

    return {
        "pitch_hz": float(median(pitches)) if pitches else None,
        "rms": med("rms"),
        "peak": med("peak"),
        "voiced_ratio": med("voiced_ratio"),
        "zero_crossing_rate": med("zero_crossing_rate"),
        "crest_factor_db": med("crest_factor_db"),
        "snr_db_estimate": med("snr_db_estimate"),
    }


def score_candidate_against_profile(result: dict[str, Any]) -> float:
    """Mutate result with transparent score details and return normalized rank score."""
    output = Path(str(result.get("file") or ""))
    profile = result.get("profile") or {}
    profile_id = str(profile.get("id") or result.get("profile_id") or "")
    if not output.exists() or not profile_id:
        return 0.0

    # Lazy import avoids a circular dependency while the runtime patches routes.
    import backend.api.voice_clone_routes as clone

    try:
        manifest = clone._load_manifest(profile_id)
        processed = clone._profile_path(profile_id) / "processed"
        references = [processed / str(item.get("processed_file") or "") for item in manifest.get("samples") or []]
        reference = _reference_profile(references)

        with tempfile.TemporaryDirectory(prefix="clone-candidate-") as temp:
            canonical = Path(temp) / "candidate.wav"
            output_metrics = transcode_reference(output, canonical)
            output_pitch = estimate_pitch_hz(canonical)

        components: list[tuple[str, float, float]] = []
        pitch_score = _pitch_similarity(reference.get("pitch_hz"), output_pitch)
        if pitch_score is not None:
            components.append(("pitch", pitch_score, 0.35))
        components.extend(
            [
                ("voiced_ratio", _bounded_similarity(float(reference["voiced_ratio"] or 0), float(output_metrics.get("voiced_ratio") or 0), 0.55), 0.18),
                ("zero_crossing", _bounded_similarity(float(reference["zero_crossing_rate"] or 0), float(output_metrics.get("zero_crossing_rate") or 0), 0.12), 0.17),
                ("crest", _bounded_similarity(float(reference["crest_factor_db"] or 0), float(output_metrics.get("crest_factor_db") or 0), 14.0), 0.12),
                ("rms", _bounded_similarity(float(reference["rms"] or 0), float(output_metrics.get("rms") or 0), 0.20), 0.08),
                ("snr", _bounded_similarity(float(reference["snr_db_estimate"] or 0), float(output_metrics.get("snr_db_estimate") or 0), 35.0), 0.10),
            ]
        )
        weight = sum(item[2] for item in components)
        acoustic = sum(value * item_weight for _, value, item_weight in components) / max(weight, 1e-9)
        technical = float(output_metrics.get("quality_score") or 0.0) / 100.0
        final = max(0.0, min(1.0, acoustic * 0.72 + technical * 0.28))

        result["candidate_score"] = round(final, 6)
        result["acoustic_profile_similarity"] = round(acoustic, 6)
        result["technical_audio_quality"] = round(technical, 6)
        result["reference_pitch_hz"] = round(float(reference["pitch_hz"]), 2) if reference.get("pitch_hz") else None
        result["candidate_pitch_hz"] = round(float(output_pitch), 2) if output_pitch else None
        result["candidate_scoring"] = "reference-aware-acoustic-profile-v1"
        result["biometric_identity_verified"] = False
        result["score_components"] = {name: round(value, 6) for name, value, _ in components}
        return round(final, 6)
    except Exception as exc:
        result["candidate_scoring"] = "technical-fallback"
        result["candidate_scoring_warning"] = str(exc)
        try:
            with tempfile.TemporaryDirectory(prefix="clone-quality-") as temp:
                canonical = Path(temp) / "candidate.wav"
                metrics = transcode_reference(output, canonical)
            fallback = float(metrics.get("quality_score") or 0.0) / 100.0
            result["technical_audio_quality"] = round(fallback, 6)
            return round(fallback, 6)
        except Exception:
            return 0.0
