"""Gemini settings, per-key controls, persistent rotation, diagnostics and URL import."""
from __future__ import annotations

import base64
import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from backend.core.gemini_key_pool import (
    append_keys,
    apply_environment,
    key_status_by_id,
    key_statuses,
    load_config,
    load_entries,
    load_keys,
    parse_keys,
    record_result,
    save_config,
    set_active_key,
    set_key_enabled,
)

router = APIRouter(prefix="/api/gemini", tags=["Gemini"])

LINKS = {
    "create_key": "https://aistudio.google.com/app/apikey",
    "billing": "https://aistudio.google.com/app/billing",
    "usage": "https://aistudio.google.com/app/usage",
    "voice_lab": "https://aistudio.google.com/generate-speech",
    "docs": "https://ai.google.dev/gemini-api/docs/speech-generation",
}

ALLOWED_MODELS = {
    "gemini-3.1-flash-tts-preview",
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-preview-tts",
}


class GeminiSettings(BaseModel):
    api_key: str = Field(default="", max_length=500)
    api_keys: str = Field(default="", max_length=16000)
    model_id: str = Field(default="gemini-2.5-flash-preview-tts", max_length=100)
    voice_name: str = Field(default="Kore", max_length=50)
    replace_existing: bool = False
    label: str = Field(default="", max_length=80)


class KeyAddRequest(BaseModel):
    api_keys: str = Field(min_length=10, max_length=16000)
    label: str = Field(default="", max_length=80)


class KeyToggleRequest(BaseModel):
    enabled: bool


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


def apply_saved_settings() -> None:
    data = load_config()
    apply_environment(load_keys(enabled_only=True), str(data.get("model_id", "")).strip() or None)


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


def _extract_audio(payload: dict) -> bytes | None:
    for candidate in payload.get("candidates") or []:
        for part in (candidate.get("content") or {}).get("parts") or []:
            inline = part.get("inlineData") or part.get("inline_data") or {}
            data = inline.get("data")
            if data:
                try:
                    return base64.b64decode(data)
                except Exception:
                    return None
    return None


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            return str((payload.get("error") or {}).get("message") or payload.get("message") or response.text[:500])
    except Exception:
        pass
    return response.text[:500]


def _models() -> list[str]:
    data = load_config()
    preferred = str(data.get("model_id") or "gemini-2.5-flash-preview-tts")
    return list(dict.fromkeys([preferred, "gemini-2.5-flash-preview-tts", "gemini-3.1-flash-tts-preview", "gemini-2.5-pro-preview-tts"]))


async def _test_one(key: str, number: int = 1) -> dict:
    outcome = {"number": number, "ok": False, "status": "failed", "model": "", "detail": ""}
    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=20.0)) as client:
        for model in _models():
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            payload = {
                "contents": [{"parts": [{"text": "اقرأ هذه العبارة فقط بصوت واضح: اختبار المفتاح."}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {"languageCode": "ar-XA", "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}},
                },
            }
            try:
                response = await client.post(endpoint, headers={"x-goog-api-key": key, "Content-Type": "application/json"}, json=payload)
                if response.status_code == 429:
                    outcome.update(status="quota", detail="الحصة أو حد الطلبات غير متاح لهذا المفتاح حاليًا.")
                    record_result(key, "quota", outcome["detail"])
                    break
                if response.status_code == 401:
                    outcome.update(status="invalid", detail="المفتاح غير صحيح أو تم إلغاؤه.")
                    record_result(key, "invalid", outcome["detail"])
                    break
                if response.status_code == 403:
                    outcome.update(status="forbidden", detail="المفتاح موجود لكن الصلاحية أو المشروع أو المنطقة تمنع إنشاء الصوت.")
                    record_result(key, "forbidden", outcome["detail"])
                    break
                if response.status_code in {400, 404}:
                    outcome.update(status="model_unavailable", detail=f"النموذج {model} غير متاح لهذا المشروع.")
                    continue
                if response.status_code >= 400:
                    outcome.update(status="failed", detail=_error_detail(response))
                    continue
                audio = _extract_audio(response.json())
                if not audio:
                    outcome.update(status="no_audio", detail=f"نجح الطلب على {model} لكنه لم يرجع صوتًا.")
                    continue
                outcome.update(ok=True, status="working", model=model, detail="تم إنشاء عينة صوتية فعلية بهذا المفتاح.")
                record_result(key, "working", model)
                break
            except Exception as exc:
                outcome.update(status="network", detail=f"تعذر الاتصال: {type(exc).__name__}")
    return outcome


def _key_payload() -> dict:
    statuses = key_statuses()
    return {
        "success": True,
        "total": len(statuses),
        "enabled": sum(1 for item in statuses if item.get("enabled")),
        "working": sum(1 for item in statuses if item.get("status") == "working"),
        "active_id": next((item["id"] for item in statuses if item.get("active")), ""),
        "keys": statuses,
    }


@router.get("/links")
async def get_links():
    return LINKS


@router.get("/settings")
async def get_settings():
    data = load_config()
    payload = _key_payload()
    payload.update({
        "configured": bool(payload["total"]),
        "key_count": payload["total"],
        "statuses": payload["keys"],
        "model_id": data.get("model_id", "gemini-2.5-flash-preview-tts"),
        "voice_name": data.get("voice_name", "Kore"),
        "append_mode": True,
        "links": LINKS,
    })
    return payload


@router.get("/keys")
async def list_key_controls():
    return _key_payload()


@router.post("/settings")
async def save_settings(settings: GeminiSettings):
    previous = load_config()
    model_id = settings.model_id if settings.model_id in ALLOWED_MODELS else str(previous.get("model_id") or "gemini-2.5-flash-preview-tts")
    voice_name = settings.voice_name.strip() or str(previous.get("voice_name") or "Kore")
    raw = settings.api_keys.strip() or settings.api_key.strip()
    incoming = parse_keys(raw)
    if raw and not incoming:
        raise HTTPException(status_code=400, detail="لم أجد مفتاح Gemini كاملًا. الصق كل مفتاح كاملًا في سطر مستقل.")
    if incoming:
        keys = append_keys(incoming, model_id, voice_name, replace=settings.replace_existing, label=settings.label)
    else:
        entries = load_entries()
        save_config(entries, model_id, voice_name)
        keys = load_keys()
    payload = _key_payload()
    payload.update({
        "configured": bool(keys),
        "key_count": len(keys),
        "message": f"تم حفظ المفاتيح. الإجمالي {payload['total']}، والمفعّل {payload['enabled']}. استخدم لوحة المفاتيح لتشغيل أو إيقاف أو اختيار أي مفتاح.",
    })
    return payload


@router.post("/keys/add")
async def add_keys(request: KeyAddRequest):
    incoming = parse_keys(request.api_keys)
    if not incoming:
        raise HTTPException(status_code=400, detail="لم أجد مفتاح Gemini كاملًا.")
    data = load_config()
    append_keys(incoming, str(data.get("model_id") or "gemini-2.5-flash-preview-tts"), str(data.get("voice_name") or "Kore"), label=request.label)
    payload = _key_payload()
    payload["message"] = f"تمت إضافة {len(incoming)} مفتاح. الإجمالي الآن {payload['total']} والمفعّل {payload['enabled']}."
    return payload


@router.post("/keys/{key_id}/toggle")
async def toggle_key(key_id: str, request: KeyToggleRequest):
    try:
        item = set_key_enabled(key_id, request.enabled)
    except KeyError:
        raise HTTPException(status_code=404, detail="المفتاح غير موجود.")
    payload = _key_payload()
    payload["key"] = item
    payload["message"] = "تم تشغيل المفتاح." if request.enabled else "تم إيقاف المفتاح ولن يستخدمه الاستوديو."
    return payload


@router.post("/keys/{key_id}/activate")
async def activate_key(key_id: str):
    try:
        item = set_active_key(key_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="المفتاح غير موجود.")
    payload = _key_payload()
    payload["key"] = item
    payload["message"] = "تم اختيار هذا المفتاح للاستخدام الآن. سيبقى نشطًا ما دام يعمل."
    return payload


@router.post("/keys/{key_id}/test")
async def test_single_key(key_id: str):
    entries = load_entries()
    match = next(((index, entry) for index, entry in enumerate(entries, start=1) if key_status_by_id(key_id)["id"] == key_id and key_status_by_id(key_id)["number"] == index), None)
    if not match:
        raise HTTPException(status_code=404, detail="المفتاح غير موجود.")
    index, entry = match
    outcome = await _test_one(entry["key"], index)
    payload = _key_payload()
    payload["result"] = outcome
    payload["message"] = "المفتاح يعمل ويمكن تشغيله." if outcome["ok"] else f"نتيجة المفتاح: {outcome['status']} — {outcome['detail']}"
    return payload


@router.post("/test")
async def test_keys():
    entries = load_entries()
    if not entries:
        raise HTTPException(status_code=400, detail="احفظ مفتاح Gemini واحدًا على الأقل.")
    results: list[dict] = []
    for index, entry in enumerate(entries, start=1):
        outcome = await _test_one(entry["key"], index)
        outcome["enabled"] = bool(entry.get("enabled", True))
        results.append(outcome)
    working = sum(1 for item in results if item["ok"])
    payload = _key_payload()
    payload.update({"results": results, "working": working, "message": f"تم اختبار {len(entries)} مفتاح فعليًا. يعمل {working} منها. افتح لوحة المفاتيح لاختيار المفتاح الذي تريد استخدامه."})
    if not working:
        payload["warning"] = "لم ينجح إنشاء الصوت بأي مفتاح حاليًا. راجع حالة كل مفتاح في اللوحة."
    return payload


@router.post("/import-url")
async def import_url(request: UrlImportRequest):
    parsed = urlparse(str(request.url))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail="استخدم رابط HTTP أو HTTPS صحيحًا.")
    _safe_public_host(parsed.hostname)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=10.0), follow_redirects=True, headers={"User-Agent": "IbnAlWaqadiStudio/3.5"}) as client:
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
