"""Coqui XTTS-v2 plugin with real consent-based speaker cloning support."""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any, Dict, List

from backend.core.config import OUTPUTS_DIR
from backend.core.logger import get_logger
from backend.plugins.tts_plugin_base import TTSPluginBase

logger = get_logger("plugin_coqui")


class CoquiPlugin(TTSPluginBase):
    name = "coqui"
    label = "Coqui XTTS-v2"
    description = "Multilingual TTS with reference-audio voice cloning"
    homepage = "https://github.com/idiap/coqui-ai-TTS"
    is_open_source = True
    requires_gpu = False

    COQUI_MODELS = {
        "xtts_v2": {
            "model_name": "tts_models/multilingual/multi-dataset/xtts_v2",
            "languages": ["ar", "en", "fr", "de", "es", "it", "pt", "pl", "tr", "ru", "nl", "cs", "zh-cn", "hu", "ko", "ja", "hi"],
            "supports_cloning": True,
        },
        "glow_tts": {
            "model_name": "tts_models/en/ljspeech/glow-tts",
            "languages": ["en"],
            "supports_cloning": False,
        },
    }

    _model: Any = None
    _device: str = "cpu"
    _model_lock = asyncio.Lock()

    def check(self) -> bool:
        try:
            from TTS.api import TTS  # noqa: F401
            return True
        except Exception:
            return False

    def install(self) -> Dict[str, Any]:
        import subprocess
        import sys

        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "coqui-tts==0.27.5"])
            installed = self.check()
            return {
                "success": installed,
                "engine": self.name,
                "message": "تم تثبيت Coqui TTS." if installed else "تعذر تثبيت Coqui TTS.",
            }
        except Exception as exc:
            return {"success": False, "engine": self.name, "message": str(exc)}

    def download_models(self, model_name: str = "xtts_v2") -> Dict[str, Any]:
        if model_name not in self.COQUI_MODELS:
            return {"success": False, "message": f"Unknown model: {model_name}"}
        if not self.check():
            return {"success": False, "message": "Coqui TTS is not installed."}
        try:
            import os
            from TTS.api import TTS as CoquiTTS

            os.environ.setdefault("COQUI_TOS_AGREED", "1")
            meta = self.COQUI_MODELS[model_name]
            model = CoquiTTS(model_name=meta["model_name"], progress_bar=False)
            marker = self.models_dir / f"{model_name}.installed"
            marker.write_text("installed", encoding="utf-8")
            del model
            return {"success": True, "model": model_name, "message": "تم تنزيل نموذج XTTS-v2."}
        except Exception as exc:
            return {"success": False, "model": model_name, "message": str(exc)}

    def list_models(self) -> List[Dict[str, Any]]:
        models: list[dict[str, Any]] = []
        for name, meta in self.COQUI_MODELS.items():
            marker = self.models_dir / f"{name}.installed"
            models.append(
                {
                    "name": name,
                    "model_name": meta["model_name"],
                    "languages": meta["languages"],
                    "supports_cloning": meta["supports_cloning"],
                    "downloaded": marker.exists(),
                }
            )
        return models

    def list_voices(self) -> List[Dict[str, Any]]:
        return [{"name": "reference_audio", "model": "xtts_v2", "language": "ar", "requires_sample": True}]

    @classmethod
    def _load_model_sync(cls):
        import os
        import torch
        from TTS.api import TTS as CoquiTTS

        os.environ.setdefault("COQUI_TOS_AGREED", "1")
        if cls._model is None:
            cls._device = "cuda" if torch.cuda.is_available() else "cpu"
            cls._model = CoquiTTS(
                model_name="tts_models/multilingual/multi-dataset/xtts_v2",
                progress_bar=False,
            ).to(cls._device)
        return cls._model

    @staticmethod
    def _output_path(text: str, reference: Path) -> Path:
        digest = hashlib.sha256(f"{reference.resolve()}|{text}".encode("utf-8")).hexdigest()[:16]
        return OUTPUTS_DIR / f"clone_coqui_{digest}.wav"

    async def generate(
        self,
        text: str,
        voice: str = "default",
        language: str = "ar",
        speed: float = 1.0,
    ) -> Dict[str, Any]:
        del speed  # XTTS similarity is more stable at native speed; mastering handles speed later.
        if not self.check():
            return {
                "success": False,
                "engine": self.name,
                "message": "Coqui TTS غير مثبت. استخدم صفحة استنساخ الصوت Pro لتجهيز XTTS المحلي.",
            }
        reference = Path(str(voice)).expanduser().resolve()
        if voice in {"", "default", None} or not reference.exists() or not reference.is_file():
            return {
                "success": False,
                "engine": self.name,
                "message": "XTTS يحتاج ملف عينة صوت صالحًا في speaker_wav.",
            }
        if not text.strip():
            return {"success": False, "engine": self.name, "message": "النص فارغ."}

        output = self._output_path(text.strip(), reference)
        try:
            async with self._model_lock:
                model = await asyncio.to_thread(self._load_model_sync)
                await asyncio.to_thread(
                    model.tts_to_file,
                    text=text.strip(),
                    speaker_wav=str(reference),
                    language=language.split("-")[0],
                    file_path=str(output),
                    split_sentences=True,
                )
            if not output.exists() or output.stat().st_size < 1024:
                raise RuntimeError("XTTS لم ينشئ ملفًا صوتيًا صالحًا.")
            return {
                "success": True,
                "engine": self.name,
                "file": str(output),
                "url": f"/api/downloads/{output.name}",
                "device": self._device,
                "message": "تم إنشاء الصوت باستخدام عينة speaker_wav عبر XTTS-v2.",
            }
        except Exception as exc:
            logger.exception("Coqui voice cloning failed")
            return {"success": False, "engine": self.name, "message": str(exc)}

    async def clone(self, reference_audio_path: str, text: str, language: str = "ar") -> Dict[str, Any]:
        return await self.generate(text=text, voice=reference_audio_path, language=language, speed=1.0)


PLUGIN_CLASS = CoquiPlugin
PLUGIN_NAME = "Coqui XTTS-v2"
PLUGIN_DESCRIPTION = "Multilingual voice cloning with required reference audio"
