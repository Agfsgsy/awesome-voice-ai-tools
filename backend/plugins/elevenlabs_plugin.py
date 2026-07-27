"""ElevenLabs Human Pro TTS plugin for highly natural multilingual Arabic speech."""

from __future__ import annotations

import hashlib
import os
from typing import Any, Dict, List

import httpx

from backend.core.config import OUTPUTS_DIR
from backend.core.logger import get_logger
from backend.core.provider_settings import provider_config
from backend.core.voice_catalog import voices_for
from backend.plugins.tts_plugin_base import TTSPluginBase

logger = get_logger("plugin_elevenlabs")


class ElevenLabsPlugin(TTSPluginBase):
    name = "elevenlabs"
    label = "Human Pro - ElevenLabs"
    description = "صوت شديد الطبيعية مع تحكم بالثبات والتعبير والتشابه والقوة"
    homepage = "https://elevenlabs.io/docs/api-reference/text-to-speech/convert"
    is_open_source = False
    requires_gpu = False

    MODELS = {
        "eleven_v3": "أعلى تعبير وانفعال — مناسب للمواعظ والدعاء (حتى 5000 حرف)",
        "eleven_multilingual_v2": "طبيعي وثابت — الأفضل للنصوص العربية الطويلة (حتى 10000 حرف)",
        "eleven_flash_v2_5": "سريع — مناسب للمعاينة والتجارب",
        "eleven_turbo_v2_5": "متوازن — سرعة وجودة",
    }

    MODEL_LIMITS = {
        "eleven_v3": 5000,
        "eleven_multilingual_v2": 10000,
        "eleven_flash_v2_5": 40000,
        "eleven_turbo_v2_5": 40000,
    }

    def _api_key(self) -> str:
        return provider_config(self.name).get("api_key", "").strip() or os.getenv("ELEVENLABS_API_KEY", "").strip()

    def _default_voice(self, language: str = "ar", gender: str = "male") -> str:
        field = f"{gender}_voice_id_{'en' if language.startswith('en') else 'ar'}"
        return provider_config(self.name).get(field, "").strip() or os.getenv("ELEVENLABS_VOICE_ID", "").strip()

    def check(self) -> bool:
        return bool(self._api_key())

    def install(self) -> Dict[str, Any]:
        return {
            "success": True,
            "engine": self.name,
            "message": "لا يحتاج إلى تثبيت مكتبات إضافية؛ أدخل مفتاح ElevenLabs ومعرّف الصوت في إعدادات Human Pro.",
        }

    def download_models(self, model_name: str = "eleven_multilingual_v2") -> Dict[str, Any]:
        return {"success": True, "model": model_name, "message": "المحرك سحابي ولا يحتاج تنزيل نموذج."}

    def list_models(self) -> List[Dict[str, Any]]:
        configured = self.check()
        return [
            {"name": name, "label": label, "language": "multi", "downloaded": configured}
            for name, label in self.MODELS.items()
        ]

    def list_voices(self) -> List[Dict[str, str]]:
        return [
            {
                "name": item["id"],
                "label": item["name_ar"],
                "language": item["language"],
                "locale": item["locale"],
                "gender": item["gender"],
            }
            for item in voices_for(self.name)
        ]

    @staticmethod
    def _profile_settings(profile: str) -> Dict[str, float | bool]:
        profiles = {
            "human_ultra": {"stability": 0.43, "similarity_boost": 0.83, "style": 0.48, "use_speaker_boost": True},
            "natural": {"stability": 0.50, "similarity_boost": 0.80, "style": 0.25, "use_speaker_boost": True},
            "sermon_calm": {"stability": 0.61, "similarity_boost": 0.81, "style": 0.36, "use_speaker_boost": True},
            "sermon_powerful": {"stability": 0.39, "similarity_boost": 0.85, "style": 0.67, "use_speaker_boost": True},
            "dua_emotional": {"stability": 0.34, "similarity_boost": 0.79, "style": 0.78, "use_speaker_boost": True},
            "documentary": {"stability": 0.66, "similarity_boost": 0.82, "style": 0.31, "use_speaker_boost": True},
            "energetic": {"stability": 0.32, "similarity_boost": 0.80, "style": 0.72, "use_speaker_boost": True},
            "broadcast_power": {"stability": 0.48, "similarity_boost": 0.84, "style": 0.54, "use_speaker_boost": True},
        }
        return profiles.get(profile, profiles["human_ultra"])

    @staticmethod
    def _prepare_text(text: str) -> str:
        paragraphs = []
        for raw in (text or "").replace("\r", "").split("\n"):
            line = " ".join(raw.split()).strip()
            if line:
                paragraphs.append(line)
        return "\n\n".join(paragraphs)

    async def generate(
        self, text: str, voice: str = "default", language: str = "ar", speed: float = 1.0
    ) -> Dict[str, Any]:
        api_key = self._api_key()
        if not api_key:
            return {
                "success": False,
                "engine": self.name,
                "message": "أدخل مفتاح ElevenLabs من إعدادات Human Pro أولًا.",
            }

        raw_voice = voice or "default"
        profile = "human_ultra"
        if "|" in raw_voice:
            raw_voice, profile = raw_voice.split("|", 1)
        voice_id = self._default_voice(language=language) if raw_voice in {"", "default", "human-pro"} else raw_voice
        if not voice_id:
            return {"success": False, "engine": self.name, "message": "أدخل معرّف الصوت Voice ID في إعدادات Human Pro."}

        clean_text = self._prepare_text(text)
        if not clean_text:
            return {"success": False, "engine": self.name, "message": "النص فارغ."}

        model_id = (
            provider_config(self.name).get("model_id", "").strip()
            or os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2").strip()
            or "eleven_multilingual_v2"
        )
        if model_id not in self.MODELS:
            model_id = "eleven_multilingual_v2"
        limit = self.MODEL_LIMITS.get(model_id, 10000)
        if len(clean_text) > limit:
            return {
                "success": False,
                "engine": self.name,
                "message": f"هذا النموذج يقبل حتى {limit} حرفًا في الطلب الواحد.",
            }

        settings = self._profile_settings(profile)
        settings["speed"] = max(0.7, min(1.2, float(speed)))
        digest = hashlib.sha256(
            f"v240|{voice_id}|{model_id}|{profile}|{speed}|{clean_text}".encode("utf-8")
        ).hexdigest()[:18]
        output = OUTPUTS_DIR / f"human_pro_{profile}_{digest}.mp3"
        if output.exists() and output.stat().st_size > 0:
            return {
                "success": True,
                "engine": self.name,
                "voice": voice_id,
                "profile": profile,
                "model": model_id,
                "file": str(output),
                "url": f"/api/downloads/{output.name}",
                "message": "تم تحميل صوت Human Pro من الذاكرة المؤقتة.",
            }

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {"xi-api-key": api_key, "Accept": "audio/mpeg", "Content-Type": "application/json"}
        payload = {
            "text": clean_text,
            "model_id": model_id,
            "language_code": "ar" if language.startswith("ar") else None,
            "voice_settings": settings,
        }
        payload = {key: value for key, value in payload.items() if value is not None}
        try:
            timeout = httpx.Timeout(180.0, connect=25.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                    params={"output_format": "mp3_44100_192"},
                )
            if response.status_code >= 400:
                detail = response.text[:600]
                if response.status_code in {401, 403}:
                    detail = "مفتاح ElevenLabs غير صحيح أو لا يملك صلاحية Text to Speech."
                elif response.status_code == 422:
                    detail = "معرّف الصوت أو النموذج أو إعدادات الصوت غير صحيحة."
                elif response.status_code == 429:
                    detail = "تم تجاوز الرصيد أو الحد المؤقت في ElevenLabs."
                return {"success": False, "engine": self.name, "message": detail}
            output.write_bytes(response.content)
            if output.stat().st_size == 0:
                output.unlink(missing_ok=True)
                raise RuntimeError("لم تُستلم بيانات صوتية.")
            return {
                "success": True,
                "engine": self.name,
                "voice": voice_id,
                "profile": profile,
                "model": model_id,
                "file": str(output),
                "url": f"/api/downloads/{output.name}",
                "message": "تم إنشاء صوت Human Pro عالي الطبيعية والتعبير.",
            }
        except Exception as exc:
            logger.exception("ElevenLabs generation failed")
            return {"success": False, "engine": self.name, "message": f"تعذر إنشاء صوت Human Pro: {exc}"}


PLUGIN_CLASS = ElevenLabsPlugin
PLUGIN_NAME = "Human Pro - ElevenLabs"
PLUGIN_DESCRIPTION = "Highly natural multilingual Arabic speech with expressive controls"
