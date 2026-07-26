"""Studio 2.7: AI rewriting, sermon generation, desktop exports, music mixing and consent-based cloning."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.core.config import CONFIG_DIR, OUTPUTS_DIR, UPLOADS_DIR
from backend.core.tts_registry import tts_registry
from backend.plugins.builtin.audio_effects import _ffmpeg_executable

router = APIRouter(prefix="/api/studio-pro", tags=["Studio Pro"])


def _keys() -> list[str]:
    cfg = CONFIG_DIR / "gemini.json"
    values: list[str] = []
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            values.extend(data.get("api_keys") or [])
            if data.get("api_key"):
                values.append(data["api_key"])
        except Exception:
            pass
    values.extend(re.split(r"[\n,;|]+", os.getenv("GEMINI_API_KEYS", "") or os.getenv("GEMINI_API_KEY", "")))
    return list(dict.fromkeys(str(k).strip() for k in values if len(str(k).strip()) >= 20))


async def _available_text_models(client: httpx.AsyncClient, key: str) -> list[str]:
    preferred = [
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-flash-latest",
    ]
    try:
        response = await client.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": key},
        )
        if response.status_code >= 400:
            return preferred
        available: list[str] = []
        for item in response.json().get("models", []):
            methods = item.get("supportedGenerationMethods") or []
            name = str(item.get("name", "")).replace("models/", "")
            low = name.lower()
            if "generateContent" not in methods:
                continue
            if any(x in low for x in ("tts", "image", "embedding", "aqa", "vision")):
                continue
            if name:
                available.append(name)
        ordered = [m for m in preferred if m in available]
        ordered.extend(m for m in available if m not in ordered)
        return ordered or preferred
    except Exception:
        return preferred


async def _ask_gemini(prompt: str, temperature: float = 0.45) -> str:
    keys = _keys()
    if not keys:
        raise HTTPException(status_code=400, detail="أضف مفتاح Gemini صالحًا أولًا.")
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
                        if response.status_code in {401, 403, 429}:
                            errors.append(f"المفتاح {key_index}: HTTP {response.status_code}")
                            break
                        if response.status_code in {400, 404}:
                            errors.append(f"{model}: HTTP {response.status_code}")
                            continue
                        response.raise_for_status()
                        parts = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
                        result = "\n".join(str(p.get("text", "")) for p in parts).strip()
                        if result:
                            return result
                    except Exception as exc:
                        errors.append(f"{model}: {str(exc)[:160]}")
                        continue
        except Exception as exc:
            errors.append(f"المفتاح {key_index}: {str(exc)[:160]}")
    raise HTTPException(status_code=502, detail="تعذر استخدام محرر Gemini بالنماذج المتاحة. " + "; ".join(errors[-4:]))


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


@router.post("/export/{filename}")
async def export_to_desktop(filename: str):
    safe = Path(filename).name
    source = OUTPUTS_DIR / safe
    if not source.exists() or not source.is_file():
        raise HTTPException(status_code=404, detail="لم يتم العثور على الملف الصوتي.")
    target_dir = _desktop_exports()
    target = target_dir / safe
    if target.exists():
        target = target_dir / f"{target.stem}_{uuid.uuid4().hex[:6]}{target.suffix}"
    shutil.copy2(source, target)
    return {"success": True, "path": str(target), "folder": str(target_dir), "message": "تم حفظ نسخة في مجلد Voice AI Studio Exports على سطح المكتب."}


@router.get("/export-folder")
async def export_folder():
    return {"success": True, "path": str(_desktop_exports())}


@router.post("/mix-music")
async def mix_music(voice: UploadFile = File(...), music: UploadFile = File(...), music_volume: float = Form(0.12), fade_seconds: float = Form(2.5)):
    if not (0 <= music_volume <= 0.5):
        raise HTTPException(status_code=400, detail="مستوى الموسيقى يجب أن يكون بين 0 و0.5")
    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        raise HTTPException(status_code=500, detail="FFmpeg غير متاح داخل البرنامج.")
    token = uuid.uuid4().hex[:12]
    voice_path = UPLOADS_DIR / f"voice_{token}{Path(voice.filename or '.wav').suffix or '.wav'}"
    music_path = UPLOADS_DIR / f"music_{token}{Path(music.filename or '.mp3').suffix or '.mp3'}"
    voice_path.write_bytes(await voice.read())
    music_path.write_bytes(await music.read())
    output = OUTPUTS_DIR / f"studio_mix_{token}.mp3"
    filters = (
        f"[1:a]volume={music_volume},afade=t=in:st=0:d={fade_seconds},aloop=loop=-1:size=2147483647[bg];"
        "[0:a]highpass=f=65,acompressor=threshold=-22dB:ratio=2.7:attack=10:release=140,loudnorm=I=-16:TP=-1.2:LRA=7[vc];"
        "[vc][bg]sidechaincompress=threshold=0.035:ratio=8:attack=15:release=500[ducked];"
        "[ducked]loudnorm=I=-15:TP=-1.0:LRA=7[out]"
    )
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(voice_path), "-stream_loop", "-1", "-i", str(music_path), "-filter_complex", filters, "-map", "[out]", "-shortest", "-c:a", "libmp3lame", "-b:a", "192k", str(output)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    if proc.returncode != 0 or not output.exists():
        raise HTTPException(status_code=500, detail=(proc.stderr or "فشل دمج الموسيقى")[-1000:])
    target = _desktop_exports() / output.name
    shutil.copy2(output, target)
    return {"success": True, "url": f"/api/downloads/{output.name}", "desktop_path": str(target), "message": "تم دمج الموسيقى بخفض تلقائي تحت الكلام وحفظ الملف على سطح المكتب."}


@router.post("/clone")
async def clone_voice(sample: UploadFile = File(...), text: str = Form(...), consent: bool = Form(False), engine: str = Form("coqui")):
    if not consent:
        raise HTTPException(status_code=400, detail="يجب تأكيد أن الصوت لك أو لديك إذن صريح من صاحبه.")
    if len(text.strip()) < 2:
        raise HTTPException(status_code=400, detail="أدخل نصًا للاستنساخ.")
    suffix = Path(sample.filename or "sample.wav").suffix.lower()
    if suffix not in {".wav", ".mp3", ".m4a", ".flac", ".ogg"}:
        raise HTTPException(status_code=400, detail="صيغة عينة الصوت غير مدعومة.")
    sample_path = UPLOADS_DIR / f"clone_{uuid.uuid4().hex[:12]}{suffix}"
    sample_path.write_bytes(await sample.read())
    plugin = tts_registry.get_plugin(engine)
    if not plugin or not hasattr(plugin, "clone"):
        raise HTTPException(status_code=503, detail="محرك الاستنساخ المحلي غير مثبت. ثبّت XTTS/Coqui أولًا من إدارة المحركات.")
    try:
        result = await plugin.clone(reference_audio_path=str(sample_path), text=text.strip())
    except TypeError:
        result = await plugin.clone(str(sample_path), text.strip())
    if not result or not result.get("success"):
        raise HTTPException(status_code=500, detail=(result or {}).get("message", "فشل استنساخ الصوت."))
    return result
