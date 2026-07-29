"""Voice Clone Pro 7 multi-engine compatibility and orchestration routes.

This layer is additive. It reuses the consent/profile/XTTS implementation already
shipped with Ibn Al-Waqadi Studio and exposes a stable API for the advanced UI.
Missing engines return actionable HTTP 503 responses instead of unhandled 500s.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.api.voice_clone_routes import (
    ENGINE_STATUS,
    PROFILES_DIR,
    WORKER_FILE,
    GenerateCloneRequest,
    _engine_python,
    _human_settings,
    _profile_path,
    _read_status,
    create_profile_from_uploads,
    generate_from_profile,
    setup_local,
)
from backend.core.config import APP_RELEASE, APP_VERSION, DATA_DIR
from backend.core.logger import get_logger

router = APIRouter(prefix="/api/voice-ai", tags=["Voice Clone Pro 7"])
logger = get_logger("voice_clone_v7")

ENGINE_PACK_ROOT = DATA_DIR / "voice_engine_pack_v7"
ENGINE_PACK_STATUS = ENGINE_PACK_ROOT / "install_status.json"
ENGINE_PACK_ROOT.mkdir(parents=True, exist_ok=True)
_INSTALL_LOCK = threading.Lock()
_INSTALL_THREAD: threading.Thread | None = None

REMOTE_ENGINES: dict[str, dict[str, Any]] = {
    "openvoice": {
        "label": "OpenVoice V2",
        "env": "OPENVOICE_ENDPOINT",
        "default": "http://127.0.0.1:8101",
        "tasks": ["speech_clone", "voice_conversion"],
    },
    "f5tts": {
        "label": "F5-TTS",
        "env": "F5TTS_ENDPOINT",
        "default": "http://127.0.0.1:8102",
        "tasks": ["speech_clone"],
    },
    "gpt_sovits": {
        "label": "GPT-SoVITS",
        "env": "GPT_SOVITS_ENDPOINT",
        "default": "http://127.0.0.1:8103",
        "tasks": ["speech_clone", "few_shot_clone"],
    },
    "cosyvoice": {
        "label": "CosyVoice",
        "env": "COSYVOICE_ENDPOINT",
        "default": "http://127.0.0.1:8104",
        "tasks": ["speech_clone", "streaming"],
    },
    "rvc": {
        "label": "RVC",
        "env": "RVC_ENDPOINT",
        "default": "http://127.0.0.1:8110",
        "tasks": ["voice_conversion", "singing_conversion"],
    },
    "ace_step": {
        "label": "ACE-Step",
        "env": "ACE_STEP_ENDPOINT",
        "default": "http://127.0.0.1:8120",
        "tasks": ["song_generation", "sheilah_generation"],
    },
    "yue": {
        "label": "YuE",
        "env": "YUE_ENDPOINT",
        "default": "http://127.0.0.1:8121",
        "tasks": ["song_generation", "sheilah_generation"],
    },
}

ALIASES = {
    "coqui": "xtts",
    "coqui-tts": "xtts",
    "coqui_xtts": "xtts",
    "xtts-v2": "xtts",
    "xtts_v2": "xtts",
    "f5-tts": "f5tts",
    "gpt-sovits": "gpt_sovits",
    "ace-step": "ace_step",
}


def _normalize_engine(value: str) -> str:
    name = (value or "auto").strip().lower()
    return ALIASES.get(name, name)


def _xtts_ready() -> bool:
    setup = _read_status()
    return _engine_python().exists() and WORKER_FILE.exists() and setup.get("state") == "ready"


def _read_pack_status() -> dict[str, Any]:
    if not ENGINE_PACK_STATUS.exists():
        return {"state": "not_started", "progress": 0, "message": "لم يبدأ تثبيت حزمة المحركات."}
    try:
        return json.loads(ENGINE_PACK_STATUS.read_text(encoding="utf-8"))
    except Exception:
        return {"state": "unknown", "progress": 0, "message": "تعذر قراءة حالة التثبيت."}


def _write_pack_status(state: str, progress: int, message: str, detail: str = "") -> None:
    ENGINE_PACK_STATUS.write_text(
        json.dumps(
            {
                "state": state,
                "progress": max(0, min(100, int(progress))),
                "message": message,
                "detail": detail[-4000:],
                "updated_at": time.time(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


async def _remote_health(name: str, definition: dict[str, Any]) -> dict[str, Any]:
    endpoint = os.getenv(definition["env"], definition["default"]).rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            response = await client.get(endpoint + "/health")
        healthy = response.status_code < 400
        detail = response.json() if healthy and "application/json" in response.headers.get("content-type", "") else {}
        return {
            "name": name,
            "label": definition["label"],
            "healthy": healthy,
            "installed": healthy,
            "endpoint": endpoint,
            "tasks": definition["tasks"],
            "detail": detail,
        }
    except Exception as exc:
        return {
            "name": name,
            "label": definition["label"],
            "healthy": False,
            "installed": (ENGINE_PACK_ROOT / name).exists(),
            "endpoint": endpoint,
            "tasks": definition["tasks"],
            "detail": str(exc),
        }


async def _engine_statuses() -> list[dict[str, Any]]:
    local = {
        "name": "xtts",
        "label": "XTTS-v2 Local Pro",
        "healthy": _xtts_ready(),
        "installed": _engine_python().exists(),
        "tasks": ["speech_clone", "multi_reference_clone"],
        "detail": _read_status(),
    }
    settings = _human_settings()
    eleven = {
        "name": "elevenlabs",
        "label": "ElevenLabs Human Pro",
        "healthy": bool(settings.get("api_key")),
        "installed": bool(settings.get("api_key")),
        "tasks": ["speech_clone"],
        "detail": "API key configured" if settings.get("api_key") else "API key missing",
    }
    remote = await asyncio.gather(*(_remote_health(name, value) for name, value in REMOTE_ENGINES.items()))
    return [local, eleven, *remote]


def _engine_unavailable_detail(statuses: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "error_code": "ENGINE_NOT_AVAILABLE",
        "message": "لا يوجد محرك استنساخ جاهز. جهّز XTTS المحلي مرة واحدة ثم أعد المحاولة.",
        "setup_endpoint": "/api/voice-ai/setup/xtts",
        "status_endpoint": "/api/voice-ai/engines",
        "windows_command": "UPDATE_AND_INSTALL_VOICE_CLONE_PRO_7.bat",
        "engines": statuses,
    }


def _candidate_quality(result: dict[str, Any]) -> float:
    path = Path(str(result.get("file") or ""))
    if not path.exists():
        return 0.0
    size_score = min(1.0, math.log10(max(path.stat().st_size, 1)) / 7.0)
    return round(size_score, 6)


async def _remote_clone(
    engine: str,
    files: list[UploadFile],
    text: str,
    language: str,
    quality_mode: str,
) -> dict[str, Any]:
    definition = REMOTE_ENGINES[engine]
    endpoint = os.getenv(definition["env"], definition["default"]).rstrip("/")
    multipart: list[tuple[str, tuple[str, bytes, str]]] = []
    for index, upload in enumerate(files, start=1):
        content = await upload.read()
        await upload.seek(0)
        multipart.append(
            (
                "files",
                (
                    Path(upload.filename or f"reference_{index}.wav").name,
                    content,
                    upload.content_type or "application/octet-stream",
                ),
            )
        )
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(3600, connect=10)) as client:
            response = await client.post(
                endpoint + "/clone",
                files=multipart,
                data={"text": text, "language": language, "quality_mode": quality_mode},
            )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "ENGINE_RUNTIME_OFFLINE",
                "message": f"محرك {definition['label']} غير مشغّل.",
                "endpoint": endpoint,
                "detail": str(exc),
            },
        ) from exc
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "error_code": "ENGINE_RUNTIME_FAILED",
                "message": f"فشل محرك {definition['label']} في إنشاء الصوت.",
                "detail": response.text[-3000:],
            },
        )
    payload = response.json()
    if not payload.get("success", True):
        raise HTTPException(status_code=502, detail=payload)
    payload.setdefault("engine", engine)
    payload.setdefault("exact_match_guaranteed", False)
    return payload


def _run_pack_installer(include_music: bool) -> None:
    global _INSTALL_THREAD
    try:
        _write_pack_status("installing", 2, "بدأ تجهيز حزمة Voice Clone Pro 7...")
        script = Path(__file__).resolve().parents[2] / "scripts" / "install_voice_clone_engine_pack.py"
        if not script.exists():
            raise RuntimeError("ملف تثبيت حزمة المحركات غير موجود.")
        command = [os.fspath(shutil.which("python") or "python"), str(script), "--all", "--accept-licenses"]
        if include_music:
            command.append("--include-music")
        import subprocess

        completed = subprocess.run(command, capture_output=True, text=True, timeout=8 * 3600, check=False)
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "فشل المثبت")[-4000:])
        _write_pack_status("completed", 100, "اكتمل تجهيز مصادر المحركات. شغّل الـruntimes المطلوبة من مركز المحركات.")
    except Exception as exc:
        logger.exception("Voice engine pack installation failed")
        _write_pack_status("failed", 0, "فشل تجهيز حزمة المحركات.", str(exc))
    finally:
        _INSTALL_THREAD = None
        if _INSTALL_LOCK.locked():
            _INSTALL_LOCK.release()


@router.get("/engines")
async def engines_status():
    statuses = await _engine_statuses()
    return {
        "success": True,
        "version": APP_VERSION,
        "release": APP_RELEASE,
        "engines": statuses,
        "speech_clone_ready": any(
            item["healthy"] and "speech_clone" in item.get("tasks", []) for item in statuses
        ),
        "engine_pack": _read_pack_status(),
        "exact_match_guaranteed": False,
    }


@router.post("/setup/xtts")
async def setup_xtts(accept_model_license: bool = Form(...)):
    return await setup_local(accept_model_license)


@router.post("/setup/all")
async def setup_all(
    accept_model_licenses: bool = Form(...),
    include_music: bool = Form(False),
):
    global _INSTALL_THREAD
    if not accept_model_licenses:
        raise HTTPException(status_code=400, detail="يجب قبول تراخيص النماذج قبل التنزيل.")
    if _INSTALL_THREAD and _INSTALL_THREAD.is_alive():
        return {"success": True, "started": False, "status": _read_pack_status()}
    if not _INSTALL_LOCK.acquire(blocking=False):
        return {"success": True, "started": False, "status": _read_pack_status()}
    _INSTALL_THREAD = threading.Thread(
        target=_run_pack_installer,
        args=(include_music,),
        name="voice-engine-pack-v7",
        daemon=True,
    )
    _INSTALL_THREAD.start()
    return {
        "success": True,
        "started": True,
        "message": "بدأ تجهيز المحركات في الخلفية. لا تغلق البرنامج.",
    }


@router.post("/audio/clone/ensemble")
async def clone_voice_ensemble(
    files: list[UploadFile] = File(...),
    text: str = Form(...),
    engine: str = Form("auto"),
    language: str = Form("ar"),
    quality_mode: str = Form("high"),
    candidate_count: int = Form(3),
    consent_confirmed: bool = Form(...),
    accept_model_license: bool = Form(False),
    owner_name: str = Form("صاحب الصوت"),
    profile_name: str = Form("صوت Voice Clone Pro 7"),
):
    if not consent_confirmed:
        raise HTTPException(status_code=403, detail={"error_code": "CONSENT_REQUIRED", "message": "يلزم إذن صاحب الصوت."})
    if not text.strip():
        raise HTTPException(status_code=400, detail="اكتب النص المطلوب.")
    if not files:
        raise HTTPException(status_code=400, detail="ارفع عينة صوتية واحدة على الأقل.")

    requested = _normalize_engine(engine)
    statuses = await _engine_statuses()
    healthy = {item["name"]: item for item in statuses if item.get("healthy")}
    if requested == "auto":
        for preferred in ("xtts", "elevenlabs", "f5tts", "gpt_sovits", "openvoice", "cosyvoice"):
            if preferred in healthy:
                requested = preferred
                break
        else:
            if accept_model_license:
                await setup_local(True)
            raise HTTPException(status_code=503, detail=_engine_unavailable_detail(statuses))

    if requested in REMOTE_ENGINES:
        if requested not in healthy:
            raise HTTPException(status_code=503, detail=_engine_unavailable_detail(statuses))
        return await _remote_clone(requested, files, text.strip(), language, quality_mode)

    if requested not in {"xtts", "elevenlabs"}:
        raise HTTPException(status_code=400, detail={"error_code": "ENGINE_NOT_SUPPORTED", "engine": requested})
    if requested == "xtts" and not _xtts_ready():
        if accept_model_license:
            await setup_local(True)
        raise HTTPException(status_code=503, detail=_engine_unavailable_detail(statuses))
    if requested == "elevenlabs" and not _human_settings().get("api_key"):
        raise HTTPException(status_code=503, detail={"error_code": "ELEVENLABS_KEY_REQUIRED", "message": "أضف مفتاح ElevenLabs أولًا."})

    manifest = await create_profile_from_uploads(
        files,
        name=profile_name,
        owner_name=owner_name,
        consent=True,
        consent_statement="أؤكد أنني صاحب هذا الصوت أو لدي إذن صريح من صاحبه لاستخدامه في الاستنساخ.",
    )
    profile_id = str(manifest["id"])
    limit_by_mode = {"fast": 1, "balanced": 2, "high": 3, "ultra": 4}
    total = max(1, min(int(candidate_count), limit_by_mode.get(quality_mode, 3), 4))
    styles = ["natural", "warm", "story", "broadcast"]
    candidates: list[dict[str, Any]] = []
    for index in range(total):
        request = GenerateCloneRequest(
            profile_id=profile_id,
            text=text.strip(),
            provider="local" if requested == "xtts" else "elevenlabs",
            language=language,
            speed=1.0,
            style=styles[index % len(styles)],
        )
        try:
            result = await generate_from_profile(request)
            result["candidate_index"] = index + 1
            result["candidate_score"] = _candidate_quality(result)
            candidates.append(result)
        except HTTPException:
            if not candidates:
                raise
        except Exception as exc:
            logger.exception("Candidate %s failed", index + 1)
            if not candidates:
                raise HTTPException(status_code=502, detail={"error_code": "INFERENCE_FAILED", "message": str(exc)}) from exc
    if not candidates:
        raise HTTPException(status_code=502, detail={"error_code": "NO_VALID_CANDIDATE", "message": "لم ينتج أي ملف صالح."})
    selected = max(candidates, key=lambda item: float(item.get("candidate_score") or 0.0))
    return {
        "success": True,
        "version": APP_VERSION,
        "release": APP_RELEASE,
        "engine": requested,
        "quality_mode": quality_mode,
        "profile_id": profile_id,
        "candidate_count": len(candidates),
        "selected_candidate": selected["candidate_index"],
        "url": selected.get("url"),
        "file": selected.get("file"),
        "desktop_project": selected.get("desktop_project"),
        "candidates": candidates,
        "exact_match_guaranteed": False,
        "message": "تم إنشاء عدة نتائج واختيار أفضل ملف صالح. التشابه يعتمد على جودة العينة والنموذج.",
    }


@router.post("/song/generate")
async def generate_song(
    lyrics: str = Form(...),
    engine: str = Form("ace_step"),
    style: str = Form("Arabic sheilah"),
    consent_confirmed: bool = Form(...),
):
    if not consent_confirmed:
        raise HTTPException(status_code=403, detail={"error_code": "CONSENT_REQUIRED"})
    name = _normalize_engine(engine)
    if name not in {"ace_step", "yue"}:
        raise HTTPException(status_code=400, detail="محرك الأغنية يجب أن يكون ACE-Step أو YuE.")
    definition = REMOTE_ENGINES[name]
    status = await _remote_health(name, definition)
    if not status["healthy"]:
        raise HTTPException(status_code=503, detail={"error_code": "SONG_ENGINE_OFFLINE", "engine": name, "status": status})
    endpoint = os.getenv(definition["env"], definition["default"]).rstrip("/")
    async with httpx.AsyncClient(timeout=httpx.Timeout(7200, connect=10)) as client:
        response = await client.post(endpoint + "/song/generate", json={"lyrics": lyrics, "style": style})
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=response.text[-3000:])
    payload = response.json()
    payload.setdefault("engine", name)
    payload.setdefault("exact_match_guaranteed", False)
    return payload
