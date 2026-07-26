"""Intelligent Arabic studio preparation: structure text, infer dialect, and recommend delivery."""
from __future__ import annotations

import json
import os
import re
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/studio", tags=["Studio"])


class PrepareRequest(BaseModel):
    text: str = Field(min_length=2, max_length=30000)
    content_type: Literal["auto", "video", "podcast", "lecture", "sermon", "dua", "documentary", "ad"] = "auto"
    dialect: Literal["auto", "msa", "yemeni", "gulf"] = "auto"
    duration_minutes: int = Field(default=0, ge=0, le=180)
    instructions: str = Field(default="", max_length=2000)


PRESETS = {
    "video": ("broadcast_power", "studio"),
    "podcast": ("podcast_natural", "podcast"),
    "lecture": ("lecture_clear", "human_master"),
    "sermon": ("sermon_calm", "cinematic_sermon"),
    "dua": ("dua_emotional", "dua_emotional"),
    "documentary": ("documentary", "warm_broadcast"),
    "ad": ("energetic", "studio"),
}


def _keys() -> list[str]:
    raw = os.getenv("GEMINI_API_KEYS", "") or os.getenv("GEMINI_API_KEY", "")
    items = re.split(r"[\n,;|]+", raw)
    return list(dict.fromkeys(k.strip() for k in items if len(k.strip()) >= 20))


def _infer_type(text: str) -> str:
    sample = text[:3000]
    if any(x in sample for x in ("اللهم", "يا رب", "دعاء")):
        return "dua"
    if any(x in sample for x in ("أيها الإخوة", "عباد الله", "الموعظة", "اتقوا الله")):
        return "sermon"
    if any(x in sample for x in ("في هذه الحلقة", "بودكاست", "ضيفنا")):
        return "podcast"
    if any(x in sample for x in ("في هذه المحاضرة", "الدرس", "المحاضرة")):
        return "lecture"
    if any(x in sample for x in ("اشترك", "تابعونا", "في هذا الفيديو")):
        return "video"
    return "documentary"


def _infer_dialect(text: str, instructions: str) -> str:
    sample = f"{instructions} {text[:1500]}".lower()
    if any(x in sample for x in ("يمني", "اليمنية", "صنعاني", "عدني", "حضرم")):
        return "yemeni"
    if any(x in sample for x in ("خليجي", "سعودي", "إماراتي", "كويتي", "قطري")):
        return "gulf"
    return "msa"


def _clean_local(text: str, content_type: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    fixed = []
    for paragraph in paragraphs:
        paragraph = re.sub(r"\s*([،؛:؟!.])\s*", r"\1 ", paragraph).strip()
        if paragraph and paragraph[-1] not in ".؟!":
            paragraph += "."
        fixed.append(paragraph)
    return "\n\n".join(fixed)


async def _gemini_prepare(req: PrepareRequest, selected_type: str, selected_dialect: str) -> str | None:
    keys = _keys()
    if not keys:
        return None
    dialect_note = {
        "msa": "عربية فصحى طبيعية وسهلة",
        "yemeni": "روح يمنية طبيعية مفهومة، دون كلمات محلية غامضة أو مبالغة",
        "gulf": "أسلوب خليجي طبيعي مفهوم، مع الحفاظ على وضوح العربية",
    }[selected_dialect]
    prompt = f"""أنت محرر نصوص ومخرج صوت عربي محترف. رتّب النص التالي ليصبح جاهزًا للتسجيل الصوتي.
نوع المحتوى: {selected_type}
اللهجة: {dialect_note}
المدة المطلوبة بالدقائق: {req.duration_minutes or 'غير محددة'}
تعليمات المستخدم: {req.instructions or 'لا توجد'}

القواعد:
- حافظ على المعنى ولا تضف ادعاءات أو معلومات جديدة.
- صحح علامات الترقيم والأخطاء الواضحة.
- قسّم النص إلى فقرات قصيرة، واجعل الوقفات طبيعية.
- لا تكتب عناوين تقنية أو ملاحظات للمؤدي داخل الناتج.
- في النصوص الدينية لا تغيّر الآيات أو الأحاديث، واترك ما يحتاج مراجعة كما هو.
- أعد النص النهائي فقط دون شرح.

النص:
{req.text}"""
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.35}}
    for key in keys:
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(
                    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
                    headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                    json=payload,
                )
            if response.status_code in {401, 403, 429}:
                continue
            response.raise_for_status()
            parts = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
            result = "\n".join(str(p.get("text", "")) for p in parts).strip()
            if result:
                return result
        except Exception:
            continue
    return None


@router.post("/prepare")
async def prepare_text(req: PrepareRequest):
    selected_type = _infer_type(req.text) if req.content_type == "auto" else req.content_type
    selected_dialect = _infer_dialect(req.text, req.instructions) if req.dialect == "auto" else req.dialect
    profile, effect = PRESETS.get(selected_type, ("human_ultra", "human_master"))
    prepared = await _gemini_prepare(req, selected_type, selected_dialect)
    used_ai = bool(prepared)
    if not prepared:
        prepared = _clean_local(req.text, selected_type)
    voice = "Kore"
    if selected_dialect == "yemeni":
        voice = "Gacrux"
        profile = "yemeni_natural" if selected_type not in {"dua", "sermon"} else profile
    elif selected_dialect == "gulf":
        voice = "Sulafat"
        profile = "gulf_natural" if selected_type not in {"dua", "sermon"} else profile
    return {
        "success": True,
        "text": prepared,
        "content_type": selected_type,
        "dialect": selected_dialect,
        "profile": profile,
        "effect": effect,
        "voice": voice,
        "used_ai": used_ai,
        "message": "تم فهم النص وترتيبه وإعداد الاستوديو تلقائيًا." if used_ai else "تم ترتيب النص محليًا؛ تعذر استخدام محرر Gemini حاليًا.",
    }
