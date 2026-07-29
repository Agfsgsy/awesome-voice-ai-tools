from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from backend.core.voice_reference_pipeline import analyze_wav, select_best_references


def _write_tone(path: Path, *, seconds: float = 2.5, rate: int = 24000, amplitude: float = 0.18) -> None:
    frames = int(seconds * rate)
    values = []
    for index in range(frames):
        envelope = min(1.0, index / max(1, int(rate * 0.05)), (frames - index) / max(1, int(rate * 0.05)))
        value = int(32767 * amplitude * envelope * math.sin(2 * math.pi * 180 * index / rate))
        values.append(value)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(struct.pack(f"<{len(values)}h", *values))


def test_analyze_wav_reports_real_metrics(tmp_path: Path) -> None:
    sample = tmp_path / "sample.wav"
    _write_tone(sample)
    report = analyze_wav(sample)
    assert 2.4 <= report["duration"] <= 2.6
    assert report["sample_rate"] == 24000
    assert report["channels"] == 1
    assert report["rms"] > 0.01
    assert report["peak"] < 0.25
    assert report["clipping_ratio"] == 0
    assert 0 <= report["quality_score"] <= 100
    assert report["quality_label"]


def test_reference_selection_prefers_quality_and_limits_duration() -> None:
    records = [
        {"sample_index": 1, "quality_score": 52, "voiced_ratio": 0.7, "snr_db_estimate": 15, "duration": 80},
        {"sample_index": 2, "quality_score": 91, "voiced_ratio": 0.8, "snr_db_estimate": 29, "duration": 50},
        {"sample_index": 3, "quality_score": 84, "voiced_ratio": 0.75, "snr_db_estimate": 25, "duration": 60},
        {"sample_index": 4, "quality_score": 78, "voiced_ratio": 0.65, "snr_db_estimate": 23, "duration": 45},
    ]
    selected = select_best_references(records, max_files=3, max_total_seconds=120)
    assert [item["sample_index"] for item in selected] == [2, 3]
    assert sum(item["duration"] for item in selected) <= 120
