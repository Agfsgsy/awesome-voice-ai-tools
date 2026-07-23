"""مسارات API الكاملة"""
import json
import aiofiles
import os
import shutil
import platform
import sys
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from pydantic import BaseModel

from backend.core.config import (
    APP_NAME, APP_VERSION, APP_HOST, APP_PORT, APP_DEBUG,
    IS_TERMUX, IS_ANDROID, IS_COLAB, GEMINI_API_KEY, GEMINI_TTS_MODEL,
    MODELS_DIR, VOICES_DIR, DOWNLOADS_DIR, UPLOADS_DIR, OUTPUTS_DIR,
    CACHE_DIR, LOGS_DIR, CONFIG_DIR, ENGINE_PRIORITY, MAX_UPLOAD_MB,
    SUPPORTED_AUDIO_FORMATS, PLUGINS_DIR
)
from backend.core.logger import get_logger
from backend.core.health import run_all_checks
from backend.core.tts_engine import tts
from backend.core.plugin_manager import init_plugin_manager
from backend.core.tts_registry import tts_registry

logger = get_logger("api")
router = APIRouter()

# === Models ===
class TTSRequest(BaseModel):
    text: str
    engine: str = "auto"
    language: str = "ar"
    voice: str = "default"
    speed: float = 1.0
    pitch: float = 0.0

class CloneRequest(BaseModel):
    reference_audio: str
    text: str
    engine: str = "coqui"

class SettingsUpdate(BaseModel):
    gemini_api_key: Optional[str] = None
    gemini_tts_model: Optional[str] = None
    default_engine: Optional[str] = None
    default_language: Optional[str] = None

class RenameRequest(BaseModel):
    new_name: str

class PluginInstallRequest(BaseModel):
    engine: str

class ModelDownloadRequest(BaseModel):
    engine: str
    model_name: str = "default"

# === Init builtin plugins ===
try:
    pm = init_plugin_manager(PLUGINS_DIR)
    pm.load_all()
except Exception as e:
    logger.warning(f"Plugin init failed (non-critical): {e}")
    pm = None

# === TTS Registry init ===
tts_registry.initialize()

# === Helper ===
def _pm_info():
    if pm:
        return pm.get_info()
    return []

# === Routes ===

@router.get("/")
async def root():
    return {"app": APP_NAME, "version": APP_VERSION, "status": "running", "docs": "/docs"}

@router.get("/health")
async def health():
    checks = run_all_checks(APP_PORT)
    all_ok = all(c.get("ok", False) for c in checks)
    return {"status": "healthy" if all_ok else "warning", "checks": checks}

@router.get("/status")
async def status():
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
        "timestamp": datetime.now().isoformat(),
        "engines": tts.list_engines(),
        "tts_plugins": [p.name for p in tts_registry.get_all_plugins()],
        "available_engines": [e["name"] for e in available],
        "auto_selected_engine": auto_engine,
        "plugins_loaded": len([k for k, v in (pm.loaded if pm else {}).items() if v is not None]),
        "plugins_total": len(pm.registry) if pm else 0,
    }

@router.get("/version")
async def version():
    return {"version": APP_VERSION, "name": APP_NAME}

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

# === Plugin endpoints ===

@router.get("/api/plugins")
async def api_plugins():
    all_plugins = []
    for plugin in tts_registry.get_all_plugins():
        info = plugin.health()
        all_plugins.append(info)
    builtin = _pm_info()
    return {"tts_plugins": all_plugins, "builtin_plugins": builtin}

@router.get("/api/plugins/{name}")
async def api_plugin_detail(name: str):
    plugin = tts_registry.get_plugin(name)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
    return plugin.health()

@router.post("/api/plugins/install")
async def api_plugin_install(req: PluginInstallRequest):
    plugin = tts_registry.get_plugin(req.engine)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Engine '{req.engine}' not found")
    return plugin.install()

@router.post("/api/plugins/check")
async def api_plugin_check(req: PluginInstallRequest):
    plugin = tts_registry.get_plugin(req.engine)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Engine '{req.engine}' not found")
    installed = plugin.check()
    return {"engine": req.engine, "installed": installed}

# === Model endpoints ===

@router.get("/api/models")
async def api_models():
    from backend.core.model_manager import model_manager
    models = model_manager.list_all_models()
    return {"models": models, "count": len(models)}

@router.post("/api/models/download")
async def api_model_download(req: ModelDownloadRequest):
    from backend.core.model_manager import model_manager
    return model_manager.download_model(req.engine, req.model_name)

@router.get("/api/voices")
async def api_voices():
    from backend.core.voice_manager import voice_manager
    voices = voice_manager.list_all_voices()
    return {"voices": voices, "count": len(voices)}

# === Settings ===

@router.get("/api/settings")
async def api_settings():
    return {
        "gemini_api_key_set": bool(GEMINI_API_KEY),
        "gemini_tts_model": GEMINI_TTS_MODEL,
        "default_engine": ENGINE_PRIORITY[0] if ENGINE_PRIORITY else "kokoro",
        "is_termux": IS_TERMUX,
        "is_colab": IS_COLAB,
        "app_host": APP_HOST,
        "app_port": APP_PORT,
    }

@router.post("/api/settings")
async def api_update_settings(data: SettingsUpdate):
    import backend.core.config as config
    env_file = Path(".env")
    env_lines = env_file.read_text().splitlines() if env_file.exists() else []
    env_dict = {line.split("=", 1)[0]: line.split("=", 1)[1] for line in env_lines if "=" in line}

    if data.gemini_api_key is not None:
        env_dict["GEMINI_API_KEY"] = data.gemini_api_key
        config.GEMINI_API_KEY = data.gemini_api_key
    if data.gemini_tts_model is not None:
        env_dict["GEMINI_TTS_MODEL"] = data.gemini_tts_model
        config.GEMINI_TTS_MODEL = data.gemini_tts_model

    # Save back to .env
    env_file.write_text("\n".join(f"{k}={v}" for k, v in env_dict.items()))

    return {"message": "Settings updated successfully"}

# === System ===

@router.get("/api/system")
async def api_system():
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

# === Logs ===

@router.get("/api/logs")
async def api_logs():
    log_file = LOGS_DIR / "app.log"
    if log_file.exists():
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]
        return {"logs": lines, "count": len(lines)}
    return {"logs": [], "message": "No log file found"}

@router.get("/api/logs/download")
async def api_download_logs():
    log_file = LOGS_DIR / "app.log"
    if not log_file.exists():
        return {"message": "No logs"}
    return FileResponse(str(log_file), filename="app.log", media_type="text/plain")

# === Downloads ===

@router.get("/api/downloads")
async def api_list_downloads():
    files = []
    for f in sorted(OUTPUTS_DIR.iterdir()):
        if f.is_file() and not f.name.startswith("."):
            files.append({
                "name": f.name, "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
    return {"files": files, "count": len(files), "dir": str(OUTPUTS_DIR)}

@router.get("/api/downloads/{filename}")
async def api_download_file(filename: str):
    filepath = OUTPUTS_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(filepath), filename=filename)

@router.delete("/api/downloads/{filename}")
async def api_delete_download(filename: str):
    filepath = OUTPUTS_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    filepath.unlink()
    return {"message": f"Deleted {filename}"}

# === Uploads ===

@router.post("/api/uploads")
async def api_upload_file(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_AUDIO_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {ext}")
    content = await file.read()
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_MB}MB)")
    filepath = UPLOADS_DIR / file.filename
    async with aiofiles.open(filepath, "wb") as f:
        await f.write(content)
    logger.info(f"Uploaded: {filepath}")
    return {"message": "File uploaded", "filename": file.filename, "path": str(filepath), "size": len(content)}

@router.get("/api/uploads")
async def api_list_uploads():
    files = []
    for f in sorted(UPLOADS_DIR.iterdir()):
        if f.is_file() and not f.name.startswith("."):
            files.append({
                "name": f.name, "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
    return {"files": files, "count": len(files), "dir": str(UPLOADS_DIR)}

# === TTS ===

@router.post("/api/tts")
async def api_tts(req: TTSRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")

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
    plugin = tts_registry.get_plugin(req.engine)
    if plugin:
        result = await plugin.generate(
            text=req.text, voice=req.voice,
            language=req.language, speed=req.speed,
        )
        return result

    # Fallback to old tts engine
    result = await tts.synthesize(
        text=req.text, engine=req.engine, language=req.language,
        voice=req.voice, speed=req.speed, pitch=req.pitch,
    )
    return result

@router.post("/api/speech")
async def api_speech(req: TTSRequest):
    return await api_tts(req)

# === Audio ===

@router.post("/api/audio/clone")
async def api_clone(req: CloneRequest):
    plugin = tts_registry.get_plugin(req.engine)
    if plugin and hasattr(plugin, "clone"):
        return await plugin.clone(reference_audio_path=req.reference_audio, text=req.text)
    result = await tts.clone_voice(
        reference_audio_path=req.reference_audio,
        text=req.text, engine=req.engine,
    )
    return result

@router.post("/api/audio/upload")
async def api_audio_upload(file: UploadFile = File(...)):
    return await api_upload_file(file)

@router.get("/api/audio/list")
async def api_audio_list():
    all_files = []
    for d in [OUTPUTS_DIR, UPLOADS_DIR]:
        for f in sorted(d.iterdir()):
            if f.is_file() and not f.name.startswith("."):
                all_files.append({
                    "name": f.name, "size": f.stat().st_size,
                    "dir": str(d), "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                })
    return {"files": all_files, "count": len(all_files)}

# === Cache ===

@router.get("/api/cache")
async def api_cache_info():
    files = []
    total_size = 0
    for f in CACHE_DIR.iterdir():
        if f.is_file() and not f.name.startswith("."):
            s = f.stat().st_size
            total_size += s
            files.append({"name": f.name, "size": s})
    return {"files": files, "count": len(files), "total_size": total_size, "dir": str(CACHE_DIR)}

@router.delete("/api/cache")
async def api_cache_clear():
    cleared = 0
    for f in CACHE_DIR.iterdir():
        if f.is_file() and not f.name.startswith("."):
            f.unlink()
            cleared += 1
    return {"message": f"Cleared {cleared} files from cache"}

# === Files ===

@router.post("/api/files/{filename}/rename")
async def api_rename_file(filename: str, req: RenameRequest):
    found = None
    for d in [OUTPUTS_DIR, UPLOADS_DIR]:
        f = d / filename
        if f.exists():
            found = f
            break
    if not found:
        raise HTTPException(status_code=404, detail="File not found")
    new_path = found.parent / req.new_name
    found.rename(new_path)
    return {"message": f"Renamed {filename} to {req.new_name}", "path": str(new_path)}

# === Effects ===
@router.post("/api/effects/apply")
async def api_effects_apply(file: UploadFile = File(...), preset: str = Form(...)):
    filename = Path(file.filename).name
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_AUDIO_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {ext}")

    content = await file.read()
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_MB}MB)")

    filepath = UPLOADS_DIR / filename
    async with aiofiles.open(filepath, "wb") as f:
        await f.write(content)

    try:
        from backend.plugins.builtin.audio_effects import process_audio
        import hashlib
        name_hash = hashlib.md5(content).hexdigest()[:8]
        out_filename = f"effect_{preset}_{name_hash}.wav"
        out_filepath = OUTPUTS_DIR / out_filename

        success = process_audio(str(filepath), str(out_filepath), preset)
        if success:
            return {
                "message": "Effects applied",
                "filename": out_filename,
                "path": str(out_filepath),
                "url": f"/api/downloads/{out_filename}"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to apply effects")
    except Exception as e:
        logger.error(f"Effect processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# === STT ===
@router.post("/api/stt")
async def api_stt(file: UploadFile = File(...), language: str = Form("ar-SA")):
    filename = Path(file.filename).name
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_AUDIO_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {ext}")

    content = await file.read()
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_MB}MB)")

    filepath = UPLOADS_DIR / filename
    async with aiofiles.open(filepath, "wb") as f:
        await f.write(content)

    try:
        from backend.plugins.builtin.stt_plugin import transcribe_audio
        text = transcribe_audio(str(filepath), language=language)
        return {"text": text, "message": "تم تحويل الصوت إلى نص"}
    except Exception as e:
        logger.error(f"STT processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
