"""Gemini settings, real per-key controls, testing, project links, and URL import."""
from __future__ import annotations

import base64
import ipaddress
import re
import socket
import webbrowser
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from backend.core.gemini_key_pool import (
    append_keys,
    apply_environment,
    delete_key,
    fingerprint,
    key_statuses,
    load_config,
    load_entries,
    ordered_keys,
    parse_keys,
    record_result,
    save_config,
    set_active_key,
    set_key_enabled,
)

router = APIRouter(prefix="/api/gemini", tags=["Gemini"])

LINKS = {
    "api_keys": "https://aistudio.google.com/app/apikey",
    "projects": "https://aistudio.google.com/app/projects",
    "usage": "https://aistudio.google.com/app/usage",
    "billing": "https://aistudio.google.com/app/billing",
    "speech_lab": "https://aistudio.google.com/generate-speech",
    "docs": "https://ai.google.dev/gemini-api/docs/api-key",
    "billing_docs": "https://ai.google.dev/gemini-api/docs/billing",
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
    auto_test: bool = True
    auto_activate: bool = True


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
    apply_environment(ordered_keys(), str(data.get("model_id", "")).strip() or None)


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


def _extract_text(payload: dict) -> str:
    values: list[str] = []
    for candidate in payload.get("candidates") or []:
        for part in (candidate.get("content") or {}).get("parts") or []:
            text = str(part.get("text") or "").strip()
            if text:
                values.append(text)
    return "\n".join(values).strip()


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            detail = str((payload.get("error") or {}).get("message") or payload.get("message") or response.text[:900])
        else:
            detail = response.text[:900]
    except Exception:
        detail = response.text[:900]
    return re.sub(r"\s+", " ", detail).strip()[:900]


def _tts_models() -> list[str]:
    data = load_config()
    preferred = str(data.get("model_id") or "gemini-2.5-flash-preview-tts")
    return list(dict.fromkeys([preferred, "gemini-2.5-flash-preview-tts", "gemini-3.1-flash-tts-preview", "gemini-2.5-pro-preview-tts"]))


async def _available_text_models(client: httpx.AsyncClient, key: str) -> list[str]:
    preferred = ["gemini-2.5-flash", "gemini-flash-latest"]
    try:
        response = await client.get("https://generativelanguage.googleapis.com/v1beta/models", headers={"x-goog-api-key": key})
        if response.status_code >= 400:
            return preferred
        available: list[str] = []
        for item in response.json().get("models", []):
            methods = item.get("supportedGenerationMethods") or []
            name = str(item.get("name", "")).replace("models/", "")
            low = name.lower()
            if "generateContent" not in methods:
                continue
            if any(token in low for token in ("tts", "image", "embedding", "aqa")):
                continue
            if name:
                available.append(name)
        ordered = [model for model in preferred if model in available]
        ordered.extend(model for model in available if model not in ordered)
        return ordered or preferred
    except Exception:
        return preferred


async def _test_one(key: str, number: int = 1) -> dict:
    outcome = {"number": number, "ok": False, "status": "failed", "model": "", "detail": "", "text_ok": False, "tts_ok": False, "text_model": "", "tts_model": "", "capabilities": []}
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=25.0)) as client:
        for model in (await _available_text_models(client, key))[:8]:
            try:
                response = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": "أجب بكلمة واحدة فقط: جاهز"}]}], "generationConfig": {"temperature": 0}},
                )
                if response.status_code in {401, 403, 429}:
                    outcome["detail"] = _error_detail(response)
                    outcome["status"] = "invalid" if response.status_code == 401 else ("forbidden" if response.status_code == 403 else "quota")
                    break
                if response.status_code in {400, 404}:
                    continue
                if response.status_code >= 400:
                    outcome["detail"] = _error_detail(response)
                    continue
                if _extract_text(response.json()):
                    outcome["text_ok"] = True
                    outcome["text_model"] = model
                    outcome["capabilities"].extend(["text", "rewrite", "sermons", "scripts"])
                    break
            except Exception as exc:
                outcome["status"] = "network"
                outcome["detail"] = f"تعذر اختبار النص: {type(exc).__name__}"

        for model in _tts_models():
            payload = {
                "contents": [{"parts": [{"text": "اقرأ هذه العبارة فقط بصوت واضح: اختبار المفتاح."}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {"languageCode": "ar-XA", "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}},
                },
            }
            try:
                response = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                    json=payload,
                )
                if response.status_code == 429:
                    outcome.update(status="quota", detail=_error_detail(response) or "الحصة أو حد الطلبات غير متاح.")
                    break
                if response.status_code == 401:
                    outcome.update(status="invalid", detail=_error_detail(response) or "المفتاح غير صحيح أو تم إلغاؤه.")
                    break
                if response.status_code == 403:
                    outcome.update(status="forbidden", detail=_error_detail(response) or "المشروع أو الصلاحية أو المنطقة تمنع إنشاء الصوت.")
                    break
                if response.status_code in {400, 404}:
                    outcome.update(status="model_unavailable", detail=f"النموذج {model} غير متاح لهذا المشروع.")
                    continue
                if response.status_code >= 400:
                    outcome.update(status="failed", detail=_error_detail(response))
                    continue
                if not _extract_audio(response.json()):
                    outcome.update(status="no_audio", detail=f"نجح الطلب على {model} لكنه لم يرجع بيانات صوتية.")
                    continue
                outcome.update(ok=True, status="working", model=model, tts_ok=True, tts_model=model, detail="نجح اختبار النص والصوت، والمفتاح جاهز للاستوديو." if outcome["text_ok"] else "نجح اختبار الصوت، لكن اختبار النص لم يكتمل.")
                outcome["capabilities"].extend(["tts", "single_voice", "interviews"])
                break
            except Exception as exc:
                outcome.update(status="network", detail=f"تعذر اختبار الصوت: {type(exc).__name__}")

    record_result(key, str(outcome["status"]), str(outcome["detail"]))
    return outcome


def _key_payload() -> dict:
    statuses = key_statuses()
    active = next((item for item in statuses if item.get("active")), None)
    selected = next((item for item in statuses if item.get("selected")), None)
    return {
        "success": True,
        "total": len(statuses),
        "enabled": sum(1 for item in statuses if item.get("enabled")),
        "working": sum(1 for item in statuses if item.get("working")),
        "active_id": active["id"] if active else "",
        "active_label": active["label"] if active else "",
        "selected_id": selected["id"] if selected else "",
        "selected_label": selected["label"] if selected else "",
        "keys": statuses,
        "links": LINKS,
        "connected_services": [
            {"id": "tts", "label": "إنشاء الصوت", "connected": bool(active)},
            {"id": "rewrite", "label": "ترتيب وتقوية النص", "connected": bool(active)},
            {"id": "sermons", "label": "توليد المواعظ", "connected": bool(active)},
            {"id": "scripts", "label": "سيناريوهات المقابلات", "connected": bool(active)},
            {"id": "dialogue", "label": "إنتاج الحوار والمقابلات", "connected": bool(active)},
        ],
    }


@router.get("/links")
async def get_links():
    return LINKS


@router.post("/open-link/{link_name}")
async def open_official_link(link_name: str):
    url = LINKS.get(link_name)
    if not url:
        raise HTTPException(status_code=404, detail="الرابط المطلوب غير موجود.")
    try:
        webbrowser.open(url, new=2)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"تعذر فتح المتصفح: {exc}")
    return {"success": True, "url": url, "message": "تم فتح الصفحة الرسمية في المتصفح."}


@router.get("/settings")
async def get_settings():
    data = load_config()
    payload = _key_payload()
    payload.update({"configured": bool(payload["total"]), "key_count": payload["total"], "statuses": payload["keys"], "model_id": data.get("model_id", "gemini-2.5-flash-preview-tts"), "voice_name": data.get("voice_name", "Kore"), "append_mode": True})
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
        append_keys(incoming, model_id, voice_name, replace=settings.replace_existing, label=settings.label)
    else:
        save_config(load_entries(), model_id, voice_name)
    payload = _key_payload()
    payload["message"] = f"تم حفظ المفاتيح. الإجمالي {payload['total']}، والمفعّل {payload['enabled']}."
    return payload


@router.post("/keys/add")
async def add_keys(request: KeyAddRequest):
    incoming = parse_keys(request.api_keys)
    if not incoming:
        raise HTTPException(status_code=400, detail="لم أجد مفتاح Gemini كاملًا.")
    data = load_config()
    before = {entry["key"] for entry in load_entries()}
    append_keys(incoming, str(data.get("model_id") or "gemini-2.5-flash-preview-tts"), str(data.get("voice_name") or "Kore"), label=request.label)
    entries = load_entries()
    new_entries = [(index, entry) for index, entry in enumerate(entries, start=1) if entry["key"] in incoming and entry["key"] not in before]
    if not new_entries:
        new_entries = [(index, entry) for index, entry in enumerate(entries, start=1) if entry["key"] in incoming]
    results: list[dict] = []
    activated = False
    if request.auto_test:
        for index, entry in new_entries:
            result = await _test_one(entry["key"], index)
            result["id"] = fingerprint(entry["key"])
            results.append(result)
            if result["ok"] and request.auto_activate and not activated:
                set_active_key(result["id"])
                activated = True
    payload = _key_payload()
    payload.update({
        "results": results,
        "activated": activated,
        "message": (f"تمت إضافة {len(incoming)} مفتاح واختبارها. " + (f"تم تشغيل {payload['active_label']} فعليًا." if activated else "لم يتم تشغيل أي مفتاح لأن اختبار الصوت لم ينجح.")) if request.auto_test else f"تمت إضافة {len(incoming)} مفتاح. اختبر المفتاح قبل استخدامه.",
    })
    return payload


@router.post("/keys/{key_id}/toggle")
async def toggle_key(key_id: str, request: KeyToggleRequest):
    try:
        item = set_key_enabled(key_id, request.enabled)
    except KeyError:
        raise HTTPException(status_code=404, detail="المفتاح غير موجود.")
    payload = _key_payload()
    payload["key"] = item
    payload["message"] = "تم تشغيل المفتاح، لكنه لن يصبح المستخدم فعليًا حتى ينجح الاختبار الصوتي." if request.enabled else "تم إيقاف المفتاح ولن تستخدمه أي أداة داخل الاستوديو."
    return payload


@router.post("/keys/{key_id}/activate")
async def activate_key(key_id: str):
    match = next((item for item in enumerate(load_entries(), start=1) if fingerprint(item[1]["key"]) == key_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="المفتاح غير موجود.")
    index, entry = match
    result = await _test_one(entry["key"], index)
    activated = False
    if result["ok"]:
        set_active_key(key_id)
        activated = True
    payload = _key_payload()
    payload.update({"result": result, "activated": activated, "message": "نجح الاختبار الصوتي وتم ربط المفتاح بكل أدوات الاستوديو واستخدامه الآن." if activated else f"لم يتم تشغيل المفتاح لأن الاختبار الحقيقي فشل: {result['status']} — {result['detail']}"})
    return payload


@router.post("/keys/{key_id}/test")
async def test_single_key(key_id: str):
    match = next((item for item in enumerate(load_entries(), start=1) if fingerprint(item[1]["key"]) == key_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="المفتاح غير موجود.")
    index, entry = match
    result = await _test_one(entry["key"], index)
    payload = _key_payload()
    payload.update({"result": result, "message": "نجح اختبار النص والصوت. اضغط «اختبار وتشغيل» لاستخدام المفتاح." if result["ok"] else f"نتيجة الاختبار: {result['status']} — {result['detail']}"})
    return payload


@router.delete("/keys/{key_id}")
async def remove_key(key_id: str):
    try:
        delete_key(key_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="المفتاح غير موجود.")
    payload = _key_payload()
    payload["message"] = "تم حذف المفتاح من الجهاز ومن قائمة الاستوديو."
    return payload


@router.post("/test")
async def test_keys():
    entries = load_entries()
    if not entries:
        raise HTTPException(status_code=400, detail="احفظ مفتاح Gemini واحدًا على الأقل.")
    results: list[dict] = []
    first_working_id = ""
    for index, entry in enumerate(entries, start=1):
        result = await _test_one(entry["key"], index)
        result["id"] = fingerprint(entry["key"])
        result["enabled"] = bool(entry.get("enabled", True))
        results.append(result)
        if result["ok"] and entry.get("enabled", True) and not first_working_id:
            first_working_id = result["id"]
    if first_working_id and not any(item.get("active") for item in key_statuses()):
        set_active_key(first_working_id)
    payload = _key_payload()
    payload.update({"results": results, "message": f"تم اختبار {len(entries)} مفتاح فعليًا. يعمل {payload['working']} منها." + (f" المفتاح المستخدم الآن: {payload['active_label']}." if payload["active_label"] else " لا يوجد مفتاح نشط.")})
    return payload


@router.post("/import-url")
async def import_url(request: UrlImportRequest):
    parsed = urlparse(str(request.url))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail="استخدم رابط HTTP أو HTTPS صحيحًا.")
    _safe_public_host(parsed.hostname)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=10.0), follow_redirects=True, headers={"User-Agent": "IbnAlWaqadiStudio/3.6"}) as client:
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
