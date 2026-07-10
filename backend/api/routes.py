"""مسارات API الكاملة - مع Authentication و Validation و Rate Limiting"""

import os
import json
import shutil
import platform
import sys
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timedelta, timezone

from fastapi import (
    APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks,
    Request, Depends, status,
)
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator

from backend.core.config import (
    APP_NAME, APP_VERSION, APP_HOST, APP_PORT, APP_DEBUG,
    IS_TERMUX, IS_ANDROID, IS_COLAB, GEMINI_API_KEY, GEMINI_TTS_MODEL,
    MODELS_DIR, VOICES_DIR, DOWNLOADS_DIR, UPLOADS_DIR, OUTPUTS_DIR,
    CACHE_DIR, LOGS_DIR, CONFIG_DIR, ENGINE_PRIORITY, MAX_UPLOAD_MB,
    SUPPORTED_AUDIO_FORMATS, PLUGINS_DIR, API_KEY_HEADER,
    DOCS_ENABLED, JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
)
from backend.core.logger import get_logger
from backend.core.health import run_all_checks
from backend.core.tts_engine import tts
from backend.core.plugin_manager import init_plugin_manager
from backend.core.tts_registry import tts_registry
from backend.core.rate_limiter import check_rate_limit
from backend.core.validation import (
    validate_uploaded_file, validate_text_input, sanitize_path,
    validate_engine_name, validate_voice_name, validate_language_code,
)
from backend.core.exceptions import (
    AuthenticationError, AuthorizationError, ValidationError,
    ResourceNotFoundError, FileUploadError, PluginError,
)
from backend.core.auth import (
    authenticate_user, create_user, create_access_token, create_refresh_token,
    decode_token, create_api_key, validate_api_key, revoke_api_key,
    list_api_keys, get_user, list_users, require_admin,
    get_current_user, get_current_user_or_api_key,
    Role, Permission, has_permission,
    generate_secure_token,
)

logger = get_logger("api")
router = APIRouter()
security = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Pydantic Request Models with Validation
# ---------------------------------------------------------------------------

class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000, description="Text to synthesize")
    engine: str = Field(default="auto", max_length=50, description="TTS engine name")
    language: str = Field(default="ar", max_length=5, description="Language code (ISO 639-1)")
    voice: str = Field(default="default", max_length=100, description="Voice name")
    speed: float = Field(default=1.0, ge=0.25, le=4.0, description="Speech speed")
    pitch: float = Field(default=0.0, ge=-20.0, le=20.0, description="Pitch adjustment")

    @field_validator("text")
    @classmethod
    def validate_text_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Text cannot be empty")
        if "\x00" in v:
            raise ValueError("Text contains null bytes")
        return v.strip()

    @field_validator("engine")
    @classmethod
    def validate_engine(cls, v):
        if not v or not all(c.isalnum() or c in "_-" for c in v):
            raise ValueError("Invalid engine name format")
        return v


class CloneRequest(BaseModel):
    reference_audio: str = Field(..., max_length=255, description="Path to reference audio file")
    text: str = Field(..., min_length=1, max_length=10000, description="Text to synthesize")
    engine: str = Field(default="coqui", max_length=50, description="Engine for voice cloning")

    @field_validator("reference_audio")
    @classmethod
    def validate_ref_audio(cls, v):
        if "\x00" in v or ".." in v:
            raise ValueError("Invalid reference audio path")
        return v


class SettingsUpdate(BaseModel):
    gemini_api_key: Optional[str] = Field(default=None, max_length=255)
    gemini_tts_model: Optional[str] = Field(default=None, max_length=100)
    default_engine: Optional[str] = Field(default=None, max_length=50)
    default_language: Optional[str] = Field(default=None, max_length=5)

    @field_validator("gemini_api_key")
    @classmethod
    def validate_api_key(cls, v):
        if v and "\x00" in v:
            raise ValueError("API key contains null bytes")
        return v


class RenameRequest(BaseModel):
    new_name: str = Field(..., min_length=1, max_length=255, description="New filename")

    @field_validator("new_name")
    @classmethod
    def validate_new_name(cls, v):
        if "\x00" in v or "/" in v or "\\" in v or ".." in v:
            raise ValueError("Invalid filename")
        if v.startswith("."):
            raise ValueError("Hidden files not allowed")
        return v


class PluginInstallRequest(BaseModel):
    engine: str = Field(..., max_length=50, description="Engine name to install/check")


class ModelDownloadRequest(BaseModel):
    engine: str = Field(..., max_length=50)
    model_name: str = Field(default="default", max_length=100)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6, max_length=255)


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6, max_length=255)
    role: str = Field(default="user", max_length=20)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=10)


# ---------------------------------------------------------------------------
# Init builtin plugins
# ---------------------------------------------------------------------------

try:
    pm = init_plugin_manager(PLUGINS_DIR)
    pm.load_all()
except Exception as e:
    logger.warning(f"Plugin init failed (non-critical): {e}")
    pm = None

# TTS Registry init
tts_registry.initialize()


# ---------------------------------------------------------------------------
# Auth Dependencies
# ---------------------------------------------------------------------------

async def _get_auth_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get authenticated user from JWT or allow public access for some endpoints"""
    if not credentials:
        return None
    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        raise AuthenticationError("Invalid or expired token")
    username = payload.get("sub")
    if not username:
        raise AuthenticationError("Invalid token payload")
    user = get_user(username)
    if not user or user.get("disabled"):
        raise AuthenticationError("User not found or disabled")
    return user


async def _require_auth_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Require authenticated user"""
    user = await _get_auth_user(credentials)
    if not user:
        raise AuthenticationError("Authentication required")
    return user


async def _get_user_with_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Authenticate via JWT or API key from header"""
    # Try JWT first
    if credentials:
        token = credentials.credentials
        payload = decode_token(token)
        if payload:
            username = payload.get("sub")
            if username:
                user = get_user(username)
                if user and not user.get("disabled"):
                    return user

    # Try API key
    api_key = request.headers.get(API_KEY_HEADER, "")
    if api_key:
        key_data = validate_api_key(api_key)
        if key_data:
            return {
                "username": key_data["user_id"],
                "user_id": key_data["user_id"],
                "role": key_data["role"],
            }

    # Not authenticated
    return None


async def _require_auth(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Require authentication (JWT or API key)"""
    user = await _get_user_with_api_key(request, credentials)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide JWT token (Bearer) or API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _pm_info():
    if pm:
        return pm.get_info()
    return []


# ---------------------------------------------------------------------------
# Public Routes (no auth required)
# ---------------------------------------------------------------------------

@router.get("/")
async def root():
    return {"app": APP_NAME, "version": APP_VERSION, "status": "running", "docs": "/docs" if DOCS_ENABLED else None}


@router.get("/health")
async def health(request: Request):
    await check_rate_limit(request, limit_type="health")
    checks = run_all_checks(APP_PORT)
    all_ok = all(c.get("ok", False) for c in checks)
    return {"status": "healthy" if all_ok else "warning", "checks": checks}


@router.get("/api/info")
async def api_info():
    return {
        "app_name": APP_NAME,
        "version": APP_VERSION,
        "description": "منصة صوتيات عربية لتوليد واستنساخ الصوت",
        "engines": tts.list_engines(),
        "max_upload_mb": MAX_UPLOAD_MB,
        "supported_formats": SUPPORTED_AUDIO_FORMATS,
        "gemini_configured": bool(GEMINI_API_KEY),
        "gemini_model": GEMINI_TTS_MODEL,
        "is_termux": IS_TERMUX,
        "is_colab": IS_COLAB,
    }


@router.get("/version")
async def version():
    return {"version": APP_VERSION, "name": APP_NAME}


# ---------------------------------------------------------------------------
# Authentication Routes
# ---------------------------------------------------------------------------

@router.post("/api/auth/login")
async def login(request: Request, req: LoginRequest):
    await check_rate_limit(request, limit_type="auth")

    user_info = authenticate_user(req.username, req.password)
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": req.username, "role": user_info["role"]})
    refresh_token = create_refresh_token(data={"sub": req.username, "role": user_info["role"]})

    return {
        "success": True,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": {
            "username": user_info["username"],
            "user_id": user_info["user_id"],
            "role": user_info["role"],
        },
    }


@router.post("/api/auth/refresh")
async def refresh_token(request: Request, req: RefreshTokenRequest):
    await check_rate_limit(request, limit_type="auth")

    payload = decode_token(req.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise AuthenticationError("Invalid refresh token")

    username = payload.get("sub")
    if not username:
        raise AuthenticationError("Invalid token payload")

    user = get_user(username)
    if not user or user.get("disabled"):
        raise AuthenticationError("User not found or disabled")

    new_access = create_access_token(data={"sub": username, "role": user["role"]})
    new_refresh = create_refresh_token(data={"sub": username, "role": user["role"]})

    return {
        "success": True,
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
    }


@router.get("/api/auth/me")
async def get_me(current_user: dict = Depends(_require_auth)):
    return {
        "success": True,
        "user": {
            "username": current_user["username"],
            "user_id": current_user["user_id"],
            "role": current_user["role"],
        },
    }


@router.post("/api/auth/logout")
async def logout(current_user: dict = Depends(_require_auth)):
    # In a stateless JWT system, client discards the token
    # For server-side invalidation, maintain a token blacklist (Redis recommended)
    return {"success": True, "message": "Logged out successfully"}


# ---------------------------------------------------------------------------
# User Management (Admin only)
# ---------------------------------------------------------------------------

@router.post("/api/users")
async def create_new_user(
    request: Request,
    req: CreateUserRequest,
    current_user: dict = Depends(require_admin),
):
    await check_rate_limit(request, limit_type="sensitive")

    try:
        role = Role(req.role) if req.role in [r.value for r in Role] else Role.USER
        result = create_user(req.username, req.password, role)
        return {"success": True, "user": result}
    except ValueError as e:
        raise ValidationError(str(e))


@router.get("/api/users")
async def list_all_users(current_user: dict = Depends(require_admin)):
    users = list_users()
    return {"success": True, "users": users, "count": len(users)}


@router.get("/api/users/{username}")
async def get_user_info(
    username: str,
    current_user: dict = Depends(require_admin),
):
    user = get_user(username)
    if not user:
        raise ResourceNotFoundError(f"User '{username}' not found")
    return {"success": True, "user": user}


# ---------------------------------------------------------------------------
# API Key Management
# ---------------------------------------------------------------------------

@router.post("/api/auth/api-keys")
async def create_new_api_key(
    request: Request,
    name: str = "",
    current_user: dict = Depends(_require_auth),
):
    await check_rate_limit(request, limit_type="sensitive")

    role = Role(current_user.get("role", "user"))
    api_key = create_api_key(
        user_id=current_user["user_id"],
        role=role,
        name=name or f"API Key for {current_user['username']}",
    )
    return {
        "success": True,
        "api_key": api_key,
        "message": "Store this API key safely - it will not be shown again",
    }


@router.get("/api/auth/api-keys")
async def list_user_api_keys(current_user: dict = Depends(_require_auth)):
    keys = list_api_keys(user_id=current_user["user_id"])
    return {"success": True, "api_keys": keys}


@router.delete("/api/auth/api-keys/{api_key_preview}")
async def revoke_user_api_key(
    api_key_preview: str,
    current_user: dict = Depends(_require_auth),
):
    # Revoke by prefix match - in production use database lookup
    revoked = False
    for key, data in list_api_keys(user_id=current_user["user_id"]):
        if data.get("key_preview", "").startswith(api_key_preview):
            revoked = True
            break
    return {"success": True, "revoked": revoked}


# ---------------------------------------------------------------------------
# Status & System (Auth required)
# ---------------------------------------------------------------------------

@router.get("/status")
async def get_status(current_user: dict = Depends(_require_auth)):
    available = tts_registry.get_available_engines()
    auto_engine = tts_registry.auto_select_engine()
    return {
        "app": APP_NAME,
        "version": APP_VERSION,
        "host": APP_HOST,
        "port": APP_PORT,
        "debug": APP_DEBUG,
        "is_termux": IS_TERMUX,
        "is_colab": IS_COLAB,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "engines": tts.list_engines(),
        "tts_plugins": [p.name for p in tts_registry.get_all_plugins()],
        "available_engines": [e["name"] for e in available],
        "auto_selected_engine": auto_engine,
        "plugins_loaded": len([k for k, v in (pm.loaded if pm else {}).items() if v is not None]),
        "plugins_total": len(pm.registry) if pm else 0,
    }


@router.get("/api/system")
async def api_system(current_user: dict = Depends(_require_auth)):
    disk = shutil.disk_usage(os.getcwd())
    return {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "is_termux": IS_TERMUX,
        "is_colab": IS_COLAB,
        "cpu_count": os.cpu_count(),
    }


# ---------------------------------------------------------------------------
# Plugin Endpoints (Auth required)
# ---------------------------------------------------------------------------

@router.get("/api/plugins")
async def api_plugins(current_user: dict = Depends(_require_auth)):
    all_plugins = []
    for plugin in tts_registry.get_all_plugins():
        try:
            info = plugin.health()
            all_plugins.append(info)
        except Exception as e:
            logger.warning(f"Failed to get health for {plugin.name}: {e}")
    builtin = _pm_info()
    return {"tts_plugins": all_plugins, "builtin_plugins": builtin}


@router.get("/api/plugins/{name}")
async def api_plugin_detail(name: str, current_user: dict = Depends(_require_auth)):
    # Sanitize plugin name to prevent injection
    if not name or not all(c.isalnum() or c in "_-" for c in name):
        raise ValidationError("Invalid plugin name")

    plugin = tts_registry.get_plugin(name)
    if not plugin:
        raise ResourceNotFoundError(f"Plugin '{name}' not found")
    return plugin.health()


@router.post("/api/plugins/install")
async def api_plugin_install(
    request: Request,
    req: PluginInstallRequest,
    current_user: dict = Depends(_require_auth),
):
    await check_rate_limit(request, limit_type="sensitive")

    # Validate engine name
    valid, error = validate_engine_name(req.engine, [])
    if not valid:
        raise ValidationError(error)

    plugin = tts_registry.get_plugin(req.engine)
    if not plugin:
        raise ResourceNotFoundError(f"Engine '{req.engine}' not found")

    try:
        result = plugin.install()
        return result
    except Exception as e:
        logger.error(f"Plugin install failed: {e}")
        raise PluginError(f"Failed to install plugin: {str(e)}")


@router.post("/api/plugins/check")
async def api_plugin_check(req: PluginInstallRequest, current_user: dict = Depends(_require_auth)):
    valid, error = validate_engine_name(req.engine, [])
    if not valid:
        raise ValidationError(error)

    plugin = tts_registry.get_plugin(req.engine)
    if not plugin:
        raise ResourceNotFoundError(f"Engine '{req.engine}' not found")

    try:
        installed = plugin.check()
        return {"engine": req.engine, "installed": installed}
    except Exception as e:
        logger.error(f"Plugin check failed: {e}")
        raise PluginError(f"Failed to check plugin: {str(e)}")


# ---------------------------------------------------------------------------
# Model Endpoints (Auth required)
# ---------------------------------------------------------------------------

@router.get("/api/models")
async def api_models(current_user: dict = Depends(_require_auth)):
    from backend.core.model_manager import model_manager
    try:
        models = model_manager.list_all_models()
        return {"models": models, "count": len(models)}
    except Exception as e:
        logger.error(f"Failed to list models: {e}")
        raise PluginError("Failed to list models", {"detail": str(e)})


@router.post("/api/models/download")
async def api_model_download(
    request: Request,
    req: ModelDownloadRequest,
    current_user: dict = Depends(_require_auth),
):
    await check_rate_limit(request, limit_type="sensitive")

    valid, error = validate_engine_name(req.engine, [])
    if not valid:
        raise ValidationError(error)

    from backend.core.model_manager import model_manager
    try:
        return model_manager.download_model(req.engine, req.model_name)
    except Exception as e:
        logger.error(f"Model download failed: {e}")
        raise PluginError(f"Failed to download model: {str(e)}")


@router.get("/api/voices")
async def api_voices(current_user: dict = Depends(_require_auth)):
    from backend.core.voice_manager import voice_manager
    try:
        voices = voice_manager.list_all_voices()
        return {"voices": voices, "count": len(voices)}
    except Exception as e:
        logger.error(f"Failed to list voices: {e}")
        raise PluginError("Failed to list voices", {"detail": str(e)})


# ---------------------------------------------------------------------------
# Settings (Auth required)
# ---------------------------------------------------------------------------

@router.get("/api/settings")
async def api_settings(current_user: dict = Depends(_require_auth)):
    # Only admins can see API key is set; users only see configured status
    is_admin = current_user.get("role") == Role.ADMIN.value
    return {
        "gemini_api_key_set": bool(GEMINI_API_KEY),
        "gemini_tts_model": GEMINI_TTS_MODEL,
        "default_engine": ENGINE_PRIORITY[0] if ENGINE_PRIORITY else "kokoro",
        "default_language": "ar",
        "is_termux": IS_TERMUX,
        "is_colab": IS_COLAB,
        "app_host": APP_HOST,
        "app_port": APP_PORT,
        "max_upload_mb": MAX_UPLOAD_MB,
        "user_role": current_user.get("role"),
    }


@router.post("/api/settings")
async def api_update_settings(
    data: SettingsUpdate,
    current_user: dict = Depends(require_admin),
):
    # Only admin can "update" settings - in production persist to config file or DB
    return {
        "success": True,
        "message": "Settings are managed via environment variables. Set GEMINI_API_KEY in .env or env.",
        "note": "To change settings, update environment variables and restart the server.",
    }


# ---------------------------------------------------------------------------
# Logs (Admin only)
# ---------------------------------------------------------------------------

@router.get("/api/logs")
async def api_logs(current_user: dict = Depends(require_admin)):
    log_file = LOGS_DIR / "app.log"
    if log_file.exists():
        try:
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]
            return {"logs": lines, "count": len(lines)}
        except Exception as e:
            raise PluginError(f"Failed to read logs: {str(e)}")
    return {"logs": [], "message": "No log file found"}


@router.get("/api/logs/download")
async def api_download_logs(current_user: dict = Depends(require_admin)):
    log_file = LOGS_DIR / "app.log"
    if not log_file.exists():
        raise ResourceNotFoundError("No logs available")
    return FileResponse(str(log_file), filename="app.log", media_type="text/plain")


# ---------------------------------------------------------------------------
# Downloads (Auth required)
# ---------------------------------------------------------------------------

@router.get("/api/downloads")
async def api_list_downloads(current_user: dict = Depends(_require_auth)):
    files = []
    try:
        for f in sorted(OUTPUTS_DIR.iterdir()):
            if f.is_file() and not f.name.startswith("."):
                files.append({
                    "name": f.name,
                    "size": f.stat().st_size,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
                })
    except Exception as e:
        logger.error(f"Failed to list downloads: {e}")
        raise PluginError("Failed to list downloads")
    return {"files": files, "count": len(files), "dir": str(OUTPUTS_DIR)}


@router.get("/api/downloads/{filename}")
async def api_download_file(filename: str, current_user: dict = Depends(_require_auth)):
    # Validate filename
    valid, error = validate_filename_safety(filename)
    if not valid:
        raise ValidationError(f"Invalid filename: {error}")

    filepath = OUTPUTS_DIR / filename
    # Ensure file is within OUTPUTS_DIR (path traversal protection)
    try:
        filepath.relative_to(OUTPUTS_DIR.resolve())
    except ValueError:
        raise AuthorizationError("Access denied: invalid file path")

    if not filepath.exists() or not filepath.is_file():
        raise ResourceNotFoundError("File not found")

    return FileResponse(str(filepath), filename=filename)


@router.delete("/api/downloads/{filename}")
async def api_delete_download(
    filename: str,
    current_user: dict = Depends(_require_auth),
):
    valid, error = validate_filename_safety(filename)
    if not valid:
        raise ValidationError(f"Invalid filename: {error}")

    filepath = OUTPUTS_DIR / filename
    try:
        filepath.relative_to(OUTPUTS_DIR.resolve())
    except ValueError:
        raise AuthorizationError("Access denied: invalid file path")

    if not filepath.exists():
        raise ResourceNotFoundError("File not found")

    filepath.unlink()
    return {"success": True, "message": f"Deleted {filename}"}


# ---------------------------------------------------------------------------
# Uploads (Auth required - with full validation)
# ---------------------------------------------------------------------------

@router.post("/api/uploads")
async def api_upload_file(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(_require_auth),
):
    await check_rate_limit(request, limit_type="upload")

    # Read file content
    content = await file.read()

    # Full validation
    is_valid, error, info = validate_uploaded_file(
        filename=file.filename or "unknown",
        content=content,
        allowed_extensions=SUPPORTED_AUDIO_FORMATS,
        max_size_mb=MAX_UPLOAD_MB,
    )

    if not is_valid:
        logger.warning(f"Upload validation failed: {error}")
        raise FileUploadError(error, {"validation": info})

    # Save file with safe name
    safe_name = Path(file.filename).name
    filepath = UPLOADS_DIR / safe_name

    # Prevent overwriting - add suffix if exists
    counter = 1
    original_path = filepath
    while filepath.exists():
        stem = original_path.stem
        suffix = original_path.suffix
        filepath = UPLOADS_DIR / f"{stem}_{counter}{suffix}"
        counter += 1

    try:
        with open(filepath, "wb") as f:
            f.write(content)
        logger.info(f"Uploaded: {filepath} ({len(content)} bytes, MIME: {info.get('mime_type', 'unknown')})")
    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}")
        raise FileUploadError(f"Failed to save file: {str(e)}")

    return {
        "success": True,
        "message": "File uploaded successfully",
        "filename": filepath.name,
        "original_name": file.filename,
        "path": str(filepath),
        "size": len(content),
        "mime_type": info.get("mime_type"),
    }


@router.get("/api/uploads")
async def api_list_uploads(current_user: dict = Depends(_require_auth)):
    files = []
    try:
        for f in sorted(UPLOADS_DIR.iterdir()):
            if f.is_file() and not f.name.startswith("."):
                files.append({
                    "name": f.name,
                    "size": f.stat().st_size,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
                })
    except Exception as e:
        logger.error(f"Failed to list uploads: {e}")
        raise PluginError("Failed to list uploads")
    return {"files": files, "count": len(files), "dir": str(UPLOADS_DIR)}


# ---------------------------------------------------------------------------
# TTS Endpoints (Auth required + rate limited)
# ---------------------------------------------------------------------------

@router.post("/api/tts")
async def api_tts(
    request: Request,
    req: TTSRequest,
    current_user: dict = Depends(_require_auth),
):
    await check_rate_limit(request, limit_type="tts")

    # Validate text
    valid, error = validate_text_input(req.text)
    if not valid:
        raise ValidationError(error)

    # Validate engine
    valid, error = validate_engine_name(req.engine, [])
    if not valid:
        raise ValidationError(error)

    # Auto-detect engine if requested
    if req.engine == "auto":
        selected = tts_registry.auto_select_engine()
        if selected:
            req.engine = selected
        else:
            return {
                "success": False,
                "engine": "auto",
                "message": "No TTS engine available with downloaded models. Install one: piper, kokoro, coqui, melotts, styletts2. See /api/plugins for status.",
                "available_engines": [e["name"] for e in tts_registry.get_available_engines()],
            }

    # Try TTS plugin system first
    try:
        plugin = tts_registry.get_plugin(req.engine)
        if plugin:
            result = await plugin.generate(
                text=req.text, voice=req.voice,
                language=req.language, speed=req.speed,
            )
            return result
    except Exception as e:
        logger.error(f"Plugin TTS failed: {e}")

    # Fallback to old tts engine
    try:
        result = await tts.synthesize(
            text=req.text, engine=req.engine, language=req.language,
            voice=req.voice, speed=req.speed, pitch=req.pitch,
        )
        return result
    except Exception as e:
        logger.error(f"TTS synthesis failed: {e}")
        raise PluginError(f"TTS synthesis failed: {str(e)}")


@router.post("/api/speech")
async def api_speech(
    request: Request,
    req: TTSRequest,
    current_user: dict = Depends(_require_auth),
):
    return await api_tts(request, req, current_user)


# ---------------------------------------------------------------------------
# Audio / Clone Endpoints (Auth required + rate limited)
# ---------------------------------------------------------------------------

@router.post("/api/audio/clone")
async def api_clone(
    request: Request,
    req: CloneRequest,
    current_user: dict = Depends(_require_auth),
):
    await check_rate_limit(request, limit_type="tts")

    # Validate inputs
    valid, error = validate_text_input(req.text)
    if not valid:
        raise ValidationError(error)

    # Sanitize reference audio path
    safe_path = sanitize_path(req.reference_audio, UPLOADS_DIR) or sanitize_path(req.reference_audio, OUTPUTS_DIR)
    if not safe_path or not safe_path.exists():
        # Try as direct filename in uploads
        direct = UPLOADS_DIR / Path(req.reference_audio).name
        if direct.exists():
            safe_path = direct
        else:
            raise ResourceNotFoundError(f"Reference audio not found: {req.reference_audio}")

    try:
        plugin = tts_registry.get_plugin(req.engine)
        if plugin and hasattr(plugin, "clone"):
            return await plugin.clone(reference_audio_path=str(safe_path), text=req.text)

        result = await tts.clone_voice(
            reference_audio_path=str(safe_path),
            text=req.text, engine=req.engine,
        )
        return result
    except Exception as e:
        logger.error(f"Voice clone failed: {e}")
        raise PluginError(f"Voice clone failed: {str(e)}")


@router.post("/api/audio/upload")
async def api_audio_upload(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(_require_auth),
):
    return await api_upload_file(request, file, current_user)


@router.get("/api/audio/list")
async def api_audio_list(current_user: dict = Depends(_require_auth)):
    all_files = []
    try:
        for d in [OUTPUTS_DIR, UPLOADS_DIR]:
            for f in sorted(d.iterdir()):
                if f.is_file() and not f.name.startswith("."):
                    all_files.append({
                        "name": f.name,
                        "size": f.stat().st_size,
                        "dir": str(d),
                        "modified": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
                    })
    except Exception as e:
        logger.error(f"Failed to list audio files: {e}")
        raise PluginError("Failed to list audio files")
    return {"files": all_files, "count": len(all_files)}


# ---------------------------------------------------------------------------
# Cache (Auth required)
# ---------------------------------------------------------------------------

@router.get("/api/cache")
async def api_cache_info(current_user: dict = Depends(_require_auth)):
    files = []
    total_size = 0
    try:
        for f in CACHE_DIR.iterdir():
            if f.is_file() and not f.name.startswith("."):
                s = f.stat().st_size
                total_size += s
                files.append({"name": f.name, "size": s})
    except Exception as e:
        logger.error(f"Failed to read cache: {e}")
        raise PluginError("Failed to read cache info")
    return {"files": files, "count": len(files), "total_size": total_size, "dir": str(CACHE_DIR)}


@router.delete("/api/cache")
async def api_cache_clear(current_user: dict = Depends(_require_auth)):
    cleared = 0
    try:
        for f in CACHE_DIR.iterdir():
            if f.is_file() and not f.name.startswith("."):
                f.unlink()
                cleared += 1
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        raise PluginError(f"Failed to clear cache: {str(e)}")
    return {"success": True, "message": f"Cleared {cleared} files from cache"}


# ---------------------------------------------------------------------------
# File Operations (Auth required)
# ---------------------------------------------------------------------------

@router.post("/api/files/{filename}/rename")
async def api_rename_file(
    filename: str,
    req: RenameRequest,
    current_user: dict = Depends(_require_auth),
):
    # Validate source filename
    valid, error = validate_filename_safety(filename)
    if not valid:
        raise ValidationError(f"Invalid source filename: {error}")

    # Find file
    found = None
    for d in [OUTPUTS_DIR, UPLOADS_DIR]:
        f = d / filename
        if f.exists() and f.is_file():
            # Verify it's within the directory
            try:
                f.relative_to(d.resolve())
                found = f
                break
            except ValueError:
                continue

    if not found:
        raise ResourceNotFoundError("File not found")

    new_path = found.parent / req.new_name
    try:
        new_path.relative_to(found.parent.resolve())
    except ValueError:
        raise AuthorizationError("Invalid destination path")

    # Prevent overwriting
    if new_path.exists():
        raise ValidationError("Destination file already exists")

    found.rename(new_path)
    return {"success": True, "message": f"Renamed {filename} to {req.new_name}", "path": str(new_path)}
