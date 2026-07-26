"""Professional dashboard endpoints for Ibn Al-Waqadi Studio.

This module is additive. It exposes sanitized local status information and a safe
command to open the desktop exports folder from the Windows application.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from backend.api.studio_pro_routes import _desktop_exports
from backend.core.config import APP_NAME, APP_VERSION, CONFIG_DIR
from backend.core.gemini_key_pool import key_statuses, load_keys
from backend.core.tts_registry import tts_registry

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
    except Exception:
        pass
    return {}


def _recent_exports(limit: int = 6) -> tuple[int, list[dict[str, Any]]]:
    folder = _desktop_exports()
    folder.mkdir(parents=True, exist_ok=True)
    files = [item for item in folder.iterdir() if item.is_file()]
    files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    recent: list[dict[str, Any]] = []
    for item in files[:limit]:
        stat = item.stat()
        recent.append({
            "name": item.name,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "modified": int(stat.st_mtime),
        })
    return len(files), recent


@router.get("/status")
async def dashboard_status():
    keys = load_keys()
    statuses = key_statuses()
    working = sum(1 for item in statuses if item.get("status") == "working")
    quota = sum(1 for item in statuses if item.get("status") == "quota")
    untested = sum(1 for item in statuses if item.get("status") in {None, "", "untested"})

    available_engines: list[dict[str, str]] = []
    try:
        for engine in tts_registry.get_available_engines():
            available_engines.append({"name": str(engine.get("name", "")), "label": str(engine.get("label", ""))})
    except Exception:
        available_engines = []

    human_pro = _read_json(CONFIG_DIR / "human_pro.json")
    dialogue = _read_json(CONFIG_DIR / "dialogue_ultra.json")
    export_count, recent = _recent_exports()

    return {
        "success": True,
        "app": {"name": APP_NAME, "version": APP_VERSION},
        "gemini": {
            "count": len(keys),
            "working": working,
            "quota": quota,
            "untested": untested,
            "statuses": statuses,
        },
        "elevenlabs": {
            "configured": bool(human_pro.get("api_key") or dialogue.get("eleven_api_key")),
            "dialogue_voices": sum(1 for key, value in dialogue.items() if key.endswith("_voice_id") and str(value).strip()),
        },
        "engines": available_engines,
        "exports": {
            "path": str(_desktop_exports()),
            "count": export_count,
            "recent": recent,
        },
    }


@router.post("/open-exports")
async def open_exports_folder():
    folder = _desktop_exports()
    folder.mkdir(parents=True, exist_ok=True)
    try:
        if sys.platform == "win32":
            os.startfile(str(folder))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"تعذر فتح مجلد الملفات: {exc}")
    return {"success": True, "path": str(folder), "message": "تم فتح مجلد ملفات الاستوديو."}
