"""OpenAI instruction-guided text-to-speech provider."""

from __future__ import annotations

import hashlib
from typing import Any

import httpx

from backend.core.config import OUTPUTS_DIR
from backend.core.provider_settings import provider_config
from backend.core.voice_catalog import TONE_PROFILES, voices_for
from backend.plugins.tts_plugin_base import TTSPluginBase


class OpenAITTSPlugin(TTSPluginBase):
    name = "openai"
    label = "OpenAI TTS"
    description = "Instruction-guided multilingual speech; paid API with no free API tier guarantee."
    homepage = "https://developers.openai.com/api/docs/models/gpt-4o-mini-tts"
    is_open_source = False
    requires_gpu = False

    def _config(self) -> dict[str, str]:
        return provider_config(self.name)

    def check(self) -> bool:
        return bool(self._config().get("api_key"))

    def install(self) -> dict[str, Any]:
        return {"success": True, "engine": self.name, "message": "Add an OpenAI API key in Provider Connections."}

    def download_models(self, model_name: str = "gpt-4o-mini-tts") -> dict[str, Any]:
        return {"success": True, "model": model_name, "message": "Cloud provider; no local model download is required."}

    def list_models(self) -> list[dict[str, Any]]:
        configured = self.check()
        return [{"name": "gpt-4o-mini-tts", "language": "multi", "downloaded": configured}]

    def list_voices(self) -> list[dict[str, Any]]:
        return [
            {
                "name": item["id"],
                "label": item["name_en"],
                "language": item["language"],
                "locale": item["locale"],
                "gender": item["gender"],
                "strict_gender": item["strict_gender"],
            }
            for item in voices_for(self.name)
        ]

    async def generate(
        self,
        text: str,
        voice: str = "marin",
        language: str = "ar",
        speed: float = 1.0,
    ) -> dict[str, Any]:
        config = self._config()
        api_key = config.get("api_key", "").strip()
        if not api_key:
            return {"success": False, "engine": self.name, "message": "أضف مفتاح OpenAI أولًا."}
        clean_text = " ".join((text or "").split()).strip()
        if not clean_text:
            return {"success": False, "engine": self.name, "message": "النص فارغ."}
        if len(clean_text) > 4096:
            return {"success": False, "engine": self.name, "message": "OpenAI يقبل حتى 4096 حرفًا في الطلب الواحد."}

        raw_voice, tone = (voice or "marin"), "natural"
        if "|" in raw_voice:
            raw_voice, tone = raw_voice.split("|", 1)
        allowed = {item["id"] for item in voices_for(self.name, language=language)}
        if raw_voice not in allowed:
            return {"success": False, "engine": self.name, "message": "الصوت غير متوافق مع اللغة المختارة."}

        profile = TONE_PROFILES.get(tone, TONE_PROFILES["natural"])
        instruction = profile["instruction_ar" if language == "ar" else "instruction_en"]
        model = config.get("model_id", "").strip() or "gpt-4o-mini-tts"
        digest = hashlib.sha256(
            f"openai-v1|{model}|{raw_voice}|{language}|{tone}|{speed}|{clean_text}".encode("utf-8")
        ).hexdigest()[:18]
        output = OUTPUTS_DIR / f"openai_{language}_{digest}.mp3"
        if output.exists() and output.stat().st_size > 0:
            return {
                "success": True,
                "engine": self.name,
                "model": model,
                "voice": raw_voice,
                "file": str(output),
                "url": f"/api/downloads/{output.name}",
                "message": "تم تحميل الصوت من الذاكرة المؤقتة.",
            }

        payload = {
            "model": model,
            "input": clean_text,
            "voice": raw_voice,
            "instructions": instruction,
            "response_format": "mp3",
            "speed": max(0.7, min(1.25, float(speed))),
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(240.0, connect=30.0)) as client:
                response = await client.post(
                    "https://api.openai.com/v1/audio/speech",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "Accept": "audio/mpeg",
                    },
                    json=payload,
                )
            if response.status_code >= 400:
                try:
                    detail = (response.json().get("error") or {}).get("message") or response.text[:700]
                except Exception:
                    detail = response.text[:700]
                return {"success": False, "engine": self.name, "status_code": response.status_code, "message": detail}
            output.write_bytes(response.content)
            if output.stat().st_size == 0:
                output.unlink(missing_ok=True)
                raise RuntimeError("لم تُستلم بيانات صوتية.")
            return {
                "success": True,
                "engine": self.name,
                "model": model,
                "voice": raw_voice,
                "profile": tone,
                "file": str(output),
                "url": f"/api/downloads/{output.name}",
                "message": "تم إنشاء الصوت عبر OpenAI.",
            }
        except Exception as exc:
            return {"success": False, "engine": self.name, "message": f"تعذر الاتصال بـ OpenAI: {exc}"}


PLUGIN_CLASS = OpenAITTSPlugin
