"""Gemini settings, guided links, key diagnostics, and safe URL text import."""
from __future__ import annotations

import ipaddress
import json
import os
import socket
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from backend.core.config import CONFIG_DIR

router = APIRouter(prefix="/api/gemini", tags=["Gemini"])
SETTINGS_FILE = CONFIG_DIR / "gemini.json"

LINKS = {
    "create_key": "https://aistudio.google.com/app/apikey",
    "billing": "https://aistudio.google.com/app/billing",
    "usage": "https://aistudio.google.com/app/usage",
    "voice_lab": "https://aistudio.google.com/generate-speech",
    "docs": "https://ai.google.dev/gemini-api/docs/speech-generation",
}


class GeminiSettings(BaseModel):
    api_key: str = Field(default="", max_length=500)
    model_id: str = Field(default="gemini-2.5-flash-preview-tts", max_length=100)
    voice_name: str = Field(default="Kore", max_length=50)


class UrlImportRequest(BaseModel):
    url: HttpUrl
    max_chars: int = Field(default=8000, ge=500, le=20000)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            text = " ".join(data.split())
            if text:
                self.parts.append(text)


def _load() -> dict:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def apply_saved_settings() -> None:
    data = _load()
    key = str(data.get("api_key", "")).strip()
    model = str(data.get("model_id", "")).strip()
    if key:
        os.environ["GEMINI_API_KEY"] = key
    if model:
        os.environ["GEMINI_TTS_MODEL"] = model


apply_saved_settings()


def _safe_public_host(hostname: str) -> None:
    if hostname.lower() in {"localhost", "localhost.localdomain"}:
        raise HTTPException(status_code=400, detail="الروابط المحلية غير مسموحة.")
    try:
        addresses = socket.getaddrinfo(hostname, None)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"تعذر الوصول إلى اسم الموقع: {exc}")
    for item in addresses:
        address = ipaddress.ip_address(item[4][0])
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast:
            raise HTTPException(status_code=400, detail="هذا الرابط يشير إلى عنوان داخلي غير مسموح.")


@router.get("/links")
async def get_links():
    return LINKS


@router.get("/settings")
async def get_settings():
    data = _load()
    return {
        "configured": bool(data.get("api_key")),
        "api_key_set": bool(data.get("api_key")),
        "model_id": data.get("model_id", "gemini-2.5-flash-preview-tts"),
        "voice_name": data.get("voice_name", "Kore"),
        "links": LINKS,
    }


@router.post("/settings")
async def save_settings(settings: GeminiSettings):
    previous = _load()
    api_key = settings.api_key.strip() or str(previous.get("api_key", "")).strip()
    if api_key and len(api_key) < 20:
        raise HTTPException(status_code=400, detail="مفتاح Gemini قصير أو غير مكتمل.")
    allowed_models = {
        "gemini-3.1-flash-tts-preview",
        "gemini-2.5-flash-preview-tts",
        "gemini-2.5-pro-preview-tts",
    }
    model_id = settings.model_id if settings.model_id in allowed_models else "gemini-2.5-flash-preview-tts"
    data = {"api_key": api_key, "model_id": model_id, "voice_name": settings.voice_name.strip() or "Kore"}
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    apply_saved_settings()
    return {"success": True, "configured": bool(api_key), "message": "تم حفظ إعداد Gemini على هذا الجهاز."}


@router.post("/test")
async def test_key():
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="احفظ مفتاح Gemini أولًا.")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                headers={"x-goog-api-key": api_key},
            )
        if response.status_code >= 400:
            try:
                detail = response.json().get("error", {}).get("message") or response.text[:500]
            except Exception:
                detail = response.text[:500]
            raise HTTPException(status_code=response.status_code, detail=detail)
        models = [item.get("name", "") for item in response.json().get("models", [])]
        return {"success": True, "message": "مفتاح Gemini صالح ويعمل.", "tts_models_visible": [m for m in models if "tts" in m.lower()]}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"تعذر اختبار Gemini: {exc}")


@router.post("/import-url")
async def import_url(request: UrlImportRequest):
    parsed = urlparse(str(request.url))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail="استخدم رابط HTTP أو HTTPS صحيحًا.")
    _safe_public_host(parsed.hostname)
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(25.0, connect=10.0),
            follow_redirects=True,
            headers={"User-Agent": "VoiceAIStudioArabic/2.5"},
        ) as client:
            response = await client.get(str(request.url))
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            raise HTTPException(status_code=400, detail="الرابط لا يحتوي على صفحة نصية مدعومة.")
        if len(response.content) > 3_000_000:
            raise HTTPException(status_code=413, detail="الصفحة كبيرة جدًا.")
        if "text/plain" in content_type:
            text = response.text
        else:
            parser = _TextExtractor()
            parser.feed(response.text)
            text = "\n".join(parser.parts)
        lines = []
        seen = set()
        for raw in text.splitlines():
            line = " ".join(raw.split()).strip()
            if len(line) < 3 or line in seen:
                continue
            seen.add(line)
            lines.append(line)
        clean = "\n".join(lines)[: request.max_chars]
        if not clean:
            raise HTTPException(status_code=422, detail="لم أجد نصًا واضحًا داخل الرابط.")
        return {"success": True, "text": clean, "chars": len(clean), "source": str(response.url), "message": "تم جلب النص من الرابط. راجعه قبل إنشاء الصوت."}
    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"الموقع أعاد خطأ {exc.response.status_code}.")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"تعذر قراءة الرابط: {exc}")
