"""Runtime audio normalization for ultra dialogue chunk stitching.

Imported after dialogue_ultra_routes so its robust concat implementation replaces
the initial helper without changing or removing any legacy route.
"""
from __future__ import annotations

import shutil
import subprocess
import uuid
import wave
from pathlib import Path

from fastapi import HTTPException

from backend.api import dialogue_ultra_routes as dialogue
from backend.plugins.builtin.audio_effects import _ffmpeg_executable


def _silence(path: Path, milliseconds: int) -> None:
    rate = 24000
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(b"\x00\x00" * int(rate * milliseconds / 1000))


def normalized_concat(paths: list[Path], output: Path, pause_ms: int, force_mp3: bool = False) -> None:
    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        raise HTTPException(status_code=500, detail="FFmpeg غير متاح داخل البرنامج.")
    work = output.parent / f".dialogue_normalize_{uuid.uuid4().hex[:8]}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        normalized: list[Path] = []
        for index, source in enumerate(paths):
            target = work / f"part_{index:04d}.wav"
            cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-vn", "-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1", str(target)]
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
            if completed.returncode != 0 or not target.exists():
                raise HTTPException(status_code=500, detail=(completed.stderr or "فشل توحيد صيغة مقطع الحوار")[-1200:])
            normalized.append(target)
        pause = work / "pause.wav"
        _silence(pause, pause_ms)
        sequence: list[Path] = []
        for index, source in enumerate(normalized):
            sequence.append(source)
            if index < len(normalized) - 1:
                sequence.append(pause)
        manifest = work / "files.txt"
        manifest.write_text("\n".join("file '" + str(path).replace("'", "'\\''") + "'" for path in sequence), encoding="utf-8")
        codec = ["-c:a", "libmp3lame", "-b:a", "192k", "-ar", "48000", "-ac", "1"] if force_mp3 or output.suffix.lower() == ".mp3" else ["-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1"]
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), *codec, str(output)]
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, check=False)
        if completed.returncode != 0 or not output.exists():
            raise HTTPException(status_code=500, detail=(completed.stderr or "فشل دمج مشاهد الحوار")[-1400:])
    finally:
        shutil.rmtree(work, ignore_errors=True)


dialogue._concat_audio = normalized_concat
