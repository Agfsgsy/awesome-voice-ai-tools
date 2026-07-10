"""Complete API Routes - All Endpoints with Validation and Security"""
import os
import json
import shutil
import platform
import sys
import asyncio
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Request, Query
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.core.config import settings, GPUConfig
from backend.core.logger import get_logger
from backend.core.health import health_checker
from backend.core.security import rate_limit, rate_limiter, generate_secure_filename, validate_audio_file
from backend.core.tts_engine import tts
from backend.core.tts_registry import tts_registry
from backend.core.plugin_manager import init_plugin_manager
from backend.core.model_manager import model_manager
from backend.core.voice_manager import voice_manager
from backend.core.cache_manager import cache_manager
from backend.core.language_manager import language_manager
from backend.core.task_manager import task_manager, Task, TaskPriority, TaskType
from backend.core.download_manager import download_manager
from backend.core.upload_manager import upload_manager
from backend.core.output_manager import output_manager
from backend.core.settings_manager import settings_manager
from backend.core.audio_utils import get_audio_info, apply_effects

logger = get_logger("api")
router = APIRouter()

# === Pydantic Models ===

class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000, description="Text to synthesize")
    engine: str = Field(default="auto", description="TTS engine name")
    language: str = Field(default="ar", description="Language code")
    voice: str = Field(default="default", description="Voice identifier")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="Speech speed")
    pitch: float = Field(default=0.0, ge=-10, le=10, description="Pitch adjustment")

class BatchTTSRequest(BaseModel):
    texts: List[str] = Field(..., min_items=1, max_items=50, description="List of texts")
    engine: str = Field(default="auto", description="TTS engine")
    language: str = Field(default="ar", description="Language code")
    voice: str = Field(default="default", description="Voice identifier")
    speed: float = Field(default=1.0, ge=0.5, le=2.0)

class CloneRequest(BaseModel):
    reference_audio: str = Field(..., description="Path to reference audio file")
    text: str = Field(..., min_length=1, max_length=5000, description="Text to clone")
    engine: str = Field(default="xtts", description="Cloning engine")

class PluginActionRequest(BaseModel):
    name: str = Field(..., description="Plugin name")
    action: str = Field(..., description="Action: enable, disable, reload, delete")

class ModelDownloadRequest(BaseModel):
    engine: str = Field(..., description="Engine name")
    model_name: str = Field(default="default", description="Model name")

class ModelSearchRequest(BaseModel):
    query: str = Field(default="", description="Search query")
    engine: str = Field(default="", description="Engine filter")
    language: str = Field(default="", description="Language filter")

class VoiceSearchRequest(BaseModel):
    query: str = Field(default="", description="Search query")
    language: str = Field(default="", description="Language filter")
    engine: str = Field(default="", description="Engine filter")
    gender: str = Field(default="", description="Gender filter")

class SettingsUpdateRequest(BaseModel):
    section: str = Field(..., description="Settings section")
    values: dict = Field(..., description="Settings values")

class CacheConfigRequest(BaseModel):
    action: str = Field(..., description="clear, info, cleanup")
    tag: str = Field(default="", description="Filter by tag")

class DownloadRequest(BaseModel):
    url: str = Field(..., description="Download URL")
    filename: str = Field(default="", description="Target filename")
    checksum: str = Field(default="", description="Expected SHA-256 checksum")

class TaskCreateRequest(BaseModel):
    name: str = Field(..., description="Task name")
    task_type: str = Field(default="custom", description="Task type")
    priority: int = Field(default=3, ge=1, le=5, description="Priority 1-5")
    params: dict = Field(default_factory=dict, description="Task parameters")

class EffectsRequest(BaseModel):
    filename: str = Field(..., description="Audio filename")
    preset: str = Field(default="studio", description="Effect preset")

# === Helper ===
def _get_plugin_manager():
    try:
        return init_plugin_manager(settings.PLUGINS_DIR)
    except Exception:
        return None

# === Root & Info ===

@router.get("/")
async def root():
    return {"app": settings.APP_NAME, "version": settings.APP_VERSION, "status": "running", "docs": "/docs"}

@router.get("/health")
async def health(request: Request):
    checks = health_checker.run_checks()
    rate_info = rate_limiter.get_remaining(request)
    return {**checks, "rate_limit": rate_info}

@router.get("/health/detailed")
async def health_detailed(categories: str = ""):
    cats = categories.split(",") if categories else None
    return health_checker.run_checks(cats)

@router.get("/status")
async def status():
    available = tts_registry.get_available_engines()
    auto_engine = tts_registry.auto_select_engine()
    return {
        "app": settings.APP_NAME, "version": settings.APP_VERSION,
        "host": settings.APP_HOST, "port": settings.APP_PORT,
        "debug": settings.APP_DEBUG, "environment": settings.APP_ENV,
        "python": sys.version.split()[0], "platform": platform.platform(),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "device": GPUConfig.get_device(),
        "gpu_info": GPUConfig.get_cuda_info(),
        "engines": tts.list_engines(),
        "available_engines": [e["name"] for e in available],
        "auto_selected_engine": auto_engine,
        "plugins_loaded": len(tts_registry.get_all_plugins()),
    }

@router.get("/version")
async def version():
    return {"version": settings.APP_VERSION, "name": settings.APP_NAME}

# === TTS Endpoints ===

@router.post("/api/tts")
async def api_tts(request: Request, req: TTSRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")

    if req.engine == "auto":
        selected = tts_registry.auto_select_engine()
        req.engine = selected or "fallback"

    plugin = tts_registry.get_plugin(req.engine)
    if plugin:
        result = await plugin.generate(text=req.text, voice=req.voice,
                                        language=req.language, speed=req.speed)
        return result

    result = await tts.synthesize(text=req.text, engine=req.engine, language=req.language,
                                   voice=req.voice, speed=req.speed, pitch=req.pitch)
    return result

@router.post("/api/tts/batch")
async def api_tts_batch(req: BatchTTSRequest):
    results = await tts.synthesize_batch(req.texts, req.engine, req.language, req.voice, req.speed)
    return {"results": results, "total": len(results), "successful": sum(1 for r in results if r.get("success"))}

@router.post("/api/tts/stream")
async def api_tts_stream(req: TTSRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")

    engine = req.engine if req.engine != "auto" else (tts_registry.auto_select_engine() or "fallback")

    async def audio_stream():
        async for chunk in tts.synthesize_streaming(req.text, engine, req.language, req.voice, req.speed):
            yield chunk

    return StreamingResponse(audio_stream(), media_type="audio/wav")

@router.post("/api/speech")
async def api_speech(request: Request, req: TTSRequest):
    return await api_tts(request, req)

# === Voice Clone ===

@router.post("/api/audio/clone")
async def api_clone(req: CloneRequest):
    result = await tts.clone_voice(req.reference_audio, req.text, req.engine)
    return result

# === Plugin Management ===

@router.get("/api/plugins")
async def api_plugins():
    all_plugins = []
    for plugin in tts_registry.get_all_plugins():
        try:
            info = plugin.health()
            all_plugins.append(info)
        except Exception as e:
            all_plugins.append({"name": getattr(plugin, "name", "unknown"), "error": str(e)})

    pm = _get_plugin_manager()
    builtin = pm.get_info() if pm else []

    return {"tts_plugins": all_plugins, "builtin_plugins": builtin, "count": len(all_plugins)}

@router.get("/api/plugins/{name}")
async def api_plugin_detail(name: str):
    plugin = tts_registry.get_plugin(name)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
    return plugin.health()

@router.post("/api/plugins/install")
async def api_plugin_install(req: PluginActionRequest):
    plugin = tts_registry.get_plugin(req.name)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{req.name}' not found")
    return plugin.install()

@router.post("/api/plugins/action")
async def api_plugin_action(req: PluginActionRequest):
    pm = _get_plugin_manager()
    if not pm:
        return {"success": False, "message": "Plugin manager not initialized"}

    if req.action == "enable":
        return {"success": pm.enable_plugin(req.name)}
    elif req.action == "disable":
        return {"success": pm.disable_plugin(req.name)}
    elif req.action == "reload":
        return {"success": pm.reload_plugin(req.name)}
    elif req.action == "delete":
        return pm.delete_plugin(req.name)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {req.action}")

@router.get("/api/plugins/{name}/health")
async def api_plugin_health(name: str):
    pm = _get_plugin_manager()
    if pm and name in pm.registry:
        return pm.health_check(name)
    plugin = tts_registry.get_plugin(name)
    if plugin:
        return {"name": name, "installed": plugin.check(), "health": "ok"}
    raise HTTPException(status_code=404, detail="Plugin not found")

# === Model Management ===

@router.get("/api/models")
async def api_models():
    models = model_manager.list_all_models()
    return {"models": models, "count": len(models)}

@router.post("/api/models/search")
async def api_models_search(req: ModelSearchRequest):
    results = model_manager.search_models(req.query, req.engine, req.language)
    return {"models": results, "count": len(results)}

@router.post("/api/models/download")
async def api_model_download(req: ModelDownloadRequest):
    return model_manager.download_model(req.engine, req.model_name)

@router.get("/api/models/{engine}/{model_name}")
async def api_model_info(engine: str, model_name: str):
    return model_manager.get_model_info(engine, model_name)

@router.delete("/api/models/{engine}/{model_name}")
async def api_model_delete(engine: str, model_name: str):
    return model_manager.delete_model(engine, model_name)

@router.post("/api/models/{engine}/{model_name}/verify")
async def api_model_verify(engine: str, model_name: str):
    return model_manager.verify_model(engine, model_name)

@router.get("/api/models/stats")
async def api_models_stats():
    return model_manager.get_stats()

# === Voice Management ===

@router.get("/api/voices")
async def api_voices():
    voices = voice_manager.list_all_voices()
    return {"voices": voices, "count": len(voices)}

@router.post("/api/voices/search")
async def api_voices_search(req: VoiceSearchRequest):
    results = voice_manager.search_voices(req.query, req.language, req.engine, req.gender)
    return {"voices": results, "count": len(results)}

@router.get("/api/voices/{voice_id}")
async def api_voice_detail(voice_id: str):
    voice = voice_manager.get_voice(voice_id)
    if not voice:
        raise HTTPException(status_code=404, detail="Voice not found")
    return voice

@router.post("/api/voices/{voice_id}/favorite")
async def api_voice_favorite(voice_id: str):
    is_fav = voice_manager.toggle_favorite(voice_id)
    return {"voice_id": voice_id, "is_favorite": is_fav}

@router.get("/api/voices/favorites/list")
async def api_voices_favorites():
    return {"voices": voice_manager.list_favorites()}

@router.get("/api/voices/stats")
async def api_voices_stats():
    return voice_manager.get_stats()

# === Language Management ===

@router.get("/api/languages")
async def api_languages():
    return {"languages": language_manager.list_languages()}

@router.post("/api/languages/detect")
async def api_detect_language(text: str = Form(...)):
    return language_manager.detect_language(text)

@router.get("/api/languages/{code}/engines")
async def api_language_engines(code: str):
    return {"language": code, "engines": language_manager.get_supported_engines(code)}

# === Task Management ===

@router.get("/api/tasks")
async def api_tasks(status: str = "", task_type: str = ""):
    st = None
    if status:
        from backend.core.task_manager import TaskStatus
        st = TaskStatus(status)
    tt = None
    if task_type:
        from backend.core.task_manager import TaskType
        tt = TaskType(task_type)
    return {"tasks": task_manager.list_tasks(st, tt)}

@router.post("/api/tasks")
async def api_create_task(req: TaskCreateRequest):
    from backend.core.task_manager import TaskType, TaskPriority
    task = Task(
        name=req.name,
        task_type=TaskType(req.task_type) if req.task_type else TaskType.CUSTOM,
        priority=TaskPriority(req.priority) if req.priority else TaskPriority.NORMAL,
        params=req.params,
    )
    task_id = await task_manager.submit(task)
    return {"success": True, "task_id": task_id}

@router.get("/api/tasks/{task_id}")
async def api_task_detail(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@router.post("/api/tasks/{task_id}/cancel")
async def api_task_cancel(task_id: str):
    return {"success": await task_manager.cancel(task_id)}

@router.get("/api/tasks/stats")
async def api_tasks_stats():
    return task_manager.get_stats()

# === Cache Management ===

@router.get("/api/cache")
async def api_cache_info():
    return cache_manager.get_info()

@router.post("/api/cache")
async def api_cache_action(req: CacheConfigRequest):
    if req.action == "clear":
        count = await cache_manager.clear()
        return {"success": True, "cleared": count}
    elif req.action == "cleanup":
        count = await cache_manager.cleanup_expired()
        return {"success": True, "cleaned": count}
    else:
        return cache_manager.get_info()

# === Download Management ===

@router.post("/api/downloads/create")
async def api_download_create(req: DownloadRequest):
    task_id = download_manager.create_task(req.url, req.filename, req.checksum)
    return {"success": True, "task_id": task_id}

@router.post("/api/downloads/{task_id}/start")
async def api_download_start(task_id: str):
    return await download_manager.start_download(task_id)

@router.get("/api/downloads/tasks")
async def api_download_tasks(status: str = ""):
    return {"downloads": download_manager.list_tasks(status)}

@router.get("/api/downloads/{task_id}")
async def api_download_status(task_id: str):
    task = download_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Download not found")
    return task

@router.get("/api/downloads/stats")
async def api_downloads_stats():
    return download_manager.get_stats()

# === Upload Management ===

@router.post("/api/uploads")
async def api_upload_file(file: UploadFile = File(...)):
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large (max {settings.MAX_UPLOAD_MB}MB)")
    return await upload_manager.process_upload(file.filename, content, file.content_type)

@router.get("/api/uploads")
async def api_list_uploads():
    return {"uploads": upload_manager.list_entries()}

@router.delete("/api/uploads/{entry_id}")
async def api_delete_upload(entry_id: str):
    return {"success": upload_manager.delete_entry(entry_id)}

# === Output Management ===

@router.get("/api/downloads")
async def api_list_outputs(pattern: str = "", sort_by: str = "modified"):
    files = output_manager.list_outputs(pattern, sort_by)
    return {"files": files, "count": len(files)}

@router.get("/api/downloads/{filename}")
async def api_get_output(filename: str):
    filepath = settings.OUTPUTS_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(filepath), filename=filename)

@router.delete("/api/downloads/{filename}")
async def api_delete_output(filename: str):
    return {"success": output_manager.delete_output(filename)}

@router.post("/api/downloads/{filename}/rename")
async def api_rename_output(filename: str, new_name: str = Form(...)):
    return output_manager.rename_output(filename, new_name)

@router.get("/api/downloads/{filename}/info")
async def api_output_info(filename: str):
    filepath = settings.OUTPUTS_DIR / filename
    return get_audio_info(filepath)

@router.post("/api/downloads/{filename}/effects")
async def api_apply_effects(filename: str, req: EffectsRequest):
    filepath = settings.OUTPUTS_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    result_path = apply_effects(filepath, req.preset)
    return {"success": True, "output": str(result_path), "preset": req.preset}

@router.get("/api/outputs/stats")
async def api_outputs_stats():
    return output_manager.get_stats()

# === Settings Management ===

@router.get("/api/settings")
async def api_settings():
    return settings_manager.get_all()

@router.get("/api/settings/{section}")
async def api_settings_section(section: str):
    return settings_manager.get_section(section)

@router.post("/api/settings/{section}")
async def api_update_settings(section: str, req: SettingsUpdateRequest):
    return {"success": settings_manager.update_section(section, req.values)}

@router.post("/api/settings/reset")
async def api_reset_settings(section: str = ""):
    if section:
        return {"success": settings_manager.reset_section(section)}
    return {"success": settings_manager.reset_all()}

# === Logs ===

@router.get("/api/logs")
async def api_logs(lines: int = 200, level: str = ""):
    from backend.core.logger import get_recent_logs
    logs = get_recent_logs(lines, level or None)
    return {"logs": logs, "count": len(logs)}

@router.get("/api/logs/download")
async def api_download_logs():
    log_file = settings.LOGS_DIR / "app.log"
    if not log_file.exists():
        return {"message": "No logs"}
    return FileResponse(str(log_file), filename="app.log")

# === System ===

@router.get("/api/system")
async def api_system():
    disk = shutil.disk_usage(str(settings.BASE_DIR))
    mem_info = {}
    try:
        import psutil
        mem = psutil.virtual_memory()
        mem_info = {"total_mb": mem.total // (1024**2), "available_mb": mem.available // (1024**2),
                    "percent": mem.percent}
    except ImportError:
        pass

    return {
        "platform": platform.platform(), "python": sys.version.split()[0],
        "cpu_count": os.cpu_count(), "disk_total_gb": round(disk.total / (1024**3), 2),
        "disk_free_gb": round(disk.free / (1024**3), 2), "memory": mem_info,
        "gpu": GPUConfig.get_cuda_info(), "device": GPUConfig.get_device(),
    }

@router.get("/api/system/stats")
async def api_system_stats():
    return {
        "models": model_manager.get_stats(),
        "voices": voice_manager.get_stats(),
        "cache": cache_manager.get_stats(),
        "tasks": task_manager.get_stats(),
        "downloads": download_manager.get_stats(),
        "outputs": output_manager.get_stats(),
        "plugins": {"total": len(tts_registry.get_all_plugins()), "registry": tts_registry.get_stats()},
    }

# === Settings/Config ===

@router.get("/api/info")
async def api_info():
    return {
        "app_name": settings.APP_NAME, "version": settings.APP_VERSION,
        "description": "Professional open-source voice AI platform",
        "engines": tts.list_engines(), "max_upload_mb": settings.MAX_UPLOAD_MB,
        "supported_formats": settings.SUPPORTED_AUDIO_FORMATS,
        "gemini_configured": bool(settings.GEMINI_API_KEY),
        "languages_supported": len(language_manager.list_languages()),
    }
