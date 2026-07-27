"""Ultimate bilingual studio: strict voices, provider connections and creative writing."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api.producer_routes import _normalize_and_concat
from backend.api.studio_pro_routes import _copy_to_desktop, _desktop_note
from backend.core.config import OUTPUTS_DIR
from backend.core.gemini_key_pool import append_keys, apply_environment, load_keys
from backend.core.provider_settings import (
    masked_provider_config,
    provider_config,
    save_provider_config,
)
from backend.core.tts_registry import tts_registry
from backend.core.voice_catalog import (
    TONE_PROFILES,
    choose_voice,
    voice_by_id,
    voices_for,
)
from backend.plugins.builtin.audio_effects import process_audio

router = APIRouter(prefix="/api/ultimate", tags=["Ultimate Voice Studio"])

PROVIDERS: dict[str, dict[str, Any]] = {
    "edge": {
        "name_ar": "Edge Neural",
        "name_en": "Edge Neural",
        "category": "free",
        "cost_ar": "مجاني بلا مفتاح — يحتاج الإنترنت",
        "cost_en": "Free, no key — internet required",
        "docs": "https://github.com/rany2/edge-tts",
        "languages": ["ar", "en"],
        "strict_gender": True,
        "config_fields": [],
    },
    "piper": {
        "name_ar": "Piper المحلي",
        "name_en": "Local Piper",
        "category": "open_source",
        "cost_ar": "مجاني ومحلي بعد تنزيل النموذج",
        "cost_en": "Free and local after model download",
        "docs": "https://github.com/OHF-Voice/piper1-gpl",
        "languages": ["ar"],
        "strict_gender": True,
        "config_fields": [],
    },
    "gemini": {
        "name_ar": "Gemini TTS",
        "name_en": "Gemini TTS",
        "category": "trial",
        "cost_ar": "حصة تجريبية/مجانية بحسب حساب Google",
        "cost_en": "Trial/free quota depends on the Google account",
        "docs": "https://ai.google.dev/gemini-api/docs/speech-generation",
        "languages": ["ar", "en"],
        "strict_gender": True,
        "config_fields": ["api_key"],
    },
    "elevenlabs": {
        "name_ar": "ElevenLabs",
        "name_en": "ElevenLabs",
        "category": "trial",
        "cost_ar": "خطة مجانية محدودة؛ الاستخدام التجاري يتطلب خطة مناسبة",
        "cost_en": "Limited free plan; commercial use requires an appropriate plan",
        "docs": "https://elevenlabs.io/docs/overview/capabilities/text-to-speech",
        "languages": ["ar", "en"],
        "strict_gender": True,
        "config_fields": [
            "api_key",
            "model_id",
            "male_voice_id_ar",
            "female_voice_id_ar",
            "male_voice_id_en",
            "female_voice_id_en",
        ],
    },
    "azure": {
        "name_ar": "Azure AI Speech",
        "name_en": "Azure AI Speech",
        "category": "trial",
        "cost_ar": "طبقة F0 مجانية حيث تتوفر، ثم مدفوع",
        "cost_en": "Free F0 tier where available, then paid",
        "docs": "https://learn.microsoft.com/azure/ai-services/speech-service/text-to-speech",
        "languages": ["ar", "en"],
        "strict_gender": True,
        "config_fields": ["api_key", "region"],
    },
    "google_cloud": {
        "name_ar": "Google Cloud TTS",
        "name_en": "Google Cloud TTS",
        "category": "trial",
        "cost_ar": "استخدام مجاني شهري وائتمان تجريبي؛ قد يلزم تفعيل الفوترة",
        "cost_en": "Monthly free usage and trial credits; billing activation may be required",
        "docs": "https://cloud.google.com/text-to-speech",
        "languages": ["ar", "en"],
        "strict_gender": True,
        "config_fields": ["api_key", "project_id"],
    },
    "openai": {
        "name_ar": "OpenAI TTS",
        "name_en": "OpenAI TTS",
        "category": "paid",
        "cost_ar": "API مدفوع؛ لا توجد طبقة API مجانية مضمونة",
        "cost_en": "Paid API; no guaranteed free API tier",
        "docs": "https://developers.openai.com/api/docs/models/gpt-4o-mini-tts",
        "languages": ["ar", "en"],
        "strict_gender": False,
        "config_fields": ["api_key", "model_id"],
    },
    "kokoro": {
        "name_ar": "Kokoro — إضافة محلية",
        "name_en": "Kokoro — local add-on",
        "category": "open_source",
        "cost_ar": "مجاني؛ الإنجليزية هي الاستخدام الأقوى",
        "cost_en": "Free; strongest for English",
        "docs": "https://github.com/hexgrad/kokoro",
        "languages": ["en"],
        "strict_gender": True,
        "config_fields": [],
    },
    "coqui": {
        "name_ar": "Coqui XTTS — إضافة محلية",
        "name_en": "Coqui XTTS — local add-on",
        "category": "open_source",
        "cost_ar": "محلي اختياري؛ راجع ترخيص نموذج XTTS قبل الاستخدام التجاري",
        "cost_en": "Optional local engine; review the XTTS model license for commercial use",
        "docs": "https://github.com/coqui-ai/TTS",
        "languages": ["ar", "en"],
        "strict_gender": False,
        "config_fields": [],
    },
    "openvoice": {
        "name_ar": "OpenVoice V2 — حزمة استنساخ اختيارية",
        "name_en": "OpenVoice V2 — optional cloning pack",
        "category": "open_source",
        "cost_ar": "MIT ومجاني؛ الاستنساخ يتطلب موافقة صاحب الصوت",
        "cost_en": "MIT and free; cloning requires the speaker's consent",
        "docs": "https://github.com/myshell-ai/OpenVoice",
        "languages": ["en"],
        "strict_gender": False,
        "config_fields": [],
        "catalog_only": True,
    },
}


class ProviderConfigRequest(BaseModel):
    api_key: str | None = Field(default=None, max_length=12000)
    region: str | None = Field(default=None, max_length=80)
    project_id: str | None = Field(default=None, max_length=180)
    model_id: str | None = Field(default=None, max_length=180)
    male_voice_id_ar: str | None = Field(default=None, max_length=180)
    female_voice_id_ar: str | None = Field(default=None, max_length=180)
    male_voice_id_en: str | None = Field(default=None, max_length=180)
    female_voice_id_en: str | None = Field(default=None, max_length=180)
    clear_secret: bool = False


class SynthesisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    provider: str = Field(default="edge", max_length=40)
    language: Literal["auto", "ar", "en"] = "auto"
    gender: Literal["male", "female", "neutral"] = "male"
    locale: str | None = Field(default=None, max_length=20)
    voice_id: str = Field(default="auto", max_length=180)
    tone: str = Field(default="natural", max_length=40)
    speed: float = Field(default=1.0, ge=0.7, le=1.25)
    effect: str = Field(default="none", max_length=60)


class CreativeRequest(BaseModel):
    mode: Literal["generate", "rewrite", "interview"] = "generate"
    subject: str = Field(default="", max_length=1000)
    source_text: str = Field(default="", max_length=30000)
    language: Literal["ar", "en"] = "ar"
    dialect: str = Field(default="msa", max_length=40)
    content_type: str = Field(default="podcast", max_length=50)
    tone: str = Field(default="engaging", max_length=50)
    audience: str = Field(default="general", max_length=300)
    duration_minutes: int = Field(default=4, ge=1, le=45)
    speakers: int = Field(default=3, ge=2, le=6)
    writer_provider: Literal["auto", "local", "gemini", "openai"] = "auto"


class DialogueRequest(BaseModel):
    script: str = Field(min_length=2, max_length=50000)
    provider: str = Field(default="edge", max_length=40)
    language: Literal["ar", "en"] = "ar"
    tone: str = Field(default="podcast", max_length=40)
    speed: float = Field(default=0.98, ge=0.7, le=1.25)
    pause_ms: int = Field(default=360, ge=100, le=1400)
    effect: str = Field(default="podcast", max_length=60)
    role_voices: dict[str, str] = Field(default_factory=dict)


def _plugin_ready(provider: str) -> bool:
    plugin = tts_registry.get_plugin(provider)
    try:
        return bool(plugin and plugin.check())
    except Exception:
        return False


def _provider_payload(provider: str, metadata: dict[str, Any]) -> dict[str, Any]:
    state = masked_provider_config(provider)
    configured = _plugin_ready(provider)
    if provider == "gemini":
        configured = bool(load_keys(enabled_only=True))
        state = {"api_key_set": configured, "key_count": len(load_keys(enabled_only=True))}
    return {
        "id": provider,
        **metadata,
        "configured": configured,
        "available": bool(tts_registry.get_plugin(provider)) and not metadata.get("catalog_only"),
        "settings": state,
        "voice_count": len(voices_for(provider)),
    }


@router.get("/providers")
async def providers():
    return {
        "success": True,
        "providers": [_provider_payload(name, metadata) for name, metadata in PROVIDERS.items()],
        "tones": [{"id": name, "name_ar": data["ar"], "name_en": data["en"]} for name, data in TONE_PROFILES.items()],
    }


@router.post("/providers/{provider}/configure")
async def configure_provider(provider: str, request: ProviderConfigRequest):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="مزود الصوت غير معروف.")
    if provider in {"edge", "piper", "kokoro", "coqui", "openvoice"}:
        raise HTTPException(status_code=400, detail="هذا المحرك لا يحتاج مفتاح API.")
    values = request.model_dump(exclude_none=True)
    clear_secret = bool(values.pop("clear_secret", False))
    if provider == "gemini":
        raw_keys = values.get("api_key", "")
        if not raw_keys and not clear_secret:
            raise HTTPException(status_code=400, detail="ضع مفتاح Gemini واحدًا على الأقل.")
        if clear_secret:
            append_keys([], "gemini-3.1-flash-tts-preview", "Kore", replace=True)
        else:
            keys = append_keys(
                raw_keys,
                values.get("model_id") or "gemini-3.1-flash-tts-preview",
                "Kore",
                replace=False,
            )
            apply_environment(keys)
        return {"success": True, "provider": provider, "message": "تم حفظ مفاتيح Gemini محليًا."}
    try:
        saved = save_provider_config(provider, values, clear_secret=clear_secret)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "success": True,
        "provider": provider,
        "configured": bool(saved.get("api_key")),
        "message": "تم حفظ إعدادات المزود محليًا. اضغط اختبار الاتصال للتأكد من صلاحيتها.",
    }


@router.post("/providers/{provider}/test")
async def test_provider(provider: str):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="مزود الصوت غير معروف.")
    if provider in {"edge", "piper", "kokoro", "coqui"}:
        if not _plugin_ready(provider):
            raise HTTPException(status_code=503, detail="المحرك غير جاهز أو لم يكتمل تثبيته.")
        return {"success": True, "provider": provider, "message": "المحرك جاهز."}
    if provider == "openvoice":
        raise HTTPException(status_code=501, detail="OpenVoice حزمة اختيارية وليست مثبتة في النسخة الخفيفة.")
    if provider == "gemini":
        if not load_keys(enabled_only=True):
            raise HTTPException(status_code=400, detail="لا يوجد مفتاح Gemini محفوظ.")
        return {
            "success": True,
            "provider": provider,
            "message": "المفتاح محفوظ. استخدم مركز Gemini لإجراء اختبار النص والصوت الكامل.",
        }

    config = provider_config(provider)
    api_key = config.get("api_key", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="أضف مفتاح API أولًا.")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(35.0, connect=15.0)) as client:
            if provider == "openai":
                model = config.get("model_id") or "gpt-4o-mini-tts"
                response = await client.get(
                    f"https://api.openai.com/v1/models/{model}",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            elif provider == "azure":
                region = config.get("region", "")
                if not region:
                    raise HTTPException(status_code=400, detail="أضف منطقة Azure مثل eastus.")
                response = await client.get(
                    f"https://{region}.tts.speech.microsoft.com/cognitiveservices/voices/list",
                    headers={"Ocp-Apim-Subscription-Key": api_key},
                )
            elif provider == "google_cloud":
                response = await client.get(
                    "https://texttospeech.googleapis.com/v1/voices",
                    params={"key": api_key, "languageCode": "ar"},
                )
            elif provider == "elevenlabs":
                response = await client.get(
                    "https://api.elevenlabs.io/v1/user/subscription",
                    headers={"xi-api-key": api_key},
                )
            else:
                raise HTTPException(status_code=400, detail="لا يوجد اختبار لهذا المزود.")
        if response.status_code >= 400:
            try:
                detail = (response.json().get("error") or {}).get("message") or response.text[:600]
            except Exception:
                detail = response.text[:600]
            raise HTTPException(status_code=response.status_code, detail=detail)
        return {"success": True, "provider": provider, "message": "نجح الاتصال الحقيقي بالمزود والمفتاح صالح."}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"تعذر اختبار الاتصال: {exc}") from exc


@router.get("/voices")
async def list_voices(
    provider: str = "edge",
    language: Literal["ar", "en"] = "ar",
    gender: Literal["male", "female", "neutral"] = "male",
    locale: str | None = None,
):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="مزود الصوت غير معروف.")
    items = voices_for(provider, language=language, gender=gender, locale=locale)
    return {
        "success": True,
        "provider": provider,
        "language": language,
        "gender": gender,
        "voices": items,
        "strict": bool(PROVIDERS[provider].get("strict_gender")),
        "message": (
            "لا يوجد صوت مطابق تمامًا لهذه اللغة والجنس؛ اختر مزودًا آخر."
            if not items
            else "تمت تصفية الأصوات حسب اللغة والجنس."
        ),
    }


def _detect_language(text: str) -> tuple[str, float]:
    arabic = len(re.findall(r"[\u0600-\u06ff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    total = arabic + latin
    if not total:
        return "ar", 0.0
    language = "ar" if arabic >= latin else "en"
    return language, max(arabic, latin) / total


def _tone_for_plugin(provider: str, tone: str) -> str:
    mappings = {
        "broadcast": "broadcast_power",
        "podcast": "podcast_natural",
        "lecture": "lecture_clear",
        "emotional": "dua_emotional",
    }
    if provider in {"edge", "gemini", "elevenlabs"}:
        return mappings.get(tone, tone)
    return tone


def _validate_voice(
    provider: str,
    voice_id: str,
    *,
    language: str,
    gender: str,
    locale: str | None,
) -> dict[str, Any]:
    if voice_id in {"", "auto", "default"}:
        selected = choose_voice(provider, language=language, gender=gender, locale=locale)
    else:
        selected = voice_by_id(provider, voice_id)
    if not selected:
        raise HTTPException(
            status_code=422,
            detail="لا يوجد صوت مطابق للمحرك واللغة والجنس. لن يختار الاستوديو صوتًا مخالفًا.",
        )
    if selected["language"] != language:
        raise HTTPException(status_code=422, detail="الصوت المختار لا يطابق لغة النص.")
    if selected["gender"] != gender:
        raise HTTPException(status_code=422, detail="الصوت المختار لا يطابق جنس المتحدث.")
    if locale and selected["locale"].lower() != locale.lower():
        available = voices_for(provider, language=language, gender=gender, locale=locale)
        if available:
            raise HTTPException(status_code=422, detail="الصوت المختار لا يطابق اللهجة أو المنطقة المحددة.")
    return selected


async def _synthesize_strict(request: SynthesisRequest) -> dict[str, Any]:
    provider = "edge" if request.provider == "auto" else request.provider
    if provider not in PROVIDERS or PROVIDERS[provider].get("catalog_only"):
        raise HTTPException(status_code=400, detail="محرك الصوت غير قابل للإنتاج في هذه النسخة.")
    language_detected, confidence = _detect_language(request.text)
    language = language_detected if request.language == "auto" else request.language
    if request.language != "auto" and confidence >= 0.78 and language_detected != language:
        raise HTTPException(
            status_code=422,
            detail="لغة النص لا تطابق اللغة المختارة. غيّر لغة النص أو اختر الكشف التلقائي.",
        )
    selected = _validate_voice(
        provider,
        request.voice_id,
        language=language,
        gender=request.gender,
        locale=request.locale,
    )
    plugin = tts_registry.get_plugin(provider)
    if not plugin:
        raise HTTPException(status_code=503, detail="إضافة المحرك غير موجودة.")
    if not plugin.check():
        raise HTTPException(status_code=503, detail="المحرك غير جاهز. افتح ربط المزود أو ثبّت الحزمة المطلوبة.")
    tone = _tone_for_plugin(provider, request.tone)
    voice_value = selected["id"]
    if provider in {"edge", "gemini", "elevenlabs", "openai"}:
        voice_value += f"|{tone}"
    result = await plugin.generate(
        text=request.text,
        voice=voice_value,
        language=language,
        speed=request.speed,
    )
    if not result or not result.get("success"):
        raise HTTPException(status_code=502, detail=(result or {}).get("message", "فشل إنتاج الصوت."))
    result.update(
        {
            "success": True,
            "provider_requested": request.provider,
            "provider_used": provider,
            "language": language,
            "language_detected": language_detected,
            "gender": request.gender,
            "voice_metadata": selected,
            "fallback": False,
        }
    )
    return result


@router.post("/synthesize")
async def synthesize(request: SynthesisRequest):
    result = await _synthesize_strict(request)
    if request.effect != "none":
        source = Path(result.get("file", ""))
        final = OUTPUTS_DIR / f"ultimate_{uuid.uuid4().hex[:12]}.mp3"
        if source.exists() and process_audio(str(source), str(final), request.effect):
            result["file"] = str(final)
            result["url"] = f"/api/downloads/{final.name}"
    return result


def _writer_prompt(request: CreativeRequest) -> str:
    language_name = "العربية" if request.language == "ar" else "English"
    role_rule = (
        "في المقابلة استخدم حصريًا: المذيع_رجل، المذيعة_امرأة، الضيف_رجل، الضيفة_امرأة، الخبير_رجل."
        if request.language == "ar"
        else "For interviews use only these role labels: HOST_MALE, HOST_FEMALE, GUEST_MALE, GUEST_FEMALE, EXPERT_MALE."
    )
    return f"""You are the senior creative director and dialogue writer for a professional voice studio.
Write in {language_name}. Preserve verified facts and never invent quotations, scripture, statistics or attributions.
Mode: {request.mode}
Content type: {request.content_type}
Tone: {request.tone}
Dialect or accent: {request.dialect}
Audience: {request.audience}
Target duration: {request.duration_minutes} minutes
Speakers: {request.speakers}
{role_rule}

Requirements:
- Start with a compelling hook that fits the subject, not clickbait.
- Build a clear narrative arc: hook, context, tension or question, useful development, memorable conclusion.
- Vary sentence length and add punctuation suitable for natural speech.
- For interviews, ask insightful follow-up questions and let speakers disagree respectfully and add distinct value.
- Do not write stage directions that a speech engine would read aloud.
- Return only the final publishable script.

Subject:
{request.subject}

Source text to preserve or rewrite:
{request.source_text}"""


def _local_script(request: CreativeRequest) -> str:
    subject = (
        request.subject.strip()
        or request.source_text.strip()
        or ("موضوع جديد" if request.language == "ar" else "a new topic")
    )
    if request.language == "en":
        if request.mode == "interview":
            roles = ["HOST_MALE", "GUEST_FEMALE", "EXPERT_MALE", "HOST_FEMALE"][: request.speakers]
            lines = [
                (
                    roles[0],
                    f"Welcome. Today we are going beyond the obvious question about {subject}: "
                    "what actually changes when we apply it in real life?",
                ),
                (
                    roles[1],
                    f"The first change is how we frame {subject}. People often look for a quick "
                    "answer, while the useful answer starts with context.",
                ),
                (
                    roles[0],
                    "What is the most common assumption that prevents people from seeing " "that context clearly?",
                ),
                (
                    roles[2] if len(roles) > 2 else roles[1],
                    "They confuse confidence with certainty. A better approach is to test the "
                    "idea, measure the result, and revise the decision.",
                ),
                (roles[0], "Give us one practical step the listener can use today."),
                (
                    roles[1],
                    "Write down the desired outcome, the strongest constraint, and the smallest "
                    "responsible experiment. That turns an abstract idea into action.",
                ),
                (
                    roles[-1],
                    "The real value is not a perfect answer; it is a better question followed "
                    "by an honest experiment. Thank you for listening.",
                ),
            ]
            return "\n\n".join(f"{role}: {text}" for role, text in lines)
        return (
            f"What if the most important part of {subject} is the part we usually rush past?\n\n"
            f"This piece explores {subject} with one goal: turn an interesting idea into a clear, useful decision. "
            "We begin with the real context, separate evidence from assumption, and then move "
            "toward a practical step.\n\n"
            "The strongest message is simple: clarity grows when we ask a precise question, "
            "listen to more than one perspective, "
            "and test our conclusion before presenting it as fact.\n\n"
            "Choose one idea from this discussion and apply it today. A small, deliberate "
            "action is more valuable than a dramatic promise."
        )
    if request.mode == "interview":
        roles = ["المذيع_رجل", "الضيفة_امرأة", "الخبير_رجل", "المذيعة_امرأة"][: request.speakers]
        lines = [
            (
                roles[0],
                f"أهلًا بكم. اليوم لن نكتفي بالسؤال المعتاد عن {subject}؛ بل سنسأل: "
                "ما الذي يتغيّر فعلًا عندما نحوله إلى ممارسة يومية؟",
            ),
            (
                roles[1],
                f"البداية هي أن نفهم سياق {subject}. كثيرون يبحثون عن إجابة سريعة، "
                "بينما الإجابة المفيدة تبدأ بسؤال أدق.",
            ),
            (roles[0], "ما الفكرة الشائعة التي تمنع الناس من رؤية الصورة بوضوح؟"),
            (
                roles[2] if len(roles) > 2 else roles[1],
                "الخلط بين الثقة واليقين. المنهج الأفضل أن نختبر الفكرة، ونقيس النتيجة، ثم نراجع القرار بصدق.",
            ),
            (roles[0], "لو أردنا خطوة واحدة يستطيع المستمع تطبيقها اليوم، فماذا تكون؟"),
            (
                roles[1],
                "يكتب النتيجة التي يريدها، وأكبر عائق أمامه، وأصغر تجربة مسؤولة يمكنه "
                "تنفيذها. هنا تتحول الفكرة إلى فعل.",
            ),
            (
                roles[-1],
                "القيمة ليست في إجابة مثالية، بل في سؤال أفضل تتبعه تجربة صادقة. " "شكرًا لحسن استماعكم.",
            ),
        ]
        return "\n\n".join(f"{role}: {text}" for role, text in lines)
    return (
        f"ماذا لو كان أهم جانب في {subject} هو الجانب الذي نعبره عادةً بسرعة؟\n\n"
        f"هذا النص يقترب من {subject} بهدف واضح: أن يحوّل الفكرة الجميلة إلى فهم نافع وقرار قابل للتطبيق. "
        "نبدأ بالسياق الحقيقي، ونفصل بين الدليل والانطباع، ثم نصل إلى خطوة عملية.\n\n"
        "الخلاصة الأقوى بسيطة: يزداد الوضوح عندما نصوغ سؤالًا دقيقًا، ونستمع إلى أكثر من زاوية، "
        "ونختبر استنتاجنا قبل أن نقدمه كحقيقة نهائية.\n\n"
        "اختر فكرة واحدة وطبّقها اليوم؛ فالخطوة الصغيرة الواعية أقوى من الوعد الكبير."
    )


async def _write_with_openai(prompt: str) -> str:
    config = provider_config("openai")
    api_key = config.get("api_key", "")
    if not api_key:
        raise RuntimeError("لا يوجد مفتاح OpenAI محفوظ.")
    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=25.0)) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "Return only the final polished script."},
                    {"role": "user", "content": prompt},
                ],
            },
        )
    if response.status_code >= 400:
        raise RuntimeError(response.text[:700])
    return str(response.json()["choices"][0]["message"]["content"]).strip()


@router.post("/creative")
async def creative(request: CreativeRequest):
    if not request.subject.strip() and not request.source_text.strip():
        raise HTTPException(status_code=400, detail="اكتب الموضوع أو النص الأصلي.")
    prompt = _writer_prompt(request)
    provider = request.writer_provider
    if provider == "auto":
        provider = "gemini" if load_keys(enabled_only=True) else "local"
    try:
        if provider == "gemini":
            from backend.api.studio_pro_routes import _ask_gemini

            text = await _ask_gemini(prompt, 0.72)
        elif provider == "openai":
            text = await _write_with_openai(prompt)
        else:
            text = _local_script(request)
            provider = "local"
    except Exception as exc:
        if request.writer_provider in {"gemini", "openai"}:
            raise HTTPException(status_code=502, detail=f"تعذر استخدام الكاتب المحدد: {exc}") from exc
        text = _local_script(request)
        provider = "local"
    return {
        "success": True,
        "text": text,
        "writer_used": provider,
        "message": (
            "تم إنشاء نص احترافي بالكاتب الذكي."
            if provider != "local"
            else "تم إنشاء مسودة محلية منظمة؛ اربط Gemini أو OpenAI لإبداع أعمق."
        ),
    }


ROLE_PATTERN = re.compile(r"^\s*([^:\n]{2,60})\s*:\s*(.*)$")


def _parse_dialogue(script: str) -> list[tuple[str, str]]:
    turns: list[tuple[str, str]] = []
    current_role = ""
    buffer: list[str] = []
    for raw in script.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = ROLE_PATTERN.match(line)
        if match:
            if current_role and buffer:
                turns.append((current_role, " ".join(buffer)))
            current_role = match.group(1).strip()
            buffer = [match.group(2).strip()] if match.group(2).strip() else []
        elif current_role:
            buffer.append(line)
    if current_role and buffer:
        turns.append((current_role, " ".join(buffer)))
    return turns


def _role_gender(role: str) -> str:
    lowered = role.lower().replace("-", "_").replace(" ", "_")
    female_markers = (
        "امرأة",
        "مذيعة",
        "ضيفة",
        "خبيرة",
        "female",
        "woman",
        "host_female",
        "guest_female",
    )
    return "female" if any(marker in lowered for marker in female_markers) else "male"


@router.post("/dialogue")
async def dialogue(request: DialogueRequest):
    turns = _parse_dialogue(request.script)
    if len(turns) < 2:
        raise HTTPException(status_code=400, detail="اكتب الحوار بصيغة اسم المتحدث: النص.")
    provider = request.provider
    if provider not in PROVIDERS or PROVIDERS[provider].get("catalog_only"):
        raise HTTPException(status_code=400, detail="محرك المقابلة غير متاح.")
    plugin = tts_registry.get_plugin(provider)
    if not plugin or not plugin.check():
        raise HTTPException(status_code=503, detail="محرك المقابلة غير جاهز.")

    by_gender = {
        gender: voices_for(provider, language=request.language, gender=gender) for gender in ("male", "female")
    }
    roles = list(dict.fromkeys(role for role, _ in turns))
    role_voice_map: dict[str, dict[str, Any]] = {}
    gender_indexes = {"male": 0, "female": 0}
    for role in roles:
        gender = _role_gender(role)
        requested_voice = request.role_voices.get(role, "")
        if requested_voice:
            selected = _validate_voice(
                provider,
                requested_voice,
                language=request.language,
                gender=gender,
                locale=None,
            )
        else:
            options = by_gender[gender]
            if not options:
                raise HTTPException(
                    status_code=422,
                    detail=f"لا يوجد صوت {gender} في {provider} للدور {role}. لن يستبدله الاستوديو بجنس آخر.",
                )
            selected = options[gender_indexes[gender] % len(options)]
            gender_indexes[gender] += 1
        role_voice_map[role] = selected

    sources: list[Path] = []
    for index, (role, text) in enumerate(turns):
        selected = role_voice_map[role]
        tone = _tone_for_plugin(provider, request.tone)
        voice_value = selected["id"]
        if provider in {"edge", "gemini", "elevenlabs", "openai"}:
            voice_value += f"|{tone}"
        variation = (1.0, 0.985, 1.012, 0.995, 1.007)[index % 5]
        result = await plugin.generate(
            text=text,
            voice=voice_value,
            language=request.language,
            speed=max(0.7, min(1.25, request.speed * variation)),
        )
        if not result or not result.get("success"):
            raise HTTPException(
                status_code=502,
                detail=f"فشل صوت الدور {role}: {(result or {}).get('message', 'خطأ غير معروف')}",
            )
        source = Path(result.get("file", ""))
        if not source.exists():
            raise HTTPException(status_code=500, detail=f"ملف الدور {role} غير موجود.")
        sources.append(source)

    token = uuid.uuid4().hex[:12]
    raw = OUTPUTS_DIR / f"ultimate_dialogue_{token}.wav"
    _normalize_and_concat(sources, raw, request.pause_ms)
    final = OUTPUTS_DIR / f"ultimate_dialogue_{token}.mp3"
    output = final if request.effect != "none" and process_audio(str(raw), str(final), request.effect) else raw
    target = _copy_to_desktop(output)
    return {
        "success": True,
        "url": f"/api/downloads/{output.name}",
        "file": str(output),
        "desktop_path": str(target) if target else None,
        "desktop_exported": bool(target),
        "provider_used": provider,
        "fallback": False,
        "segments": len(turns),
        "roles": {
            role: {
                "voice_id": metadata["id"],
                "gender": metadata["gender"],
                "language": metadata["language"],
                "locale": metadata["locale"],
            }
            for role, metadata in role_voice_map.items()
        },
        "message": "تم إنتاج الحوار بأصوات مطابقة للغة والجنس دون تبديل صامت." + _desktop_note(target),
    }
