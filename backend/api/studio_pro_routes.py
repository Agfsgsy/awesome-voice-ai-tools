"""Studio Pro: AI rewriting, sermons, exports, music mixing and consent-based cloning."""
from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.api.voice_clone_routes import (
    GenerateCloneRequest,
    create_profile_from_uploads,
    generate_from_profile,
)
from backend.core.config import OUTPUTS_DIR, UPLOADS_DIR
from backend.core.gemini_key_pool import ordered_keys, record_result
from backend.core.logger import get_logger
from backend.plugins.builtin.audio_effects import _ffmpeg_executable

router = APIRouter(prefix="/api/studio-pro", tags=["Studio Pro"])
logger = get_logger("studio_exports")


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
            if any(x in low for x in ("tts", "image", "embedding", "aqa")):
                continue
            if name:
                available.append(name)
        ordered = [model for model in preferred if model in available]
        ordered.extend(model for model in available if model not in ordered)
        return ordered or preferred
    except Exception:
        return preferred


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            return str((payload.get("error") or {}).get("message") or response.text[:500])
    except Exception:
        pass
    return response.text[:500]


async def _ask_gemini(prompt: str, temperature: float = 0.45) -> str:
    """Use the exact same enabled and active key pool as TTS and interviews."""
    keys = ordered_keys()
    if not keys:
        raise HTTPException(status_code=400, detail="لا يوجد مفتاح Gemini مفعّل وجاهز. افتح إدارة المفاتيح، اختبر مفتاحًا ثم شغّله.")
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": temperature}}
    errors: list[str] = []
    for key_index, key in enumerate(keys, start=1):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=25.0)) as client:
                models = await _available_text_models(client, key)
                for model in models:
                    try:
                        response = await client.post(
                            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                            json=payload,
                        )
                        if response.status_code == 429:
                            detail = _error_detail(response); record_result(key, "quota", detail); errors.append(f"المفتاح {key_index}: انتهت الحصة"); break
                        if response.status_code == 401:
                            detail = _error_detail(response); record_result(key, "invalid", detail); errors.append(f"المفتاح {key_index}: غير صحيح"); break
                        if response.status_code == 403:
                            detail = _error_detail(response); record_result(key, "forbidden", detail); errors.append(f"المفتاح {key_index}: مرفوض"); break
                        if response.status_code in {400, 404}:
                            errors.append(f"{model}: غير متاح"); continue
                        response.raise_for_status()
                        parts = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
                        result = "\n".join(str(part.get("text", "")) for part in parts).strip()
                        if result:
                            record_result(key, "working", f"Text model: {model}")
                            return result
                    except Exception as exc:
                        errors.append(f"{model}: {str(exc)[:160]}")
        except Exception as exc:
            errors.append(f"المفتاح {key_index}: {str(exc)[:160]}")
    raise HTTPException(status_code=502, detail="تعذر استخدام محرر Gemini بالمفاتيح المفعّلة. " + "; ".join(errors[-5:]))


class RewriteRequest(BaseModel):
    text: str = Field(min_length=2, max_length=30000)
    goal: str = Field(default="فيديو مؤثر", max_length=300)
    dialect: str = Field(default="auto", max_length=30)
    intensity: str = Field(default="balanced", max_length=30)
    add_hook: bool = True
    add_ending: bool = True


class SermonRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=500)
    duration_minutes: int = Field(default=4, ge=1, le=30)
    dialect: str = Field(default="msa", max_length=30)
    tone: str = Field(default="heart_touching", max_length=40)


@router.post("/rewrite")
async def rewrite(req: RewriteRequest):
    dialect = {"yemeni": "يمني طبيعي مفهوم", "gulf": "خليجي طبيعي راقٍ", "msa": "فصحى سهلة", "auto": "اختر الأنسب من النص"}.get(req.dialect, "فصحى سهلة")
    prompt = f"""أنت كاتب ومخرج صوت عربي محترف للفيديو والبودكاست والمحاضرات.
أعد صياغة النص ليكون شديد الوضوح والتأثير وسهل الاستماع، مع الحفاظ على المعنى وعدم اختلاق معلومات.
الهدف: {req.goal}
اللهجة: {dialect}
درجة التأثير: {req.intensity}
أضف افتتاحية جاذبة: {'نعم' if req.add_hook else 'لا'}
أضف خاتمة قوية ودعوة مناسبة: {'نعم' if req.add_ending else 'لا'}
قسّم النص إلى فقرات قصيرة، واضبط علامات الوقف والتنفس. لا تضع تعليمات تقنية بين أقواس، وأعد النص النهائي فقط.
في الآيات والأحاديث لا تغيّر النص، ولا تنسب حديثًا دون تحقق.

النص:
{req.text}"""
    result = await _ask_gemini(prompt)
    return {"success": True, "text": result, "message": "تم تعديل النص وتقويته وتجهيزه للإلقاء."}


@router.post("/sermon")
async def generate_sermon(req: SermonRequest):
    dialect = {"yemeni": "يمني طبيعي مفهوم", "gulf": "خليجي طبيعي", "msa": "فصحى مؤثرة"}.get(req.dialect, "فصحى مؤثرة")
    words = max(140, req.duration_minutes * 125)
    prompt = f"""اكتب موعظة عربية أصلية تلامس القلب حول الموضوع: {req.topic}
الطول التقريبي: {words} كلمة. الأسلوب: {dialect}. النبرة: مؤثرة وصادقة وهادئة ثم خاتمة قوية.
ابدأ بمقدمة جاذبة، ثم فكرة واضحة، ثم تطبيق عملي، ثم خاتمة ودعاء قصير مناسب.
لا تخترع آيات أو أحاديث، ولا تنسب قولًا دينيًا دون يقين. عند عدم اليقين استخدم معنى عامًا صحيحًا.
اكتب نص الموعظة النهائي فقط، بفقرات قصيرة وعلامات وقف مناسبة للصوت."""
    result = await _ask_gemini(prompt, 0.65)
    return {"success": True, "text": result, "message": "تم إنشاء موعظة مؤثرة جاهزة للمراجعة والتسجيل."}


def _desktop_exports() -> Path:
    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        desktop = Path.home()
    target = desktop / "Voice AI Studio Exports"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _copy_to_desktop(source: Path) -> Path | None:
    """Best-effort export that never discards a completed audio result."""
    try:
        target_dir = _desktop_exports()
    except OSError as exc:
        logger.warning("Desktop export folder is unavailable: %s", exc)
        return None

    for attempt in range(8):
        target = target_dir / source.name
        if attempt or target.exists():
            target = target_dir / f"{source.stem}_{uuid.uuid4().hex[:8]}{source.suffix}"
        try:
            shutil.copy2(source, target)
            return target
        except OSError as exc:
            logger.warning("Desktop export attempt %s failed for %s: %s", attempt + 1, source.name, exc)
    return None


def _desktop_note(target: Path | None) -> str:
    if target:
        return " وحُفظت نسخة على سطح المكتب."
    return " والنتيجة محفوظة داخل التطبيق؛ تعذر نسخها إلى سطح المكتب لأن Windows منع الكتابة أو لأن الملف مفتوح."


@router.post("/export/{filename}")
async def export_to_desktop(filename: str):
    safe = Path(filename).name
    source = OUTPUTS_DIR / safe
    if not source.exists() or not source.is_file():
        raise HTTPException(status_code=404, detail="لم يتم العثور على الملف الصوتي.")
    target = _copy_to_desktop(source)
    if target:
        return {
            "success": True,
            "exported": True,
            "path": str(target),
            "folder": str(target.parent),
            "message": "تم حفظ نسخة في مجلد Voice AI Studio Exports على سطح المكتب.",
        }
    return {
        "success": True,
        "exported": False,
        "path": str(source),
        "folder": str(OUTPUTS_DIR),
        "message": "الملف محفوظ داخل التطبيق. أغلق أي نسخة مفتوحة منه أو اسمح بالكتابة على سطح المكتب ثم أعد التصدير.",
    }


@router.get("/export-folder")
async def export_folder():
    try:
        path = _desktop_exports()
    except OSError:
        path = OUTPUTS_DIR
    return {"success": True, "path": str(path)}


class MixRequest(BaseModel):
    voice_filename: str = Field(min_length=1, max_length=300)
    music_filename: str = Field(min_length=1, max_length=300)
    music_volume: float = Field(default=0.12, ge=0.01, le=0.8)


@router.post("/mix")
async def mix_audio(req: MixRequest):
    voice = OUTPUTS_DIR / Path(req.voice_filename).name
    music = OUTPUTS_DIR / Path(req.music_filename).name
    if not voice.exists() or not music.exists():
        raise HTTPException(status_code=404, detail="ملف الصوت أو الموسيقى غير موجود.")
    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        raise HTTPException(status_code=500, detail="FFmpeg غير متاح.")
    output = OUTPUTS_DIR / f"mix_{uuid.uuid4().hex[:10]}.mp3"
    filter_graph = f"[1:a]volume={req.music_volume},aloop=loop=-1:size=2e+09[bg];[bg][0:a]sidechaincompress=threshold=0.04:ratio=8:attack=20:release=500[duck];[0:a][duck]amix=inputs=2:duration=first:weights='1 1',loudnorm=I=-16:TP=-1.5:LRA=11[out]"
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(voice), "-i", str(music), "-filter_complex", filter_graph, "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "192k", str(output)]
    process = subprocess.run(command, capture_output=True, text=True, timeout=900, check=False)
    if process.returncode != 0 or not output.exists():
        raise HTTPException(status_code=500, detail=(process.stderr or "فشل دمج الصوت والموسيقى")[-1200:])
    target = _copy_to_desktop(output)
    return {
        "success": True,
        "url": f"/api/downloads/{output.name}",
        "desktop_path": str(target) if target else None,
        "desktop_exported": bool(target),
        "message": "تم دمج الموسيقى وخفضها تلقائيًا تحت الكلام." + _desktop_note(target),
    }


@router.post("/clone")
async def clone_voice(
    sample: UploadFile = File(...),
    text: str = Form(...),
    consent: bool = Form(...),
    engine: str = Form("coqui"),
):
    """Compatibility endpoint for the old studio clone box.

    The previous implementation called Coqui.generate() without passing the sample
    as speaker_wav. This route now creates a real consent profile and delegates to
    Voice Clone Pro. Existing UI requests continue to work unchanged.
    """
    provider = "elevenlabs" if engine.lower() in {"elevenlabs", "human_pro"} else "local"
    manifest = await create_profile_from_uploads(
        [sample],
        name="استنساخ سريع",
        owner_name="صاحب العينة",
        consent=consent,
        consent_statement="تم تأكيد امتلاك الصوت أو الإذن الصريح من واجهة الاستوديو الكامل.",
    )
    request = GenerateCloneRequest(
        profile_id=str(manifest["id"]),
        text=text.strip(),
        provider=provider,
        language="ar",
        speed=1.0,
        style="natural",
    )
    result = await generate_from_profile(request)
    result["message"] = "تم إصلاح الاستنساخ القديم وإنشاء الصوت بعينة speaker_wav حقيقية. " + str(result.get("message", ""))
    return result
