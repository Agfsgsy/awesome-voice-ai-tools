"""Advanced voice AI API routes added without replacing the existing API."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import List, Optional

import aiofiles
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend.core.config import FRONTEND_DIR, MAX_UPLOAD_MB, UPLOADS_DIR
from backend.core.logger import get_logger
from backend.voice_ai.legacy_bridge import install_legacy_clone_bridge
from backend.voice_ai.models import CloneOptions, QualityMode, SongRequest
from backend.voice_ai.numbers import normalize_numbers_in_text
from backend.voice_ai.service import voice_ai_suite

install_legacy_clone_bridge()

logger = get_logger("voice_ai_api")
router = APIRouter(tags=["Voice AI Suite"])

_ALLOWED_AUDIO = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".webm"}


async def _save_upload(file: UploadFile) -> Path:
    suffix = Path(file.filename or "audio.wav").suffix.lower()
    if suffix not in _ALLOWED_AUDIO:
        raise HTTPException(status_code=400, detail="UNSUPPORTED_AUDIO_FORMAT")
    destination = UPLOADS_DIR / f"voice_ai_{uuid.uuid4().hex}{suffix}"
    size = 0
    try:
        async with aiofiles.open(destination, "wb") as handle:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_MB * 1024 * 1024:
                    raise HTTPException(status_code=413, detail=f"FILE_TOO_LARGE: max {MAX_UPLOAD_MB}MB")
                await handle.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    if size < 128:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="INVALID_REFERENCE_AUDIO")
    return destination


@router.get("/voice-ai-studio", include_in_schema=False)
async def voice_ai_studio_page():
    page = FRONTEND_DIR / "templates" / "voice_ai_studio.html"
    if not page.exists():
        raise HTTPException(status_code=404, detail="Voice AI Studio page not installed")
    return FileResponse(str(page))


@router.get("/api/voice-ai/engines")
@router.get("/api/engines/capabilities")
async def list_voice_ai_engines():
    return {"engines": await voice_ai_suite.engine_statuses()}


@router.post("/api/voice-ai/audio/analyze")
@router.post("/api/audio/analyze")
async def analyze_uploaded_audio(file: UploadFile = File(...)):
    path = await _save_upload(file)
    try:
        return {"success": True, "analysis": await voice_ai_suite.analyze(path)}
    except Exception as exc:
        logger.exception("Audio analysis failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/voice-ai/text/numbers")
@router.post("/api/text/numbers")
async def normalize_numbers(text: str = Form(...), mode: str = Form("context")):
    return {
        "original_text": text,
        "normalized_text": normalize_numbers_in_text(text, mode=mode),
        "mode": mode,
    }


@router.post("/api/voice-ai/audio/clone/ensemble")
@router.post("/api/audio/clone/ensemble")
async def clone_voice_ensemble(
    files: List[UploadFile] = File(...),
    text: str = Form(...),
    engine: str = Form("auto"),
    language: str = Form("ar"),
    dialect: Optional[str] = Form(None),
    quality_mode: QualityMode = Form(QualityMode.balanced),
    candidate_count: int = Form(2),
    seed: Optional[int] = Form(None),
    speed: float = Form(1.0),
    reference_text: Optional[str] = Form(None),
    consent_confirmed: bool = Form(False),
    enable_similarity_scoring: bool = Form(True),
    enable_intelligibility_scoring: bool = Form(True),
    return_candidates: bool = Form(False),
):
    if not consent_confirmed:
        raise HTTPException(status_code=403, detail="CONSENT_REQUIRED")
    if not files:
        raise HTTPException(status_code=400, detail="REFERENCE_AUDIO_NOT_FOUND")
    paths = [await _save_upload(file) for file in files]
    try:
        options = CloneOptions(
            text=text,
            engine=engine,
            language=language,
            dialect=dialect,
            quality_mode=quality_mode,
            candidate_count=candidate_count,
            seed=seed,
            speed=speed,
            reference_text=reference_text,
            consent_confirmed=consent_confirmed,
            enable_similarity_scoring=enable_similarity_scoring,
            enable_intelligibility_scoring=enable_intelligibility_scoring,
            return_candidates=return_candidates,
        )
        return await voice_ai_suite.clone(paths, options)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Ensemble cloning failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/voice-ai/read/text")
@router.post("/api/read/text")
async def read_text_with_cloned_voice(
    files: List[UploadFile] = File(...),
    text: str = Form(...),
    engine: str = Form("auto"),
    language: str = Form("ar"),
    number_mode: str = Form("context"),
    speed: float = Form(1.0),
    consent_confirmed: bool = Form(False),
):
    if not consent_confirmed:
        raise HTTPException(status_code=403, detail="CONSENT_REQUIRED")
    paths = [await _save_upload(file) for file in files]
    try:
        return await voice_ai_suite.read_text(
            text=text,
            references=paths,
            engine=engine,
            language=language,
            number_mode=number_mode,
            consent_confirmed=consent_confirmed,
            speed=speed,
        )
    except Exception as exc:
        logger.exception("Reading generation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/voice-ai/song/generate")
@router.post("/api/song/generate")
async def generate_song(request: SongRequest):
    try:
        return await voice_ai_suite.generate_song(request)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Song generation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
