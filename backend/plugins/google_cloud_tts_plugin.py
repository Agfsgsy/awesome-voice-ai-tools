"""Google Cloud Text-to-Speech provider with gender-certified voices."""

from __future__ import annotations

import base64
import hashlib
from typing import Any

import httpx

from backend.core.config import OUTPUTS_DIR
from backend.core.provider_settings import provider_config
from backend.core.voice_catalog import voices_for
from backend.plugins.tts_plugin_base import TTSPluginBase


class GoogleCloudTTSPlugin(TTSPluginBase):
    name = "google_cloud"
    label = "Google Cloud TTS"
    description = "Chirp 3 HD Arabic and English voices with official SSML gender metadata."
    homepage = "https://cloud.google.com/text-to-speech"
    is_open_source = False
    requires_gpu = False

    def _config(self) -> dict[str, str]:
        return provider_config(self.name)

    def check(self) -> bool:
        return bool(self._config().get("api_key"))

    def install(self) -> dict[str, Any]:
        return {"success": True, "engine": self.name, "message": "Add a Google Cloud Text-to-Speech API key."}

    def download_models(self, model_name: str = "chirp3-hd") -> dict[str, Any]:
        return {"success": True, "model": model_name, "message": "Cloud provider; no model download is required."}

    def list_models(self) -> list[dict[str, Any]]:
        return [{"name": "chirp3-hd", "language": "multi", "downloaded": self.check()}]

    def list_voices(self) -> list[dict[str, Any]]:
        return [
            {
                "name": item["id"],
                "label": item["name_en"],
                "language": item["language"],
                "locale": item["locale"],
                "gender": item["gender"],
            }
            for item in voices_for(self.name)
        ]

    async def generate(
        self,
        text: str,
        voice: str = "default",
        language: str = "ar",
        speed: float = 1.0,
    ) -> dict[str, Any]:
        api_key = self._config().get("api_key", "").strip()
        if not api_key:
            return {"success": False, "engine": self.name, "message": "أضف مفتاح Google Cloud TTS أولًا."}
        clean_text = " ".join((text or "").split()).strip()
        if not clean_text:
            return {"success": False, "engine": self.name, "message": "النص فارغ."}
        if len(clean_text) > 5000:
            return {"success": False, "engine": self.name, "message": "قسّم النص إلى مقاطع أقصر من 5000 حرف."}

        raw_voice, _tone = (voice or "default"), "natural"
        if "|" in raw_voice:
            raw_voice, _tone = raw_voice.split("|", 1)
        catalog = {item["id"]: item for item in voices_for(self.name, language=language)}
        metadata = catalog.get(raw_voice)
        if not metadata:
            return {"success": False, "engine": self.name, "message": "صوت Google غير متوافق مع اللغة المختارة."}

        digest = hashlib.sha256(
            f"google-cloud-v1|{raw_voice}|{language}|{speed}|{clean_text}".encode("utf-8")
        ).hexdigest()[:18]
        output = OUTPUTS_DIR / f"google_cloud_{language}_{digest}.mp3"
        if output.exists() and output.stat().st_size > 0:
            return {
                "success": True,
                "engine": self.name,
                "voice": raw_voice,
                "file": str(output),
                "url": f"/api/downloads/{output.name}",
                "message": "تم تحميل الصوت من الذاكرة المؤقتة.",
            }

        payload = {
            "input": {"text": clean_text},
            "voice": {
                "languageCode": metadata["locale"],
                "name": raw_voice,
                "ssmlGender": metadata["gender"].upper(),
            },
            "audioConfig": {
                "audioEncoding": "MP3",
                "speakingRate": max(0.7, min(1.25, float(speed))),
            },
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=25.0)) as client:
                response = await client.post(
                    "https://texttospeech.googleapis.com/v1/text:synthesize",
                    params={"key": api_key},
                    json=payload,
                )
            if response.status_code >= 400:
                try:
                    detail = (response.json().get("error") or {}).get("message") or response.text[:700]
                except Exception:
                    detail = response.text[:700]
                return {"success": False, "engine": self.name, "status_code": response.status_code, "message": detail}
            audio = base64.b64decode(response.json().get("audioContent", ""))
            if not audio:
                raise RuntimeError("لم تُستلم بيانات صوتية.")
            output.write_bytes(audio)
            return {
                "success": True,
                "engine": self.name,
                "voice": raw_voice,
                "file": str(output),
                "url": f"/api/downloads/{output.name}",
                "message": "تم إنشاء الصوت عبر Google Cloud TTS.",
            }
        except Exception as exc:
            return {"success": False, "engine": self.name, "message": f"تعذر الاتصال بـ Google Cloud TTS: {exc}"}


PLUGIN_CLASS = GoogleCloudTTSPlugin
