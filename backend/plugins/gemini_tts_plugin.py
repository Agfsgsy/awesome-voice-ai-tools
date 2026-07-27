"""Google Gemini TTS plugin with Arabic direction, dialect profiles, retries and automatic key rotation."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import re
import wave
from pathlib import Path
from typing import Any, Dict, List

import httpx

from backend.core.config import OUTPUTS_DIR
from backend.core.logger import get_logger
from backend.plugins.tts_plugin_base import TTSPluginBase

logger = get_logger("plugin_gemini_tts")


class GeminiTTSPlugin(TTSPluginBase):
    name = "gemini"
    label = "Google Gemini TTS"
    description = "استوديو صوت عربي تعبيري مع لهجة يمنية وخليجية وتبديل تلقائي للمفاتيح"
    homepage = "https://ai.google.dev/gemini-api/docs/speech-generation"
    is_open_source = False
    requires_gpu = False

    MODELS = {
        "gemini-3.1-flash-tts-preview": "Gemini 3.1 Flash TTS — أحدث وأسرع",
        "gemini-2.5-flash-preview-tts": "Gemini 2.5 Flash TTS — مناسب للخطة المجانية",
        "gemini-2.5-pro-preview-tts": "Gemini 2.5 Pro TTS — أعلى جودة وقد يتطلب فوترة",
    }
    VOICES = {
        "Achernar": "ناعم",
        "Achird": "ودود",
        "Algenib": "أجش",
        "Algieba": "هادئ وقريب",
        "Alnilam": "حازم",
        "Aoede": "خفيف",
        "Autonoe": "مشرق",
        "Callirrhoe": "سلس",
        "Charon": "معلوماتي",
        "Despina": "ناعم",
        "Erinome": "واضح",
        "Gacrux": "ناضج",
        "Iapetus": "واضح",
        "Kore": "قوي وثابت",
        "Leda": "شبابي",
        "Orus": "حازم",
        "Puck": "حيوي",
        "Rasalgethi": "معلوماتي",
        "Sadaltager": "خبير",
        "Sulafat": "دافئ",
        "Vindemiatrix": "لطيف",
    }
    VOICE_GENDERS = {
        "Achernar": "female",
        "Aoede": "female",
        "Autonoe": "female",
        "Callirrhoe": "female",
        "Despina": "female",
        "Erinome": "female",
        "Gacrux": "female",
        "Kore": "female",
        "Leda": "female",
        "Sulafat": "female",
        "Vindemiatrix": "female",
        "Achird": "male",
        "Algenib": "male",
        "Algieba": "male",
        "Alnilam": "male",
        "Charon": "male",
        "Iapetus": "male",
        "Orus": "male",
        "Puck": "male",
        "Rasalgethi": "male",
        "Sadaltager": "male",
    }
    PROFILES = {
        "human_ultra": "اقرأ العربية بصوت بشري شديد الطبيعية، بتنغيم متوازن وتنفس ووقفات واقعية، دون أداء آلي.",
        "natural": "اقرأ بصوت عربي طبيعي وواضح وهادئ، مع نطق دقيق ووقفات مناسبة للمعنى.",
        "yemeni_natural": "أدّ النص بروح يمنية طبيعية دافئة ومفهومة عربيًا، دون مبالغة أو تقليد ساخر، وبنطق واضح صالح للفيديو والبودكاست.",
        "gulf_natural": "أدّ النص بصوت خليجي طبيعي راقٍ وواضح، بنبرة دافئة ووقفات بشرية مناسبة للفيديو والبودكاست.",
        "podcast_natural": "أدّ النص كبودكاست عربي قريب من المستمع، هادئ وواثق، مع تنفس طبيعي وتغيير خفيف في الإيقاع.",
        "lecture_clear": "ألق النص كمحاضرة عربية مرتبة وواضحة، مع إبراز الأفكار الرئيسية ووقفات تعليمية دون تكلف.",
        "sermon_calm": "ألق النص كموعظة هادئة دافئة وخاشعة، بسرعة متأنية ووقفات مؤثرة ونطق عربي فصيح.",
        "sermon_powerful": "ألق النص كخطيب عربي قوي وواثق، بحضور واضح وتصاعد محسوب دون صراخ.",
        "dua_emotional": "اقرأ الدعاء بخشوع وصدق وهدوء، مع تنفس طبيعي ووقفات طويلة قليلًا.",
        "documentary": "اقرأ بأسلوب وثائقي عربي رزين، واضح ومتماسك ومناسب للقصص.",
        "energetic": "اقرأ بحماس إيجابي وطاقة واضحة وإيقاع سريع قليلًا دون فقدان الوضوح.",
        "broadcast_power": "اقرأ بأسلوب إذاعي عربي احترافي، قوي ودافئ وواضح ومناسب للفيديو.",
    }

    def _api_keys(self) -> list[str]:
        raw = os.getenv("GEMINI_API_KEYS", "") or os.getenv("GEMINI_API_KEY", "")
        return list(dict.fromkeys(k.strip() for k in re.split(r"[\n,;|]+", raw) if len(k.strip()) >= 20))

    def _model(self) -> str:
        return os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts").strip()

    def check(self) -> bool:
        return bool(self._api_keys())

    def install(self) -> Dict[str, Any]:
        return {"success": True, "engine": self.name, "message": "لا يحتاج تثبيتًا؛ أضف مفتاح Gemini واحدًا أو أكثر."}

    def download_models(self, model_name: str = "gemini-2.5-flash-preview-tts") -> Dict[str, Any]:
        return {"success": True, "model": model_name, "message": "محرك سحابي ولا يحتاج تنزيل نموذج."}

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {"name": n, "label": l, "language": "multi", "downloaded": self.check()} for n, l in self.MODELS.items()
        ]

    def list_voices(self) -> List[Dict[str, str]]:
        return [
            {
                "name": name,
                "label": label,
                "language": "multi",
                "gender": self.VOICE_GENDERS.get(name, "neutral"),
            }
            for name, label in self.VOICES.items()
        ]

    @staticmethod
    def _save_wav(path: Path, pcm: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(24000)
            output.writeframes(pcm)

    @staticmethod
    def _extract_audio(data: Dict[str, Any]) -> bytes | None:
        for candidate in data.get("candidates") or []:
            for part in (candidate.get("content") or {}).get("parts") or []:
                inline = part.get("inlineData") or part.get("inline_data") or {}
                if inline.get("data"):
                    return base64.b64decode(inline["data"])
        return None

    @staticmethod
    def _detail(response: httpx.Response) -> str:
        try:
            payload = response.json()
            return payload.get("error", {}).get("message") or response.text[:700]
        except Exception:
            return response.text[:700]

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        raw = response.headers.get("retry-after", "").strip()
        try:
            if raw:
                return max(1.0, min(12.0, float(raw)))
        except ValueError:
            pass
        return min(8.0, 1.5 * (2 ** max(0, attempt - 1)))

    async def generate(
        self, text: str, voice: str = "default", language: str = "ar", speed: float = 1.0
    ) -> Dict[str, Any]:
        keys = self._api_keys()
        if not keys:
            return {"success": False, "engine": self.name, "message": "أدخل مفتاح Gemini واحدًا على الأقل."}
        clean_text = "\n".join(line.strip() for line in (text or "").splitlines() if line.strip())
        if not clean_text:
            return {"success": False, "engine": self.name, "message": "النص فارغ."}
        if len(clean_text) > 12000:
            return {
                "success": False,
                "engine": self.name,
                "message": "النص أطول من 12000 حرف. استخدم أداة ترتيب النص وقسّمه إلى حلقات.",
            }

        raw_voice, profile = (voice or "Kore"), "human_ultra"
        if "|" in raw_voice:
            raw_voice, profile = raw_voice.split("|", 1)
        selected_voice = raw_voice if raw_voice in self.VOICES else "Kore"
        preferred = self._model() if self._model() in self.MODELS else "gemini-2.5-flash-preview-tts"
        models = list(
            dict.fromkeys(
                [
                    preferred,
                    "gemini-2.5-flash-preview-tts",
                    "gemini-3.1-flash-tts-preview",
                    "gemini-2.5-pro-preview-tts",
                ]
            )
        )
        guidance = self.PROFILES.get(profile, self.PROFILES["human_ultra"])
        if language.startswith("en"):
            english_profiles = {
                "human_ultra": "Use highly natural human delivery with balanced intonation and realistic pauses.",
                "natural": "Speak naturally and clearly with phrasing that follows the meaning.",
                "podcast_natural": "Use an intimate, confident podcast delivery with subtle breathing.",
                "lecture_clear": "Deliver a structured, clear lecture and emphasize the key ideas.",
                "sermon_calm": "Use a calm, sincere sermon delivery with dignity.",
                "sermon_powerful": "Use a powerful, controlled sermon delivery without shouting.",
                "dua_emotional": "Speak with restrained, sincere emotion and meaningful pauses.",
                "documentary": "Use a composed professional documentary narration.",
                "energetic": "Use positive energy and a lively pace while keeping every word clear.",
                "broadcast_power": "Use a warm, confident professional broadcast delivery.",
            }
            guidance = english_profiles.get(profile, english_profiles["human_ultra"])
            speed_note = "medium" if 0.9 <= speed <= 1.1 else ("slightly slow" if speed < 0.9 else "slightly fast")
            prompt = (
                f"{guidance}\nPace: {speed_note}. Understand the meaning before speaking and vary "
                f"intonation and pauses with each sentence. Speak only this text without additions:\n\n{clean_text}"
            )
            language_code = "en-US"
        else:
            speed_note = "متوسطة" if 0.9 <= speed <= 1.1 else ("بطيئة قليلًا" if speed < 0.9 else "سريعة قليلًا")
            prompt = (
                f"{guidance}\nالسرعة: {speed_note}. افهم المعنى قبل الإلقاء، وغيّر النبرة والوقفات "
                f"حسب الجملة. انطق النص فقط دون إضافة:\n\n{clean_text}"
            )
            language_code = "ar-XA"
        digest = hashlib.sha256(
            f"gemini-v310|{preferred}|{selected_voice}|{profile}|{speed}|{clean_text}".encode()
        ).hexdigest()[:18]
        output = OUTPUTS_DIR / f"gemini_{profile}_{digest}.wav"
        if output.exists() and output.stat().st_size > 44:
            return {
                "success": True,
                "engine": self.name,
                "url": f"/api/downloads/{output.name}",
                "file": str(output),
                "message": "تم تحميل الصوت من الذاكرة المؤقتة.",
            }

        errors: list[str] = []
        quota_only = True
        async with httpx.AsyncClient(timeout=httpx.Timeout(240.0, connect=30.0)) as client:
            for number, key in enumerate(keys, start=1):
                key_exhausted = False
                for model in models:
                    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                    payload = {
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "responseModalities": ["AUDIO"],
                            "speechConfig": {
                                "languageCode": language_code,
                                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": selected_voice}},
                            },
                        },
                    }
                    for attempt in (1, 2):
                        try:
                            response = await client.post(
                                endpoint,
                                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                                json=payload,
                            )
                            if response.status_code == 429:
                                if attempt == 1:
                                    await asyncio.sleep(self._retry_delay(response, attempt))
                                    continue
                                errors.append(f"المفتاح {number}: انتهت الحصة أو تم تجاوز الحد 429")
                                key_exhausted = True
                                break
                            if response.status_code in {401, 403}:
                                quota_only = False
                                errors.append(f"المفتاح {number}: مرفوض {response.status_code}")
                                key_exhausted = True
                                break
                            if response.status_code in {400, 404}:
                                quota_only = False
                                errors.append(f"{model}: غير متاح {response.status_code}")
                                break
                            if response.status_code >= 400:
                                quota_only = False
                                return {
                                    "success": False,
                                    "engine": self.name,
                                    "status_code": response.status_code,
                                    "message": self._detail(response),
                                }
                            pcm = self._extract_audio(response.json())
                            if not pcm:
                                quota_only = False
                                errors.append(f"{model}: لم يرجع بيانات صوتية")
                                break
                            self._save_wav(output, pcm)
                            return {
                                "success": True,
                                "engine": self.name,
                                "model": model,
                                "voice": selected_voice,
                                "profile": profile,
                                "key_used": number,
                                "file": str(output),
                                "url": f"/api/downloads/{output.name}",
                                "message": f"تم إنشاء الصوت بنجاح باستخدام المفتاح رقم {number}.",
                            }
                        except Exception as exc:
                            quota_only = False
                            if attempt == 1:
                                await asyncio.sleep(1.0)
                                continue
                            errors.append(f"المفتاح {number}: {type(exc).__name__}")
                    if key_exhausted:
                        break

        message = "تعذر التوليد بكل مفاتيح Gemini: " + "، ".join(errors[-8:])
        if quota_only:
            message = "انتهت حصة جميع مفاتيح Gemini حاليًا. سيستخدم الاستوديو المحرك الاحتياطي تلقائيًا عند توفره."
        return {
            "success": False,
            "engine": self.name,
            "status_code": 429 if quota_only else 502,
            "error_code": "quota_exhausted" if quota_only else "generation_failed",
            "all_keys_exhausted": quota_only,
            "message": message,
        }


PLUGIN_CLASS = GeminiTTSPlugin
PLUGIN_NAME = "Google Gemini TTS"
PLUGIN_DESCRIPTION = "Arabic studio TTS with Yemeni/Gulf profiles, retry and multi-key fallback"
