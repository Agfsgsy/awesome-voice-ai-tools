"""Reliable audio download/export runtime.

This module does not delete, rename, or move generated files. It replaces only the
GET download handler at application startup so every download first creates a safe
copy on the Windows Desktop, organized by provider and studio tool. The original
file remains untouched in OUTPUTS_DIR.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute

from backend.core.config import OUTPUTS_DIR
from backend.core.logger import get_logger

logger = get_logger("download_export")

_AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".opus"}
_INVALID_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _desktop_directory() -> Path:
    """Resolve the user's real Desktop without changing any existing setting."""
    candidates: list[Path] = []
    for variable in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        value = os.getenv(variable, "").strip()
        if value:
            candidates.append(Path(value) / "Desktop")
    user_profile = os.getenv("USERPROFILE", "").strip()
    if user_profile:
        candidates.append(Path(user_profile) / "Desktop")
    candidates.append(Path.home() / "Desktop")
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    fallback = Path(user_profile) / "Desktop" if user_profile else Path.home() / "Desktop"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _read_interview_engine(job_id: str) -> str:
    manifest = OUTPUTS_DIR / "interview_jobs" / job_id / "progress.json"
    if not manifest.exists():
        return ""
    try:
        payload: dict[str, Any] = json.loads(manifest.read_text(encoding="utf-8"))
        return str(payload.get("engine", "")).strip().lower()
    except Exception:
        return ""


def _related_engine(filename: str) -> str:
    """Infer provider for final files whose visible name no longer contains it."""
    low = filename.lower()
    job = re.search(r"ibn_alwaqadi_(?:podcast|interview)_([a-f0-9]{18})", low)
    if job:
        engine = _read_interview_engine(job.group(1))
        if engine:
            return engine
    dialogue = re.search(r"ibn_alwaqadi_dialogue_([a-f0-9]{10})", low)
    if dialogue:
        token = dialogue.group(1)
        if (OUTPUTS_DIR / f"ibn_alwaqadi_edge_free_{token}.wav").exists():
            return "edge"
        if (OUTPUTS_DIR / f"ibn_alwaqadi_gemini_native_strict_{token}.wav").exists():
            return "gemini"
        if (OUTPUTS_DIR / f"ibn_alwaqadi_dialogue_v3_{token}.mp3").exists():
            return "elevenlabs"
    producer = re.search(r"interview_final_([a-f0-9]{10})", low)
    if producer:
        token = producer.group(1)
        for engine in ("gemini", "elevenlabs", "edge"):
            if (OUTPUTS_DIR / f"interview_{engine}_{token}.wav").exists():
                return engine
    return ""


def _provider(filename: str) -> tuple[str, str]:
    low = filename.lower()
    engine = _related_engine(filename)
    if not engine:
        if low.startswith("yemeni_music_"):
            engine = "yemeni_music"
        elif low.startswith("gemini_") or "_gemini_" in low:
            engine = "gemini"
        elif low.startswith("edge_") or "_edge_" in low or "edge_free" in low:
            engine = "edge"
        elif low.startswith("human_pro_") or "eleven" in low or "dialogue_v3" in low:
            engine = "elevenlabs"
        elif low.startswith(("piper_", "coqui_", "kokoro_", "melotts_", "styletts2_")):
            engine = "local"
        elif low.startswith("mix_"):
            engine = "mixed"
    labels = {
        "gemini": ("Gemini", "Gemini"),
        "edge": ("الصوت المجاني", "الصوت المجاني"),
        "elevenlabs": ("ElevenLabs", "ElevenLabs"),
        "local": ("المحركات المحلية", "محرك محلي"),
        "mixed": ("المخرجات المختلطة", "مزيج صوتي"),
        "yemeni_music": ("الموسيقى اليمنية الأصلية", "موسيقى أصلية"),
    }
    return labels.get(engine, ("ملفات صوتية أخرى", "صوت"))


def _tool(filename: str) -> str:
    low = filename.lower()
    if low.startswith("yemeni_"):
        return "الإهداءات والأشعار اليمنية"
    if "ibn_alwaqadi_podcast_" in low or low.startswith("interview_"):
        return "المقابلات البشرية Pro"
    if "dialogue" in low or "edge_free" in low or "gemini_native_strict" in low:
        return "الحوار الطبيعي Ultra"
    if low.startswith("ambient_"):
        return "المنتج الصوتي - خلفية"
    if low.startswith("mix_"):
        return "المنتج الصوتي - دمج"
    if "clone" in low:
        return "استنساخ الصوت"
    if low.startswith(("gemini_", "edge_", "human_pro_", "piper_", "coqui_", "kokoro_", "melotts_", "styletts2_")):
        return "الاستوديو الكامل"
    if "effect" in low or "master" in low:
        return "المؤثرات الصوتية"
    return "ملفات الصوت"


def _safe_component(value: str) -> str:
    cleaned = _INVALID_WINDOWS_CHARS.sub("-", value).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:80] or "ملف صوتي"


def _unique_target(directory: Path, stem: str, suffix: str) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    base = _safe_component(f"{stem}_{timestamp}")
    target = directory / f"{base}{suffix.lower()}"
    counter = 2
    while target.exists():
        target = directory / f"{base}_{counter}{suffix.lower()}"
        counter += 1
    return target


def export_download_copy(source: Path) -> Path:
    """Copy one generated audio file to Desktop; never alter the source file."""
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(source)
    if source.suffix.lower() not in _AUDIO_SUFFIXES:
        raise ValueError("الملف المطلوب ليس ملفًا صوتيًا مدعومًا.")
    provider_folder, provider_label = _provider(source.name)
    tool_name = _tool(source.name)
    directory = _desktop_directory() / "استوديو ابن الواقدي" / _safe_component(provider_folder) / _safe_component(tool_name)
    directory.mkdir(parents=True, exist_ok=True)
    target = _unique_target(directory, f"{tool_name} - {provider_label}", source.suffix)
    shutil.copy2(source, target)
    if not target.exists() or target.stat().st_size != source.stat().st_size:
        target.unlink(missing_ok=True)
        raise OSError("لم تكتمل مطابقة نسخة سطح المكتب مع الملف الأصلي.")
    return target


async def _download_and_export(filename: str):
    safe = Path(filename).name
    if safe != filename or not safe:
        raise HTTPException(status_code=400, detail="اسم الملف غير صالح.")
    source = OUTPUTS_DIR / safe
    if not source.exists() or not source.is_file():
        raise HTTPException(status_code=404, detail="لم يتم العثور على الملف الصوتي.")
    download_name = source.name
    try:
        desktop_copy = export_download_copy(source)
        download_name = desktop_copy.name
        logger.info("Audio download exported to Desktop: %s", desktop_copy)
    except Exception as exc:
        logger.warning("Desktop audio export failed for %s: %s", source.name, exc)
    media_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    return FileResponse(
        str(source),
        filename=download_name,
        media_type=media_type,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


def install_download_export_runtime(app: FastAPI) -> None:
    """Replace only the existing audio download endpoint, preserving all other APIs."""
    matches = 0
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path == "/api/downloads/{filename}" and "GET" in (route.methods or set()):
            route.endpoint = _download_and_export
            route.dependant.call = _download_and_export
            matches += 1
    if matches != 1:
        raise RuntimeError(f"Expected exactly one audio download route, found {matches}.")
    logger.info("Reliable Desktop audio download export is active.")
