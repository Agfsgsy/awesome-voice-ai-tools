"""Gemini settings, multiple-key rotation, guided links, diagnostics, and safe URL import."""
from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
from html.parser import HTMLParser
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
    api_keys: str = Field(default="", max_length=8000)
    model_id: str = Field(default="gemini-2.5-flash-preview-tts", max_length=100)
    voice_name: str = Field(default="Kore", max_length=50)


class UrlImportRequest(BaseModel):
    url: HttpUrl
    max_chars: int = Field(default=8000, ge=500, le=30000)


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


def _parse_keys(raw: str) -> list[str]:
    return list(dict.fromkeys(k.strip() for k in re.split(r"[\n,;|]+", raw or "") if len(k.strip()) >= 20))


def _load() -> dict:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def apply_saved_settings() -> None:
    data = _load()
    keys = data.get("api_keys") or ([data.get("api_key")] if data.get("api_key") else [])
    keys = [str(k).strip() for k in keys if str(k).strip()]
    model = str(data.get("model_id", "")).strip()
    if keys:
        os.environ["GEMINI_API_KEYS"] = "||".join(keys)
        os.environ["GEMINI_API_KEY"] = keys[0]
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
    keys = data.get("api_keys") or ([data.get("api_key")] if data.get("api_key") else [])
    return {
        "configured": bool(keys),
        "key_count": len(keys),
        "model_id": data.get("model_id", "gemini-2.5-flash-preview-tts"),
        "voice_name": data.get("voice_name", "Kore"),
        "links": LINKS,
    }


@router.post("/settings")
async def save_settings(settings: GeminiSettings):
    previous = _load()
    raw = settings.api_keys.strip() or settings.api_key.strip()
    keys = _parse_keys(raw) if raw else list(previous.get("api_keys", []))
    if not keys and previous.get("api_key"):
        keys = [str(previous["api_key"]).strip()]
    allowed_models = {
        "gemini-3.1-flash-tts-preview",
        "gemini-2.5-flash-preview-tts",
        "gemini-2.5-pro-preview-tts",
    }
    model_id = settings.model_id if settings.model_id in allowed_models else "gemini-2.5-flash-preview-tts"
    data = {"api_keys": keys, "model_id": model_id, "voice_name": settings.voice_name.strip() or "Kore"}
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    apply_saved_settings()
    return {"success": True, "configured": bool(keys), "key_count": len(keys), "message": f"تم حفظ {len(keys)} مفتاح Gemini، والتبديل التلقائي جاهز."}


@router.post("/test")
async def test_keys():
    data = _load()
    keys = list(data.get("api_keys", []))
    if not keys:
        raise HTTPException(status_code=400, detail="احفظ مفتاح Gemini واحدًا على الأقل.")
    results = []
    visible_models = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for index, key in enumerate(keys, start=1):
            try:
                response = await client.get("https://generativelanguage.googleapis.com/v1beta/models", headers={"x-goog-api-key": key})
                if response.status_code < 400:
                    models = [item.get("name", "") for item in response.json().get("models", [])]
                    visible_models = [m for m in models if "tts" in m.lower()]
                    results.append({"number": index, "ok": True})
                else:
                    results.append({"number": index, "ok": False, "status": response.status_code})
            except Exception:
                results.append({"number": index, "ok": False, "status": "network"})
    working = sum(1 for item in results if item["ok"])
    if not working:
        raise HTTPException(status_code=401, detail="لم يعمل أي مفتاح Gemini محفوظ.")
    return {"success": True, "message": f"يعمل {working} من أصل {len(keys)} مفاتيح. التبديل التلقائي مفعّل.", "results": results, "tts_models_visible": visible_models}


@router.post("/import-url")
async def import_url(request: UrlImportRequest):
    parsed = urlparse(str(request.url))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail="استخدم رابط HTTP أو HTTPS صحيحًا.")
    _safe_public_host(parsed.hostname)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=10.0), follow_redirects=True, headers={"User-Agent": "VoiceAIStudioArabic/2.6"}) as client:
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
            parser = _TextExtractor(); parser.feed(response.text); text = "\n".join(parser.parts)
        lines, seen = [], set()
        for raw in text.splitlines():
            line = " ".join(raw.split()).strip()
            if len(line) < 3 or line in seen:
                continue
            seen.add(line); lines.append(line)
        clean = "\n".join(lines)[: request.max_chars]
        if not clean:
            raise HTTPException(status_code=422, detail="لم أجد نصًا واضحًا داخل الرابط.")
        return {"success": True, "text": clean, "chars": len(clean), "source": str(response.url), "message": "تم جلب النص من الرابط. اضغط الآن فهم وترتيب النص."}
    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"الموقع أعاد خطأ {exc.response.status_code}.")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"تعذر قراءة الرابط: {exc}")
