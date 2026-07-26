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
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(24000)
            output.writeframes(pcm)

    @staticmethod
    def _extract_audio(data: Dict[str, Any]) -> bytes | None:
        """Read PCM audio from both generateContent and Interactions response shapes."""
        candidates = data.get("candidates") or []
        for candidate in candidates:
            content = candidate.get("content") or {}
            for part in content.get("parts") or []:
                inline = part.get("inlineData") or part.get("inline_data") or {}
                encoded = inline.get("data")
                if encoded:
                    return base64.b64decode(encoded)

        output_audio = data.get("output_audio") or data.get("outputAudio") or {}
        encoded = output_audio.get("data")
        if encoded:
            return base64.b64decode(encoded)

        outputs = data.get("outputs") or []
        for item in outputs:
            audio = item.get("audio") or item.get("output_audio") or {}
            encoded = audio.get("data")
            if encoded:
                return base64.b64decode(encoded)
        return None

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
            error = payload.get("error") or {}
            detail = error.get("message") or response.text[:800]
        except Exception:
            detail = response.text[:800]
        if response.status_code == 429:
            return "تم تجاوز الحصة المجانية أو الرصيد. انتظر قليلًا أو فعّل الفوترة من زر Gemini المدفوع."
        if response.status_code in {401, 403}:
            return "مفتاح Gemini غير صالح، أو المشروع لا يملك صلاحية Gemini API، أو توجد قيود تمنع استخدامه."
        if response.status_code == 404:
            return "نموذج Gemini المحدد غير متاح لهذا المشروع. جرّب Gemini 2.5 Flash TTS."
        return detail

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
        prompt = (
            f"{guidance}\n"
            f"السرعة المطلوبة: {speed_note}.\n"
            "انطق النص العربي كما هو، دون شرح أو مقدمة أو إضافة أو حذف:\n\n"
            f"{clean_text}"
        )

        digest = hashlib.sha256(
            f"gemini-v251|{model}|{selected_voice}|{profile}|{speed}|{clean_text}".encode("utf-8")
        ).hexdigest()[:18]
        output = OUTPUTS_DIR / f"gemini_{profile}_{digest}.wav"
        if output.exists() and output.stat().st_size > 44:
            return {
                "success": True,
                "engine": self.name,
                "model": model,
                "voice": selected_voice,
                "file": str(output),
                "url": f"/api/downloads/{output.name}",
                "message": "تم تحميل صوت Gemini من الذاكرة المؤقتة.",
            }

        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "languageCode": "ar-XA" if language.startswith("ar") else None,
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": selected_voice}
                    },
                },
            },
        }
        if payload["generationConfig"]["speechConfig"]["languageCode"] is None:
            payload["generationConfig"]["speechConfig"].pop("languageCode")

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(240.0, connect=30.0)) as client:
                response = await client.post(
                    endpoint,
                    headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                    json=payload,
                )

            if response.status_code >= 400:
                return {
                    "success": False,
                    "engine": self.name,
                    "message": self._error_message(response),
                }

            data = response.json()
            pcm = self._extract_audio(data)
            if not pcm:
                finish_reason = ""
                try:
                    finish_reason = str(data.get("candidates", [{}])[0].get("finishReason", ""))
                except Exception:
                    pass
                detail = "لم تُرجع Gemini بيانات صوتية."
                if finish_reason:
                    detail += f" سبب الإنهاء: {finish_reason}."
                logger.error("Gemini response contained no audio: %s", str(data)[:2000])
                return {"success": False, "engine": self.name, "message": detail}

            self._save_wav(output, pcm)
            if not output.exists() or output.stat().st_size <= 44:
                output.unlink(missing_ok=True)
                raise RuntimeError("تم استلام استجابة، لكن ملف الصوت الناتج فارغ.")

            return {
                "success": True,
                "engine": self.name,
                "model": model,
                "voice": selected_voice,
                "profile": profile,
                "file": str(output),
                "url": f"/api/downloads/{output.name}",
                "message": "تم إنشاء صوت Gemini العربي بنجاح.",
            }
        except Exception as exc:
            logger.exception("Gemini TTS generation failed")
            return {"success": False, "engine": self.name, "message": f"تعذر إنشاء صوت Gemini: {exc}"}


PLUGIN_CLASS = GeminiTTSPlugin
PLUGIN_NAME = "Google Gemini TTS"
PLUGIN_DESCRIPTION = "Arabic expressive speech with free and paid Gemini TTS models"
