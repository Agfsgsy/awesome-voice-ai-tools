"""Google Gemini TTS plugin with Arabic style prompting and free/paid models."""
from __future__ import annotations

import base64
import hashlib
import os
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
    description = "صوت عربي تعبيري مع توجيه طبيعي للأسلوب واللهجة والسرعة"
    homepage = "https://ai.google.dev/gemini-api/docs/speech-generation"
    is_open_source = False
    requires_gpu = False

    MODELS = {
        "gemini-3.1-flash-tts-preview": "Gemini 3.1 Flash TTS — أحدث وأسرع",
        "gemini-2.5-flash-preview-tts": "Gemini 2.5 Flash TTS — مناسب للخطة المجانية",
        "gemini-2.5-pro-preview-tts": "Gemini 2.5 Pro TTS — أعلى جودة وقد يتطلب فوترة",
    }
    VOICES = {
        "Kore": "قوي وثابت",
        "Sulafat": "دافئ",
        "Gacrux": "ناضج",
        "Iapetus": "واضح",
        "Charon": "معلوماتي",
        "Alnilam": "حازم",
        "Achernar": "ناعم",
        "Vindemiatrix": "لطيف",
        "Puck": "حيوي",
        "Aoede": "خفيف",
    }
    PROFILES = {
        "human_ultra": "اقرأ العربية بصوت بشري شديد الطبيعية، بتنغيم متوازن ووقفات واقعية، دون مبالغة أو أداء آلي.",
        "natural": "اقرأ بصوت عربي طبيعي وواضح وهادئ، مع نطق دقيق ووقفات مناسبة للمعنى.",
        "sermon_calm": "ألق النص كموعظة هادئة دافئة وخاشعة، بسرعة متأنية ووقفات مؤثرة ونطق عربي فصيح.",
        "sermon_powerful": "ألق النص كخطيب عربي قوي وواثق، بحضور واضح وتصاعد محسوب دون صراخ.",
        "dua_emotional": "اقرأ الدعاء بخشوع وصدق وهدوء، مع تنفس طبيعي ووقفات طويلة قليلًا.",
        "documentary": "اقرأ بأسلوب وثائقي عربي رزين، واضح ومتماسك ومناسب للقصص.",
        "energetic": "اقرأ بحماس إيجابي وطاقة واضحة وإيقاع سريع قليلًا دون فقدان الوضوح.",
        "broadcast_power": "اقرأ بأسلوب إذاعي عربي احترافي، قوي ودافئ وواضح ومناسب للفيديو.",
    }

    def _api_key(self) -> str:
        return os.getenv("GEMINI_API_KEY", "").strip()

    def _model(self) -> str:
        return os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts").strip()

    def check(self) -> bool:
        return bool(self._api_key())

    def install(self) -> Dict[str, Any]:
        return {"success": True, "engine": self.name, "message": "لا يحتاج تثبيتًا؛ أنشئ مفتاح Gemini واحفظه داخل البرنامج."}

    def download_models(self, model_name: str = "gemini-2.5-flash-preview-tts") -> Dict[str, Any]:
        return {"success": True, "model": model_name, "message": "محرك سحابي ولا يحتاج تنزيل نموذج."}

    def list_models(self) -> List[Dict[str, Any]]:
        return [{"name": name, "label": label, "language": "multi", "downloaded": self.check()} for name, label in self.MODELS.items()]

    def list_voices(self) -> List[Dict[str, str]]:
        return [{"name": name, "label": label, "language": "ar"} for name, label in self.VOICES.items()]

    @staticmethod
    def _save_wav(path: Path, pcm: bytes) -> None:
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(24000)
            output.writeframes(pcm)

    async def generate(self, text: str, voice: str = "default", language: str = "ar", speed: float = 1.0) -> Dict[str, Any]:
        api_key = self._api_key()
        if not api_key:
            return {"success": False, "engine": self.name, "message": "أدخل مفتاح Gemini API من إعداد Gemini أولًا."}
        clean_text = "\n".join(line.strip() for line in (text or "").splitlines() if line.strip())
        if not clean_text:
            return {"success": False, "engine": self.name, "message": "النص فارغ."}
        if len(clean_text) > 8000:
            return {"success": False, "engine": self.name, "message": "النص أطول من 8000 حرف. قسّمه إلى أجزاء."}

        raw_voice = voice or "Kore"
        profile = "human_ultra"
        if "|" in raw_voice:
            raw_voice, profile = raw_voice.split("|", 1)
        selected_voice = raw_voice if raw_voice in self.VOICES else "Kore"
        model = self._model()
        if model not in self.MODELS:
            model = "gemini-2.5-flash-preview-tts"
        guidance = self.PROFILES.get(profile, self.PROFILES["human_ultra"])
        speed_note = "متوسطة"
        if speed < 0.9:
            speed_note = "بطيئة قليلًا"
        elif speed > 1.1:
            speed_note = "سريعة قليلًا"
        prompt = f"{guidance}\nالسرعة المطلوبة: {speed_note}.\nاقرأ النص التالي كما هو دون إضافة أو حذف:\n\n{clean_text}"

        digest = hashlib.sha256(f"gemini-v250|{model}|{selected_voice}|{profile}|{speed}|{clean_text}".encode("utf-8")).hexdigest()[:18]
        output = OUTPUTS_DIR / f"gemini_{profile}_{digest}.wav"
        if output.exists() and output.stat().st_size > 0:
            return {"success": True, "engine": self.name, "model": model, "voice": selected_voice, "file": str(output), "url": f"/api/downloads/{output.name}", "message": "تم تحميل صوت Gemini من الذاكرة المؤقتة."}

        payload = {
            "model": model,
            "input": prompt,
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": selected_voice}]},
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=25.0)) as client:
                response = await client.post(
                    "https://generativelanguage.googleapis.com/v1beta/interactions",
                    headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                    json=payload,
                )
            if response.status_code >= 400:
                try:
                    error = response.json().get("error", {})
                    detail = error.get("message") or response.text[:600]
                except Exception:
                    detail = response.text[:600]
                if response.status_code == 429:
                    detail = "تم تجاوز الحصة المجانية أو الرصيد. انتظر أو فعّل الفوترة من زر Gemini المدفوع."
                elif response.status_code in {401, 403}:
                    detail = "مفتاح Gemini غير صالح أو محظور أو غير مقيّد لخدمة Gemini API."
                return {"success": False, "engine": self.name, "message": detail}
            data = response.json()
            audio = data.get("output_audio", {}).get("data")
            if not audio:
                raise RuntimeError("لم تُرجع Gemini بيانات صوتية.")
            self._save_wav(output, base64.b64decode(audio))
            return {"success": True, "engine": self.name, "model": model, "voice": selected_voice, "profile": profile, "file": str(output), "url": f"/api/downloads/{output.name}", "message": "تم إنشاء صوت Gemini العربي بنجاح."}
        except Exception as exc:
            logger.exception("Gemini TTS generation failed")
            return {"success": False, "engine": self.name, "message": f"تعذر إنشاء صوت Gemini: {exc}"}


PLUGIN_CLASS = GeminiTTSPlugin
PLUGIN_NAME = "Google Gemini TTS"
PLUGIN_DESCRIPTION = "Arabic expressive speech with free and paid Gemini TTS models"
