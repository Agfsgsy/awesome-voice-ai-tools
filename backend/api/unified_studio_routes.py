"""Unified stable API contracts for Ibn Al-Waqadi Studio.

This module is the single public contract layer for the desktop studio. It keeps the
existing implementation modules intact, but exposes request bodies explicitly so a
packaged build can never interpret a JSON payload as a missing query parameter.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from backend.api.interview_pro_routes import (
    RenderRequest,
    ScenarioRequest,
    create_scenario as _create_interview_scenario,
    render as _render_interview,
)
from backend.core.config import APP_NAME, APP_RELEASE, APP_VERSION, ENGINE_PRIORITY, OUTPUTS_DIR
from backend.core import gemini_key_pool


# Compatibility router keeps the existing frontend URLs working. The original
# interview router is intentionally not mounted in main.py; all calls pass through
# this explicit Body(...) contract instead.
interview_router = APIRouter(prefix="/api/interview-pro", tags=["Interview Pro — Unified"])
studio_router = APIRouter(prefix="/api/studio", tags=["Studio Unified Control"])


@interview_router.post("/scenario")
async def interview_scenario(payload: ScenarioRequest = Body(...)):
    return await _create_interview_scenario(payload)


@interview_router.post("/render")
async def interview_render(payload: RenderRequest = Body(...)):
    return await _render_interview(payload)


# Canonical v1 URLs for future frontends and external clients.
@studio_router.post("/v1/interviews/scenario")
async def studio_interview_scenario(payload: ScenarioRequest = Body(...)):
    return await _create_interview_scenario(payload)


@studio_router.post("/v1/interviews/render")
async def studio_interview_render(payload: RenderRequest = Body(...)):
    return await _render_interview(payload)


def _safe_job_id(value: str) -> str:
    value = (value or "").strip().lower()
    if not re.fullmatch(r"[a-f0-9]{18}", value):
        raise HTTPException(status_code=400, detail="معرّف المهمة غير صالح.")
    return value


@studio_router.get("/v1/interviews/progress/{job_id}")
async def interview_progress(job_id: str):
    job_id = _safe_job_id(job_id)
    work = OUTPUTS_DIR / "interview_jobs" / job_id
    manifest = work / "progress.json"
    final = OUTPUTS_DIR / f"ibn_alwaqadi_podcast_{job_id}.mp3"

    if final.exists() and final.stat().st_size > 256:
        return {
            "success": True,
            "job_id": job_id,
            "status": "completed",
            "completed": True,
            "url": f"/api/downloads/{final.name}",
        }
    if not manifest.exists():
        return {
            "success": True,
            "job_id": job_id,
            "status": "not_started",
            "completed": False,
            "completed_segments": 0,
        }
    try:
        data: dict[str, Any] = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"تعذر قراءة حالة المهمة: {type(exc).__name__}") from exc
    data.update({"success": True, "job_id": job_id, "completed": data.get("status") == "completed"})
    return data


@studio_router.get("/version")
async def studio_version():
    return {
        "success": True,
        "name": APP_NAME,
        "version": APP_VERSION,
        "release": APP_RELEASE,
        "update_channel": "free-first",
    }


@studio_router.get("/health")
async def studio_health():
    entries = gemini_key_pool.load_entries()
    enabled = [entry for entry in entries if entry.get("enabled", True)]
    return {
        "success": True,
        "name": APP_NAME,
        "version": APP_VERSION,
        "release": APP_RELEASE,
        "cloud_only": False,
        "free_first": True,
        "default_engine": ENGINE_PRIORITY[0],
        "automatic_free_fallback": True,
        "explicit_cloud_choice_is_strict": True,
        "interview_request_contract": "application/json body",
        "persistent_sessions": True,
        "resumable_interviews": True,
        "gemini_keys": {"total": len(entries), "enabled": len(enabled)},
    }
