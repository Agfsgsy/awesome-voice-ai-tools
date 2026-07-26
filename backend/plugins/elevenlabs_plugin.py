"""ElevenLabs Human Pro TTS plugin for highly natural multilingual Arabic speech."""
from __future__ import annotations

import hashlib
import os
from typing import Any, Dict, List

import httpx

from backend.core.config import OUTPUTS_DIR
from backend.core.logger import get_logger
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
        "eleven_multilingual_v2": "متعدد اللغات — أعلى جودة للنصوص العربية الطويلة",
        "eleven_flash_v2_5": "سريع — مناسب للمعاينة",
        "eleven_turbo_v2_5": "متوازن — سرعة وجودة",
    }

    def _api_key(self) -> str:
        return os.getenv("ELEVENLABS_API_KEY", "").strip()

    def _default_voice(self) -> str:
        return os.getenv("ELEVENLABS_VOICE_ID", "").strip()

    def check(self) -> bool:
        return bool(self._api_key() and self._default_voice())

    def install(self) -> Dict[str, Any]:
        return {
            "success": True,
            "engine": self.name,
            "message": "لا يحتاج إلى تثبيت مكتبات إضافية؛ أدخل مفتاح ElevenLabs ومعرّف الصوت في الإعدادات.",
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
        voice_id = self._default_voice()
        return ([{"name": voice_id, "label": "صوت Human Pro المحفوظ", "language": "ar"}] if voice_id else [])

    @staticmethod
    def _profile_settings(profile: str) -> Dict[str, float | bool]:
        profiles = {
            "natural": {"stability": 0.48, "similarity_boost": 0.78, "style": 0.22, "use_speaker_boost": True},
            "sermon_calm": {"stability": 0.62, "similarity_boost": 0.78, "style": 0.32, "use_speaker_boost": True},
            "sermon_powerful": {"stability": 0.42, "similarity_boost": 0.82, "style": 0.62, "use_speaker_boost": True},
            "dua_emotional": {"stability": 0.38, "similarity_boost": 0.76, "style": 0.72, "use_speaker_boost": True},
            "documentary": {"stability": 0.66, "similarity_boost": 0.80, "style": 0.28, "use_speaker_boost": True},
            "energetic": {"stability": 0.35, "similarity_boost": 0.78, "style": 0.68, "use_speaker_boost": True},
        }
        return profiles.get(profile, profiles["natural"])

    async def generate(self, text: str, voice: str = "default", language: str = "ar", speed: float = 1.0) -> Dict[str, Any]:
        api_key = self._api_key()
        if not api_key:
            return {"success": False, "engine": self.name, "message": "أدخل مفتاح ElevenLabs من إعدادات Human Pro أولًا."}

        raw_voice = voice or "default"
        profile = "natural"
        if "|" in raw_voice:
            raw_voice, profile = raw_voice.split("|", 1)
        voice_id = self._default_voice() if raw_voice in {"", "default", "human-pro"} else raw_voice
        if not voice_id:
            return {"success": False, "engine": self.name, "message": "أدخل معرّف الصوت Voice ID في إعدادات Human Pro."}

        clean_text = " ".join((text or "").split()).strip()
        if not clean_text:
            return {"success": False, "engine": self.name, "message": "النص فارغ."}
        if len(clean_text) > 10000:
            return {"success": False, "engine": self.name, "message": "النص أطول من 10000 حرف."}

        model_id = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2").strip() or "eleven_multilingual_v2"
        settings = self._profile_settings(profile)
        settings["speed"] = max(0.7, min(1.2, float(speed)))
        digest = hashlib.sha256(f"{voice_id}|{model_id}|{profile}|{speed}|{clean_text}".encode("utf-8")).hexdigest()[:18]
        output = OUTPUTS_DIR / f"human_pro_{profile}_{digest}.mp3"
        if output.exists() and output.stat().st_size > 0:
            return {"success": True, "engine": self.name, "voice": voice_id, "profile": profile, "file": str(output), "url": f"/api/downloads/{output.name}", "message": "تم إنشاء الصوت Human Pro من الذاكرة المؤقتة."}

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {"xi-api-key": api_key, "Accept": "audio/mpeg", "Content-Type": "application/json"}
        payload = {"text": clean_text, "model_id": model_id, "voice_settings": settings}
        try:
            timeout = httpx.Timeout(120.0, connect=20.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, headers=headers, json=payload, params={"output_format": "mp3_44100_192"})
            if response.status_code >= 400:
                detail = response.text[:500]
                if response.status_code in {401, 403}:
                    detail = "مفتاح ElevenLabs غير صحيح أو لا يملك صلاحية."
                elif response.status_code == 422:
                    detail = "معرّف الصوت أو إعدادات الصوت غير صحيحة."
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
                "file": str(output),
                "url": f"/api/downloads/{output.name}",
                "message": "تم إنشاء صوت Human Pro عالي الطبيعية.",
            }
        except Exception as exc:
            logger.exception("ElevenLabs generation failed")
            return {"success": False, "engine": self.name, "message": f"تعذر إنشاء صوت Human Pro: {exc}"}


PLUGIN_CLASS = ElevenLabsPlugin
PLUGIN_NAME = "Human Pro - ElevenLabs"
PLUGIN_DESCRIPTION = "Highly natural multilingual Arabic speech with expressive controls"
