"""Azure Speech neural TTS provider with strict locale voices."""

from __future__ import annotations

import hashlib
from typing import Any
from xml.sax.saxutils import escape

import httpx

from backend.core.config import OUTPUTS_DIR
from backend.core.provider_settings import provider_config
from backend.core.voice_catalog import voices_for
from backend.plugins.tts_plugin_base import TTSPluginBase


class AzureTTSPlugin(TTSPluginBase):
    name = "azure"
    label = "Azure AI Speech"
    description = "Azure neural Arabic and English voices with a free F0 tier where available."
    homepage = "https://learn.microsoft.com/azure/ai-services/speech-service/text-to-speech"
    is_open_source = False
    requires_gpu = False

    def _config(self) -> dict[str, str]:
        return provider_config(self.name)

    def check(self) -> bool:
        config = self._config()
        return bool(config.get("api_key") and config.get("region"))

    def install(self) -> dict[str, Any]:
        return {"success": True, "engine": self.name, "message": "Add the Azure Speech key and region."}

    def download_models(self, model_name: str = "neural") -> dict[str, Any]:
        return {"success": True, "model": model_name, "message": "Cloud provider; no model download is required."}

    def list_models(self) -> list[dict[str, Any]]:
        return [{"name": "azure-neural", "language": "multi", "downloaded": self.check()}]

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
        config = self._config()
        api_key = config.get("api_key", "").strip()
        region = config.get("region", "").strip()
        if not api_key or not region:
            return {"success": False, "engine": self.name, "message": "أضف مفتاح Azure والمنطقة أولًا."}
        clean_text = " ".join((text or "").split()).strip()
        if not clean_text:
            return {"success": False, "engine": self.name, "message": "النص فارغ."}
        if len(clean_text) > 12000:
            return {"success": False, "engine": self.name, "message": "قسّم النص إلى مقاطع أقصر من 12000 حرف."}

        raw_voice, _tone = (voice or "default"), "natural"
        if "|" in raw_voice:
            raw_voice, _tone = raw_voice.split("|", 1)
        catalog = {item["id"]: item for item in voices_for(self.name, language=language)}
        metadata = catalog.get(raw_voice)
        if not metadata:
            return {"success": False, "engine": self.name, "message": "صوت Azure غير متوافق مع اللغة المختارة."}

        rate = max(0.7, min(1.25, float(speed)))
        rate_percent = round((rate - 1.0) * 100)
        ssml = (
            f'<speak version="1.0" xml:lang="{metadata["locale"]}">'
            f'<voice name="{raw_voice}"><prosody rate="{rate_percent:+d}%">'
            f"{escape(clean_text)}</prosody></voice></speak>"
        )
        digest = hashlib.sha256(f"azure-v1|{raw_voice}|{language}|{rate}|{clean_text}".encode("utf-8")).hexdigest()[:18]
        output = OUTPUTS_DIR / f"azure_{language}_{digest}.mp3"
        if output.exists() and output.stat().st_size > 0:
            return {
                "success": True,
                "engine": self.name,
                "voice": raw_voice,
                "file": str(output),
                "url": f"/api/downloads/{output.name}",
                "message": "تم تحميل الصوت من الذاكرة المؤقتة.",
            }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=25.0)) as client:
                response = await client.post(
                    f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
                    headers={
                        "Ocp-Apim-Subscription-Key": api_key,
                        "Content-Type": "application/ssml+xml",
                        "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3",
                        "User-Agent": "IbnWaqadiStudio",
                    },
                    content=ssml.encode("utf-8"),
                )
            if response.status_code >= 400:
                detail = response.text[:700] or f"Azure HTTP {response.status_code}"
                return {"success": False, "engine": self.name, "status_code": response.status_code, "message": detail}
            output.write_bytes(response.content)
            return {
                "success": True,
                "engine": self.name,
                "voice": raw_voice,
                "file": str(output),
                "url": f"/api/downloads/{output.name}",
                "message": "تم إنشاء الصوت عبر Azure AI Speech.",
            }
        except Exception as exc:
            return {"success": False, "engine": self.name, "message": f"تعذر الاتصال بـ Azure Speech: {exc}"}


PLUGIN_CLASS = AzureTTSPlugin
