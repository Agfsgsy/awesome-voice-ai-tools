"""Local-only settings routes for Human Pro voice providers."""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.config import CONFIG_DIR

router = APIRouter(prefix="/api/human-pro", tags=["Human Pro"])
SETTINGS_FILE = CONFIG_DIR / "human_pro.json"


class HumanProSettings(BaseModel):
    api_key: str = Field(default="", max_length=300)
    voice_id: str = Field(default="", max_length=120)
    model_id: str = Field(default="eleven_multilingual_v2", max_length=80)


def _load() -> dict:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def apply_saved_settings() -> None:
    data = _load()
    for file_key, env_key in (
        ("api_key", "ELEVENLABS_API_KEY"),
        ("voice_id", "ELEVENLABS_VOICE_ID"),
        ("model_id", "ELEVENLABS_MODEL_ID"),
    ):
        value = str(data.get(file_key, "")).strip()
        if value:
            os.environ[env_key] = value


apply_saved_settings()


@router.get("/settings")
async def get_human_pro_settings():
    data = _load()
    return {
        "configured": bool(data.get("api_key") and data.get("voice_id")),
        "api_key_set": bool(data.get("api_key")),
        "voice_id": data.get("voice_id", ""),
        "model_id": data.get("model_id", "eleven_multilingual_v2"),
    }


@router.post("/settings")
async def save_human_pro_settings(settings: HumanProSettings):
    api_key = settings.api_key.strip()
    voice_id = settings.voice_id.strip()
    model_id = settings.model_id.strip() or "eleven_multilingual_v2"
    if api_key and len(api_key) < 10:
        raise HTTPException(status_code=400, detail="مفتاح API قصير أو غير صحيح.")
    if voice_id and len(voice_id) < 8:
        raise HTTPException(status_code=400, detail="معرّف الصوت Voice ID غير صحيح.")

    previous = _load()
    if not api_key:
        api_key = str(previous.get("api_key", ""))
    data = {"api_key": api_key, "voice_id": voice_id, "model_id": model_id}
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    apply_saved_settings()
    return {"success": True, "configured": bool(api_key and voice_id), "message": "تم حفظ إعدادات Human Pro على هذا الجهاز."}
