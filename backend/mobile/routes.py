"""طبقة API مستقلة وآمنة لتطبيق Flutter دون كسر المسارات القديمة."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.core.config import APP_NAME, APP_VERSION
from backend.core.tts_engine import tts
from backend.core.tts_registry import tts_registry
from backend.mobile.audio import AudioAnalysisError, analyze_audio, probe_audio
from backend.mobile.config import (
    MOBILE_DATA_DIR,
    MOBILE_MAX_UPLOAD_MB,
    MOBILE_PAIRING_TTL_SECONDS,
    MOBILE_REQUIRE_HTTPS_EXTERNAL,
    MOBILE_SHARE_TOKEN_SECONDS,
    MOBILE_TRUST_PROXY_HEADERS,
    MOBILE_UPLOADS_DIR,
    SUPPORTED_DOCUMENT_EXTENSIONS,
    SUPPORTED_MOBILE_AUDIO_EXTENSIONS,
)
from backend.mobile.files import MobileFileError, mobile_file_store
from backend.mobile.jobs import mobile_job_manager
from backend.mobile.schemas import (
    AuthRequest,
    PairRequest,
    PrepareEngineRequest,
    SongGenerateRequest,
    VoiceCloneRequest,
    VoiceSynthesisRequest,
)
from backend.mobile.security import MobileSecurityError, mobile_security
from backend.mobile.service import (
    clone_voice_job,
    generate_song_job,
    prepare_engine_job,
    read_document_job,
    synthesize_text,
)

router = APIRouter(prefix="/api/mobile", tags=["mobile"])
bearer = HTTPBearer(auto_error=False)
_bearer_dependency = Depends(bearer)
_required_upload = File(...)
_optional_upload = File(default=None)
_rate_lock = threading.Lock()
_pair_attempts: dict[str, deque[float]] = defaultdict(deque)
_consent_file = MOBILE_DATA_DIR / "consent_audit.jsonl"


def _is_private_client(request: Request) -> bool:
    host = request.client.host if request.client else ""
    if host in {"localhost", "testclient"}:
        return True
    try:
        address = ipaddress.ip_address(host)
        return address.is_private or address.is_loopback or address.is_link_local
    except ValueError:
        return False


def _request_scheme(request: Request) -> str:
    if MOBILE_TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
        if forwarded in {"http", "https"}:
            return forwarded
    return request.url.scheme.lower()


async def require_secure_transport(request: Request) -> None:
    if MOBILE_REQUIRE_HTTPS_EXTERNAL and not _is_private_client(request) and _request_scheme(request) != "https":
        raise HTTPException(status_code=426, detail="يجب استخدام HTTPS عند الاتصال من خارج الشبكة المحلية")


async def current_device(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = _bearer_dependency,
) -> str:
    await require_secure_transport(request)
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="تسجيل الدخول مطلوب")
    try:
        return mobile_security.verify_access_token(credentials.credentials)
    except MobileSecurityError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def _check_pair_rate_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    now = time.time()
    with _rate_lock:
        attempts = _pair_attempts[client]
        while attempts and attempts[0] < now - 60:
            attempts.popleft()
        if len(attempts) >= 10:
            raise HTTPException(status_code=429, detail="محاولات اقتران كثيرة؛ انتظر دقيقة ثم حاول مجددًا")
        attempts.append(now)


async def _store_incoming_file(
    file: UploadFile, owner_device_id: str, allowed_extensions: set[str] | None
) -> tuple[str, Path]:
    del owner_device_id
    filename = Path(file.filename or "upload.bin").name
    extension = Path(filename).suffix.lower()
    if allowed_extensions is not None and extension not in allowed_extensions:
        raise HTTPException(status_code=400, detail="صيغة الملف غير مدعومة")
    if not re.fullmatch(r"\.[a-z0-9]{1,12}", extension):
        extension = ".bin"
    token = secrets.token_urlsafe(16).replace("-", "_")
    destination = MOBILE_UPLOADS_DIR / f"mobile_{token}{extension}"
    total = 0
    try:
        with destination.open("wb") as handle:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MOBILE_MAX_UPLOAD_MB * 1024 * 1024:
                    raise HTTPException(
                        status_code=413,
                        detail=f"حجم الملف يتجاوز الحد الأقصى ({MOBILE_MAX_UPLOAD_MB} ميجابايت)",
                    )
                handle.write(chunk)
        if total == 0:
            raise HTTPException(status_code=400, detail="الملف فارغ")
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    file_id = mobile_file_store.encode_file_id("mobile", destination.name)
    return file_id, destination


def _resolve_input_file(file_id: str | None) -> Path:
    if not file_id:
        raise HTTPException(status_code=400, detail="الملف مطلوب")
    try:
        _, path = mobile_file_store.resolve_file_id(file_id)
        return path
    except MobileFileError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _provider_headers(
    gemini_key: str | None,
    gemini_model: str | None,
    elevenlabs_key: str | None,
    elevenlabs_model: str | None,
) -> dict[str, str | None]:
    return {
        "gemini_key": gemini_key.strip() if gemini_key else None,
        "gemini_model": gemini_model.strip() if gemini_model else None,
        "elevenlabs_key": elevenlabs_key.strip() if elevenlabs_key else None,
        "elevenlabs_model": elevenlabs_model.strip() if elevenlabs_model else None,
    }


@router.get("/status")
async def mobile_status(request: Request):
    return {
        "status": "online",
        "app": APP_NAME,
        "desktop_version": APP_VERSION,
        "mobile_api_version": "1.0.0",
        "server_time": datetime.now(timezone.utc).isoformat(),
        "local_client": _is_private_client(request),
        "https_required_external": MOBILE_REQUIRE_HTTPS_EXTERNAL,
        "pairing_ttl_seconds": MOBILE_PAIRING_TTL_SECONDS,
        "max_upload_mb": MOBILE_MAX_UPLOAD_MB,
        "audio_formats": {
            "common_extensions": sorted(SUPPORTED_MOBILE_AUDIO_EXTENSIONS),
            "additional_ffmpeg_decodable_formats": True,
        },
        "capabilities": {
            "pairing": True,
            "resumable_uploads": True,
            "job_cancellation": True,
            "audio_analysis": True,
            "voice_cloning": True,
            "document_reader": True,
            "song_studio": True,
        },
    }


@router.post("/pair")
async def mobile_pair(payload: PairRequest, request: Request):
    await require_secure_transport(request)
    _check_pair_rate_limit(request)
    try:
        return mobile_security.pair_device(
            pairing_id=payload.pairing_id,
            code=payload.pairing_code,
            device_name=payload.device_name,
            platform_name=payload.platform,
            app_version=payload.app_version,
        )
    except MobileSecurityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/auth")
async def mobile_auth(payload: AuthRequest, request: Request):
    await require_secure_transport(request)
    try:
        token = mobile_security.authenticate_device(payload.device_id, payload.device_token)
    except MobileSecurityError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {**token, "device_id": payload.device_id}


@router.get("/engines")
async def mobile_engines(device_id: str = Depends(current_device)):
    del device_id
    engines = []
    for plugin in tts_registry.get_all_plugins():
        try:
            health = plugin.health()
            models = plugin.list_models()
            downloading = any(path.suffix in {".part", ".tmp"} for path in plugin.models_dir.glob("*"))
            downloaded = any(bool(model.get("downloaded")) for model in models if isinstance(model, dict))
            ready = bool(health.get("installed")) and (downloaded or not models)
            engines.append({**health, "ready": ready, "models": models, "downloading": downloading})
        # عزل فشل إضافة واحدة حتى تبقى حالة بقية المحركات متاحة للمستخدم.
        except Exception as exc:  # noqa: BLE001
            engines.append(
                {
                    "name": getattr(plugin, "name", "unknown"),
                    "label": getattr(plugin, "label", "محرك غير معروف"),
                    "installed": False,
                    "ready": False,
                    "downloading": False,
                    "models": [],
                    "error": str(exc),
                }
            )
    builtin_names = {item["name"] for item in engines}
    for item in tts.list_engines():
        if item["name"] not in builtin_names:
            engines.append({**item, "ready": item.get("available", False), "models": [], "downloading": False})
    for provider_name, provider_label in (("elevenlabs", "ElevenLabs"), ("gemini", "Google Gemini TTS")):
        provider = next((item for item in engines if item["name"] == provider_name), None)
        details = {
            "name": provider_name,
            "label": provider_label,
            "ready": True,
            "external": True,
            "requires_api_key": True,
            "models": [],
            "downloading": False,
        }
        if provider is None:
            engines.append(details)
        else:
            provider.update(details)
    return {"engines": engines, "count": len(engines)}


@router.post("/engines/{engine}/prepare", status_code=202)
async def mobile_prepare_engine(
    engine: str,
    payload: PrepareEngineRequest,
    device_id: str = Depends(current_device),
):
    async def runner(context):
        return await prepare_engine_job(context, engine=engine, model_name=payload.model_name)

    job = await mobile_job_manager.create("engine_prepare", device_id, runner)
    return job.to_dict()


@router.post("/uploads")
async def mobile_resumable_upload(
    file: UploadFile = _required_upload,
    upload_id: str = Form(...),
    filename: str = Form(...),
    offset: int = Form(...),
    total_size: int = Form(...),
    device_id: str = Depends(current_device),
):
    chunk = await file.read(6 * 1024 * 1024)
    if await file.read(1):
        raise HTTPException(status_code=413, detail="حجم الجزء الواحد يتجاوز 6 ميجابايت")
    try:
        return mobile_file_store.append_upload(
            upload_id=upload_id,
            owner_device_id=device_id,
            filename=filename,
            offset=offset,
            total_size=total_size,
            chunk=chunk,
        )
    except MobileFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/uploads/{upload_id}")
async def mobile_upload_status(upload_id: str, device_id: str = Depends(current_device)):
    try:
        return mobile_file_store.upload_status(upload_id, device_id)
    except MobileFileError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/reference/analyze")
async def mobile_reference_analyze(
    file: UploadFile | None = _optional_upload,
    file_id: str | None = Form(default=None),
    device_id: str = Depends(current_device),
):
    selected_file_id = file_id
    if file is not None:
        selected_file_id, path = await _store_incoming_file(file, device_id, None)
    else:
        path = _resolve_input_file(file_id)
    try:
        analysis = await asyncio.to_thread(analyze_audio, path)
    except AudioAnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"file_id": selected_file_id, "analysis": analysis}


@router.post("/voice/clone", status_code=202)
async def mobile_voice_clone(payload: VoiceCloneRequest, device_id: str = Depends(current_device)):
    if not payload.consent_confirmed:
        raise HTTPException(status_code=403, detail="يجب تأكيد ملكية الصوت أو وجود إذن صريح قبل الاستنساخ")
    reference = _resolve_input_file(payload.reference_file_id)
    try:
        probe_audio(reference)
    except AudioAnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "device_id": device_id,
        "voice_rights": payload.voice_rights,
        "statement_hash": hashlib.sha256(payload.consent_statement.encode("utf-8")).hexdigest(),
        "reference_hash": hashlib.sha256(reference.read_bytes()).hexdigest(),
    }
    _consent_file.parent.mkdir(parents=True, exist_ok=True)
    with _consent_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(audit, ensure_ascii=False) + "\n")

    async def runner(context):
        return await clone_voice_job(
            context,
            reference_file_id=payload.reference_file_id,
            text=payload.text,
            engine=payload.engine,
            language=payload.language,
            candidate_count=payload.candidate_count,
        )

    job = await mobile_job_manager.create("voice_clone", device_id, runner)
    return job.to_dict()


@router.post("/voice/synthesize", status_code=202)
async def mobile_voice_synthesize(
    payload: VoiceSynthesisRequest,
    device_id: str = Depends(current_device),
    gemini_key: str | None = Header(default=None, alias="X-Gemini-Api-Key"),
    gemini_model: str | None = Header(default=None, alias="X-Gemini-Model"),
    elevenlabs_key: str | None = Header(default=None, alias="X-ElevenLabs-Api-Key"),
    elevenlabs_model: str | None = Header(default=None, alias="X-ElevenLabs-Model"),
):
    providers = _provider_headers(gemini_key, gemini_model, elevenlabs_key, elevenlabs_model)

    async def runner(context):
        candidates = []
        for index in range(payload.candidate_count):
            context.raise_if_cancelled()
            await context.update(5 + int(index / payload.candidate_count * 85), f"جارٍ إنشاء المرشح {index + 1}")
            path = await synthesize_text(
                text=payload.text,
                engine=payload.engine,
                language=payload.language,
                voice=payload.voice,
                speed=payload.speed,
                output_hint="mobile_tts",
                index=index,
                **providers,
            )
            file_id = mobile_file_store.encode_file_id("output", path.name)
            candidates.append(
                {
                    "candidate_id": f"{context.job_id}-{index + 1}",
                    "file_id": file_id,
                    "name": path.name,
                    "url": f"/api/mobile/files/{file_id}",
                }
            )
        return {"candidates": candidates, "best_candidate_id": candidates[0]["candidate_id"]}

    job = await mobile_job_manager.create("voice_synthesis", device_id, runner)
    return job.to_dict()


@router.get("/jobs/{job_id}")
async def mobile_job(job_id: str, device_id: str = Depends(current_device)):
    try:
        return mobile_job_manager.get(job_id, device_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="المهمة غير موجودة") from exc


@router.post("/jobs/{job_id}/cancel")
async def mobile_cancel_job(job_id: str, device_id: str = Depends(current_device)):
    try:
        job = await mobile_job_manager.cancel(job_id, device_id)
        return job.to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="المهمة غير موجودة") from exc


@router.get("/files")
async def mobile_files(device_id: str = Depends(current_device)):
    del device_id
    files = mobile_file_store.list_files()
    return {"files": files, "count": len(files)}


@router.get("/files/{file_id}")
async def mobile_download_file(
    file_id: str,
    request: Request,
    share_token: str | None = None,
    credentials: HTTPAuthorizationCredentials | None = _bearer_dependency,
):
    await require_secure_transport(request)
    shared = bool(share_token and mobile_security.verify_share_token(share_token, file_id))
    if not shared:
        if credentials is None:
            raise HTTPException(status_code=401, detail="تسجيل الدخول مطلوب")
        try:
            mobile_security.verify_access_token(credentials.credentials)
        except MobileSecurityError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
    try:
        _, path = mobile_file_store.resolve_file_id(file_id)
    except MobileFileError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path=str(path), filename=path.name)


@router.post("/files/{file_id}/share")
async def mobile_share_file(file_id: str, request: Request, device_id: str = Depends(current_device)):
    del device_id
    try:
        mobile_file_store.resolve_file_id(file_id)
    except MobileFileError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    token = mobile_security.create_share_token(file_id)
    url = str(request.url_for("mobile_download_file", file_id=file_id))
    return {"share_url": f"{url}?share_token={token}", "expires_in": MOBILE_SHARE_TOKEN_SECONDS}


@router.delete("/files/{file_id}")
async def mobile_delete_file(file_id: str, device_id: str = Depends(current_device)):
    del device_id
    try:
        return mobile_file_store.delete(file_id)
    except MobileFileError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/read/document", status_code=202)
async def mobile_read_document(
    file: UploadFile | None = _optional_upload,
    file_id: str | None = Form(default=None),
    text: str | None = Form(default=None),
    engine: str = Form(default="auto"),
    language: str = Form(default="ar"),
    voice: str = Form(default="default"),
    speed: float = Form(default=1.0),
    normalize_numbers: bool = Form(default=True),
    device_id: str = Depends(current_device),
    gemini_key: str | None = Header(default=None, alias="X-Gemini-Api-Key"),
    gemini_model: str | None = Header(default=None, alias="X-Gemini-Model"),
    elevenlabs_key: str | None = Header(default=None, alias="X-ElevenLabs-Api-Key"),
    elevenlabs_model: str | None = Header(default=None, alias="X-ElevenLabs-Model"),
):
    if not 0.5 <= speed <= 2.0:
        raise HTTPException(status_code=400, detail="سرعة القراءة يجب أن تكون بين 0.5 و2.0")
    if file is not None:
        _, document_path = await _store_incoming_file(file, device_id, SUPPORTED_DOCUMENT_EXTENSIONS)
    elif file_id:
        document_path = _resolve_input_file(file_id)
        if document_path.suffix.lower() not in SUPPORTED_DOCUMENT_EXTENSIONS:
            raise HTTPException(status_code=400, detail="صيغة المستند غير مدعومة")
    elif text and text.strip():
        document_path = MOBILE_UPLOADS_DIR / f"reader_{secrets.token_urlsafe(12)}.txt"
        document_path.write_text(text.strip(), encoding="utf-8")
    else:
        raise HTTPException(status_code=400, detail="أدخل نصًا أو اختر مستندًا")
    providers = _provider_headers(gemini_key, gemini_model, elevenlabs_key, elevenlabs_model)

    async def runner(context):
        return await read_document_job(
            context,
            document_path=document_path,
            engine=engine,
            language=language,
            voice=voice,
            speed=speed,
            normalize_numbers=normalize_numbers,
            **providers,
        )

    job = await mobile_job_manager.create("document_read", device_id, runner)
    return job.to_dict()


@router.post("/song/generate", status_code=202)
async def mobile_song_generate(
    payload: SongGenerateRequest,
    device_id: str = Depends(current_device),
    gemini_key: str | None = Header(default=None, alias="X-Gemini-Api-Key"),
    gemini_model: str | None = Header(default=None, alias="X-Gemini-Model"),
    elevenlabs_key: str | None = Header(default=None, alias="X-ElevenLabs-Api-Key"),
    elevenlabs_model: str | None = Header(default=None, alias="X-ElevenLabs-Model"),
):
    if payload.instrumental_file_id:
        _resolve_input_file(payload.instrumental_file_id)
    providers = _provider_headers(gemini_key, gemini_model, elevenlabs_key, elevenlabs_model)

    async def runner(context):
        return await generate_song_job(
            context,
            lyrics=payload.lyrics,
            title=payload.title,
            style=payload.style,
            engine=payload.engine,
            language=payload.language,
            voice=payload.voice,
            candidate_count=payload.candidate_count,
            tempo=payload.tempo,
            pitch_semitones=payload.pitch_semitones,
            reverb=payload.reverb,
            instrumental_file_id=payload.instrumental_file_id,
            **providers,
        )

    job = await mobile_job_manager.create("song_generate", device_id, runner)
    return job.to_dict()


@router.get("/storage")
async def mobile_storage(device_id: str = Depends(current_device)):
    del device_id
    usage = os.statvfs(MOBILE_DATA_DIR)
    free = usage.f_bavail * usage.f_frsize
    total = usage.f_blocks * usage.f_frsize
    return {"free_bytes": free, "total_bytes": total, "enough_for_upload": free > MOBILE_MAX_UPLOAD_MB * 1024 * 1024}
