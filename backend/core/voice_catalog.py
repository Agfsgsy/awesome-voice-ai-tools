"""One authoritative voice catalog for strict language and gender matching."""

from __future__ import annotations

from typing import Any

from backend.core.provider_settings import provider_config

TONE_PROFILES: dict[str, dict[str, str]] = {
    "natural": {
        "ar": "طبيعي متوازن",
        "en": "Natural and balanced",
        "instruction_ar": "اقرأ بطبيعية ووضوح وتنغيم بشري متزن.",
        "instruction_en": "Speak naturally with clear pronunciation and balanced human intonation.",
    },
    "broadcast": {
        "ar": "إذاعي احترافي",
        "en": "Professional broadcast",
        "instruction_ar": "أدِّ النص كمذيع محترف، واثق ودافئ، دون مبالغة.",
        "instruction_en": "Deliver this like a warm, confident professional broadcaster without exaggeration.",
    },
    "podcast": {
        "ar": "بودكاست قريب",
        "en": "Intimate podcast",
        "instruction_ar": "تحدث بقرب وصدق وهدوء، مع وقفات وتنفس طبيعيين.",
        "instruction_en": "Use an intimate, sincere podcast delivery with natural pauses and breathing.",
    },
    "lecture": {
        "ar": "محاضرة واضحة",
        "en": "Clear lecture",
        "instruction_ar": "ألقِ النص كمحاضر واضح، أبرز الأفكار المهمة واستخدم وقفات تعليمية.",
        "instruction_en": "Speak as a clear lecturer, emphasizing key ideas with instructional pauses.",
    },
    "sermon_calm": {
        "ar": "موعظة هادئة",
        "en": "Calm sermon",
        "instruction_ar": "ألقِ النص كموعظة هادئة صادقة، بخشوع ووقار ومن دون تمثيل زائد.",
        "instruction_en": "Deliver a calm, sincere sermon with dignity and restrained emotion.",
    },
    "sermon_powerful": {
        "ar": "خطبة قوية",
        "en": "Powerful sermon",
        "instruction_ar": "ألقِ النص بحضور خطابي قوي وتصاعد محسوب من دون صراخ.",
        "instruction_en": "Use a powerful, controlled sermon delivery that builds intensity without shouting.",
    },
    "emotional": {
        "ar": "عاطفي مؤثر",
        "en": "Emotionally moving",
        "instruction_ar": "أدِّ النص بصدق عاطفي ووقفات مؤثرة من دون مبالغة مسرحية.",
        "instruction_en": "Use sincere emotion and meaningful pauses without becoming theatrical.",
    },
    "documentary": {
        "ar": "وثائقي رزين",
        "en": "Documentary",
        "instruction_ar": "اقرأ بأسلوب وثائقي رزين وواضح ومتماسك.",
        "instruction_en": "Use a composed, clear and cohesive documentary narration.",
    },
    "energetic": {
        "ar": "حماسي",
        "en": "Energetic",
        "instruction_ar": "تحدث بطاقة إيجابية وإيقاع نشط مع الحفاظ على وضوح الكلمات.",
        "instruction_en": "Speak with positive energy and an active pace while keeping every word clear.",
    },
}


def _voice(
    provider: str,
    voice_id: str,
    *,
    language: str,
    locale: str,
    gender: str,
    name_ar: str,
    name_en: str,
    quality: str = "neural",
    strict_gender: bool = True,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "id": voice_id,
        "language": language,
        "locale": locale,
        "gender": gender,
        "name_ar": name_ar,
        "name_en": name_en,
        "quality": quality,
        "strict_gender": strict_gender,
    }


EDGE_VOICES = [
    _voice(
        "edge",
        "ar-SA-HamedNeural",
        language="ar",
        locale="ar-SA",
        gender="male",
        name_ar="حامد — سعودي",
        name_en="Hamed — Saudi",
    ),
    _voice(
        "edge",
        "ar-SA-ZariyahNeural",
        language="ar",
        locale="ar-SA",
        gender="female",
        name_ar="زارية — سعودية",
        name_en="Zariyah — Saudi",
    ),
    _voice(
        "edge",
        "ar-YE-SalehNeural",
        language="ar",
        locale="ar-YE",
        gender="male",
        name_ar="صالح — يمني",
        name_en="Saleh — Yemeni",
    ),
    _voice(
        "edge",
        "ar-YE-MaryamNeural",
        language="ar",
        locale="ar-YE",
        gender="female",
        name_ar="مريم — يمنية",
        name_en="Maryam — Yemeni",
    ),
    _voice(
        "edge",
        "ar-EG-ShakirNeural",
        language="ar",
        locale="ar-EG",
        gender="male",
        name_ar="شاكر — مصري",
        name_en="Shakir — Egyptian",
    ),
    _voice(
        "edge",
        "ar-EG-SalmaNeural",
        language="ar",
        locale="ar-EG",
        gender="female",
        name_ar="سلمى — مصرية",
        name_en="Salma — Egyptian",
    ),
    _voice(
        "edge",
        "ar-AE-HamdanNeural",
        language="ar",
        locale="ar-AE",
        gender="male",
        name_ar="حمدان — إماراتي",
        name_en="Hamdan — Emirati",
    ),
    _voice(
        "edge",
        "ar-AE-FatimaNeural",
        language="ar",
        locale="ar-AE",
        gender="female",
        name_ar="فاطمة — إماراتية",
        name_en="Fatima — Emirati",
    ),
    _voice(
        "edge",
        "ar-JO-TaimNeural",
        language="ar",
        locale="ar-JO",
        gender="male",
        name_ar="تيم — أردني",
        name_en="Taim — Jordanian",
    ),
    _voice(
        "edge",
        "ar-JO-SanaNeural",
        language="ar",
        locale="ar-JO",
        gender="female",
        name_ar="سناء — أردنية",
        name_en="Sana — Jordanian",
    ),
    _voice(
        "edge",
        "ar-MA-JamalNeural",
        language="ar",
        locale="ar-MA",
        gender="male",
        name_ar="جمال — مغربي",
        name_en="Jamal — Moroccan",
    ),
    _voice(
        "edge",
        "ar-MA-MounaNeural",
        language="ar",
        locale="ar-MA",
        gender="female",
        name_ar="منى — مغربية",
        name_en="Mouna — Moroccan",
    ),
    _voice(
        "edge",
        "ar-IQ-BasselNeural",
        language="ar",
        locale="ar-IQ",
        gender="male",
        name_ar="باسل — عراقي",
        name_en="Bassel — Iraqi",
    ),
    _voice(
        "edge",
        "ar-IQ-RanaNeural",
        language="ar",
        locale="ar-IQ",
        gender="female",
        name_ar="رنا — عراقية",
        name_en="Rana — Iraqi",
    ),
    _voice(
        "edge",
        "ar-KW-FahedNeural",
        language="ar",
        locale="ar-KW",
        gender="male",
        name_ar="فهد — كويتي",
        name_en="Fahed — Kuwaiti",
    ),
    _voice(
        "edge",
        "ar-KW-NouraNeural",
        language="ar",
        locale="ar-KW",
        gender="female",
        name_ar="نورة — كويتية",
        name_en="Noura — Kuwaiti",
    ),
    _voice(
        "edge",
        "ar-LB-RamiNeural",
        language="ar",
        locale="ar-LB",
        gender="male",
        name_ar="رامي — لبناني",
        name_en="Rami — Lebanese",
    ),
    _voice(
        "edge",
        "ar-LB-LaylaNeural",
        language="ar",
        locale="ar-LB",
        gender="female",
        name_ar="ليلى — لبنانية",
        name_en="Layla — Lebanese",
    ),
    _voice(
        "edge",
        "ar-OM-AbdullahNeural",
        language="ar",
        locale="ar-OM",
        gender="male",
        name_ar="عبدالله — عُماني",
        name_en="Abdullah — Omani",
    ),
    _voice(
        "edge",
        "ar-OM-AyshaNeural",
        language="ar",
        locale="ar-OM",
        gender="female",
        name_ar="عائشة — عُمانية",
        name_en="Aysha — Omani",
    ),
    _voice(
        "edge",
        "ar-QA-MoazNeural",
        language="ar",
        locale="ar-QA",
        gender="male",
        name_ar="معاذ — قطري",
        name_en="Moaz — Qatari",
    ),
    _voice(
        "edge",
        "ar-QA-AmalNeural",
        language="ar",
        locale="ar-QA",
        gender="female",
        name_ar="أمل — قطرية",
        name_en="Amal — Qatari",
    ),
    _voice(
        "edge",
        "ar-SY-LaithNeural",
        language="ar",
        locale="ar-SY",
        gender="male",
        name_ar="ليث — سوري",
        name_en="Laith — Syrian",
    ),
    _voice(
        "edge",
        "ar-SY-AmanyNeural",
        language="ar",
        locale="ar-SY",
        gender="female",
        name_ar="أماني — سورية",
        name_en="Amany — Syrian",
    ),
    _voice(
        "edge",
        "ar-DZ-IsmaelNeural",
        language="ar",
        locale="ar-DZ",
        gender="male",
        name_ar="إسماعيل — جزائري",
        name_en="Ismael — Algerian",
    ),
    _voice(
        "edge",
        "ar-DZ-AminaNeural",
        language="ar",
        locale="ar-DZ",
        gender="female",
        name_ar="أمينة — جزائرية",
        name_en="Amina — Algerian",
    ),
    _voice(
        "edge",
        "ar-TN-HediNeural",
        language="ar",
        locale="ar-TN",
        gender="male",
        name_ar="الهادي — تونسي",
        name_en="Hedi — Tunisian",
    ),
    _voice(
        "edge",
        "ar-TN-ReemNeural",
        language="ar",
        locale="ar-TN",
        gender="female",
        name_ar="ريم — تونسية",
        name_en="Reem — Tunisian",
    ),
    _voice(
        "edge",
        "ar-BH-AliNeural",
        language="ar",
        locale="ar-BH",
        gender="male",
        name_ar="علي — بحريني",
        name_en="Ali — Bahraini",
    ),
    _voice(
        "edge",
        "ar-BH-LailaNeural",
        language="ar",
        locale="ar-BH",
        gender="female",
        name_ar="ليلى — بحرينية",
        name_en="Laila — Bahraini",
    ),
    _voice(
        "edge",
        "ar-LY-OmarNeural",
        language="ar",
        locale="ar-LY",
        gender="male",
        name_ar="عمر — ليبي",
        name_en="Omar — Libyan",
    ),
    _voice(
        "edge",
        "ar-LY-ImanNeural",
        language="ar",
        locale="ar-LY",
        gender="female",
        name_ar="إيمان — ليبية",
        name_en="Iman — Libyan",
    ),
    _voice(
        "edge",
        "en-US-GuyNeural",
        language="en",
        locale="en-US",
        gender="male",
        name_ar="جاي — أمريكي",
        name_en="Guy — American",
    ),
    _voice(
        "edge",
        "en-US-JennyNeural",
        language="en",
        locale="en-US",
        gender="female",
        name_ar="جيني — أمريكية",
        name_en="Jenny — American",
    ),
    _voice(
        "edge",
        "en-GB-RyanNeural",
        language="en",
        locale="en-GB",
        gender="male",
        name_ar="رايان — بريطاني",
        name_en="Ryan — British",
    ),
    _voice(
        "edge",
        "en-GB-SoniaNeural",
        language="en",
        locale="en-GB",
        gender="female",
        name_ar="سونيا — بريطانية",
        name_en="Sonia — British",
    ),
    _voice(
        "edge",
        "en-AU-WilliamNeural",
        language="en",
        locale="en-AU",
        gender="male",
        name_ar="ويليام — أسترالي",
        name_en="William — Australian",
    ),
    _voice(
        "edge",
        "en-AU-NatashaNeural",
        language="en",
        locale="en-AU",
        gender="female",
        name_ar="ناتاشا — أسترالية",
        name_en="Natasha — Australian",
    ),
]

PIPER_VOICES = [
    _voice(
        "piper",
        "kareem",
        language="ar",
        locale="ar-JO",
        gender="male",
        name_ar="كريم — عربي محلي",
        name_en="Kareem — Local Arabic",
        quality="local",
    ),
]

GEMINI_BASE = {
    "Achernar": ("female", "ناعم", "Soft"),
    "Aoede": ("female", "خفيف", "Breezy"),
    "Autonoe": ("female", "مشرق", "Bright"),
    "Callirrhoe": ("female", "سلس", "Easy-going"),
    "Despina": ("female", "ناعم", "Smooth"),
    "Erinome": ("female", "واضح", "Clear"),
    "Gacrux": ("female", "ناضج", "Mature"),
    "Kore": ("female", "ثابت", "Firm"),
    "Leda": ("female", "شبابي", "Youthful"),
    "Sulafat": ("female", "دافئ", "Warm"),
    "Vindemiatrix": ("female", "لطيف", "Gentle"),
    "Achird": ("male", "ودود", "Friendly"),
    "Algenib": ("male", "أجش", "Gravelly"),
    "Algieba": ("male", "هادئ", "Smooth"),
    "Alnilam": ("male", "ثابت", "Firm"),
    "Charon": ("male", "معلوماتي", "Informative"),
    "Iapetus": ("male", "واضح", "Clear"),
    "Orus": ("male", "حازم", "Firm"),
    "Puck": ("male", "حيوي", "Upbeat"),
    "Rasalgethi": ("male", "معلوماتي", "Informative"),
    "Sadaltager": ("male", "خبير", "Knowledgeable"),
}
GEMINI_VOICES = [
    _voice(
        "gemini",
        name,
        language=language,
        locale="ar-XA" if language == "ar" else "en-US",
        gender=gender,
        name_ar=f"{name} — {label_ar}",
        name_en=f"{name} — {label_en}",
        quality="generative",
    )
    for language in ("ar", "en")
    for name, (gender, label_ar, label_en) in GEMINI_BASE.items()
]

GOOGLE_CLOUD_VOICES = [
    _voice(
        "google_cloud",
        f"ar-XA-Chirp3-HD-{name}",
        language="ar",
        locale="ar-XA",
        gender=gender,
        name_ar=f"{name} — Google HD",
        name_en=f"{name} — Arabic Google HD",
        quality="premium",
    )
    for name, (gender, _, _) in GEMINI_BASE.items()
] + [
    _voice(
        "google_cloud",
        f"en-US-Chirp3-HD-{name}",
        language="en",
        locale="en-US",
        gender=gender,
        name_ar=f"{name} — إنجليزي Google HD",
        name_en=f"{name} — English Google HD",
        quality="premium",
    )
    for name, (gender, _, _) in GEMINI_BASE.items()
]

AZURE_VOICES = [{**item, "provider": "azure", "quality": "premium"} for item in EDGE_VOICES]

OPENAI_VOICES = [
    _voice(
        "openai",
        name,
        language=language,
        locale="ar-XA" if language == "ar" else "en-US",
        gender="neutral",
        name_ar=f"{name} — محايد رسميًا",
        name_en=f"{name} — officially ungendered",
        quality="generative",
        strict_gender=False,
    )
    for language in ("ar", "en")
    for name in ("marin", "cedar", "coral", "onyx", "sage", "shimmer")
]


def _elevenlabs_configured_voices() -> list[dict[str, Any]]:
    config = provider_config("elevenlabs")
    voices: list[dict[str, Any]] = []
    for language in ("ar", "en"):
        locale = "ar-SA" if language == "ar" else "en-US"
        for gender in ("male", "female"):
            field = f"{gender}_voice_id_{language}"
            voice_id = config.get(field, "").strip()
            if voice_id:
                voices.append(
                    _voice(
                        "elevenlabs",
                        voice_id,
                        language=language,
                        locale=locale,
                        gender=gender,
                        name_ar=f"ElevenLabs — {'رجل' if gender == 'male' else 'امرأة'} ({language.upper()})",
                        name_en=f"ElevenLabs — {gender.title()} ({language.upper()})",
                        quality="premium",
                    )
                )
    return voices


def all_voices() -> list[dict[str, Any]]:
    return [
        *EDGE_VOICES,
        *PIPER_VOICES,
        *GEMINI_VOICES,
        *GOOGLE_CLOUD_VOICES,
        *AZURE_VOICES,
        *OPENAI_VOICES,
        *_elevenlabs_configured_voices(),
    ]


def voices_for(
    provider: str,
    *,
    language: str | None = None,
    gender: str | None = None,
    locale: str | None = None,
) -> list[dict[str, Any]]:
    result = [item for item in all_voices() if item["provider"] == provider]
    if language:
        result = [item for item in result if item["language"] == language]
    if gender:
        result = [item for item in result if item["gender"] == gender]
    if locale:
        exact = [item for item in result if item["locale"].lower() == locale.lower()]
        if exact:
            result = exact
    return result


def voice_by_id(provider: str, voice_id: str) -> dict[str, Any] | None:
    return next(
        (item for item in all_voices() if item["provider"] == provider and item["id"] == voice_id),
        None,
    )


def choose_voice(
    provider: str,
    *,
    language: str,
    gender: str,
    locale: str | None = None,
) -> dict[str, Any] | None:
    matches = voices_for(provider, language=language, gender=gender, locale=locale)
    return matches[0] if matches else None
