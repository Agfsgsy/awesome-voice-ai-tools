"""Google Gemini TTS plugin with Arabic direction, dialect profiles, and automatic key rotation."""
from __future__ import annotations

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
        "Kore": "قوي وثابت", "Sulafat": "دافئ", "Gacrux": "ناضج", "Iapetus": "واضح",
        "Charon": "معلوماتي", "Alnilam": "حازم", "Achernar": "ناعم", "Vindemiatrix": "لطيف",
        "Puck": "حيوي", "Aoede": "خفيف",
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
        return [{"name": n, "label": l, "language": "multi", "downloaded": self.check()} for n, l in self.MODELS.items()]

    def list_voices(self) -> List[Dict[str, str]]:
        return [{"name": n, "label": l, "language": "ar"} for n, l in self.VOICES.items()]

    @staticmethod
    def _save_wav(path: Path, pcm: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1); output.setsampwidth(2); output.setframerate(24000); output.writeframes(pcm)

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
            return response.json().get("error", {}).get("message") or response.text[:700]
        except Exception:
            return response.text[:700]

    async def generate(self, text: str, voice: str = "default", language: str = "ar", speed: float = 1.0) -> Dict[str, Any]:
        keys = self._api_keys()
        if not keys:
            return {"success": False, "engine": self.name, "message": "أدخل مفتاح Gemini واحدًا على الأقل."}
        clean_text = "\n".join(line.strip() for line in (text or "").splitlines() if line.strip())
        if not clean_text:
            return {"success": False, "engine": self.name, "message": "النص فارغ."}
        if len(clean_text) > 12000:
            return {"success": False, "engine": self.name, "message": "النص أطول من 12000 حرف. استخدم أداة ترتيب النص وقسّمه إلى حلقات."}

        raw_voice, profile = (voice or "Kore"), "human_ultra"
        if "|" in raw_voice:
            raw_voice, profile = raw_voice.split("|", 1)
        selected_voice = raw_voice if raw_voice in self.VOICES else "Kore"
        model = self._model() if self._model() in self.MODELS else "gemini-2.5-flash-preview-tts"
        guidance = self.PROFILES.get(profile, self.PROFILES["human_ultra"])
        speed_note = "متوسطة" if 0.9 <= speed <= 1.1 else ("بطيئة قليلًا" if speed < 0.9 else "سريعة قليلًا")
        prompt = f"{guidance}\nالسرعة: {speed_note}. افهم المعنى قبل الإلقاء، وغيّر النبرة والوقفات حسب الجملة. انطق النص فقط دون إضافة:\n\n{clean_text}"
        digest = hashlib.sha256(f"gemini-v260|{model}|{selected_voice}|{profile}|{speed}|{clean_text}".encode()).hexdigest()[:18]
        output = OUTPUTS_DIR / f"gemini_{profile}_{digest}.wav"
        if output.exists() and output.stat().st_size > 44:
            return {"success": True, "engine": self.name, "url": f"/api/downloads/{output.name}", "file": str(output), "message": "تم تحميل الصوت من الذاكرة المؤقتة."}

        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"languageCode": "ar-XA", "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": selected_voice}}}}}
        errors = []
        async with httpx.AsyncClient(timeout=httpx.Timeout(240.0, connect=30.0)) as client:
            for number, key in enumerate(keys, start=1):
                try:
                    response = await client.post(endpoint, headers={"x-goog-api-key": key, "Content-Type": "application/json"}, json=payload)
                    if response.status_code >= 400:
                        errors.append(f"المفتاح {number}: {response.status_code}")
                        if response.status_code in {401, 403, 429}:
                            continue
                        return {"success": False, "engine": self.name, "message": self._detail(response)}
                    pcm = self._extract_audio(response.json())
                    if not pcm:
                        errors.append(f"المفتاح {number}: لا توجد بيانات صوتية")
                        continue
                    self._save_wav(output, pcm)
                    return {"success": True, "engine": self.name, "model": model, "voice": selected_voice, "profile": profile, "key_used": number, "file": str(output), "url": f"/api/downloads/{output.name}", "message": f"تم إنشاء الصوت بنجاح باستخدام المفتاح رقم {number}."}
                except Exception as exc:
                    errors.append(f"المفتاح {number}: {type(exc).__name__}")
                    continue
        return {"success": False, "engine": self.name, "message": "تعذر التوليد بكل المفاتيح: " + "، ".join(errors)}


PLUGIN_CLASS = GeminiTTSPlugin
PLUGIN_NAME = "Google Gemini TTS"
PLUGIN_DESCRIPTION = "Arabic studio TTS with Yemeni/Gulf profiles and multi-key fallback"
