"""Piper TTS plugin with automatic Arabic model setup and cached inference."""
from __future__ import annotations

import asyncio
import hashlib
import importlib
import shutil
import subprocess
import sys
import urllib.request
import wave
from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar

from backend.core.config import OUTPUTS_DIR
from backend.core.logger import get_logger
from backend.plugins.tts_plugin_base import TTSPluginBase

logger = get_logger("plugin_piper")


class PiperPlugin(TTSPluginBase):
    name = "piper"
    label = "Piper TTS"
    description = "صوت عصبي محلي مجاني يعمل بلا مفتاح API بعد تنزيل النموذج مرة واحدة"
    homepage = "https://github.com/OHF-Voice/piper1-gpl"
    is_open_source = True
    requires_gpu = False

    PIPER_MODELS: ClassVar[dict[str, dict[str, str]]] = {
        "ar_JO-kareem-low": {
            "url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/ar/ar_JO/kareem/low/ar_JO-kareem-low.onnx",
            "config_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/ar/ar_JO/kareem/low/ar_JO-kareem-low.onnx.json",
            "language": "ar",
            "speaker": "kareem",
            "quality": "low",
        },
        "ar_JO-kareem-medium": {
            "url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/ar/ar_JO/kareem/medium/ar_JO-kareem-medium.onnx",
            "config_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/ar/ar_JO/kareem/medium/ar_JO-kareem-medium.onnx.json",
            "language": "ar",
            "speaker": "kareem",
            "quality": "medium",
        },
        "en_US-lessac-medium": {
            "url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
            "config_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
            "language": "en",
            "speaker": "lessac",
            "quality": "medium",
        },
    }

    def check(self) -> bool:
        try:
            importlib.import_module("piper")
        except (ImportError, OSError):
            return False
        return True

    def install(self) -> dict[str, Any]:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "piper-tts>=1.6,<2"])
            installed = self.check()
            return {
                "success": installed,
                "engine": self.name,
                "message": "تم تثبيت Piper بنجاح." if installed else "تعذر تثبيت Piper.",
            }
        except (OSError, subprocess.CalledProcessError) as e:
            return {"success": False, "engine": self.name, "message": str(e)}

    def download_models(self, model_name: str = "ar_JO-kareem-medium") -> dict[str, Any]:
        if model_name == "default":
            model_name = "ar_JO-kareem-medium"
        if model_name not in self.PIPER_MODELS:
            return {
                "success": False,
                "message": f"نموذج Piper غير معروف: {model_name}",
            }
        meta = self.PIPER_MODELS[model_name]
        model_path = self.models_dir / f"{model_name}.onnx"
        config_path = self.models_dir / f"{model_name}.onnx.json"

        try:
            logger.info(f"Downloading Piper model: {model_name}")
            for url, target in (
                (meta["url"], model_path),
                (meta["config_url"], config_path),
            ):
                if target.exists() and target.stat().st_size > 100:
                    continue
                temp = target.with_suffix(target.suffix + ".part")
                temp.unlink(missing_ok=True)
                request = urllib.request.Request(url, headers={"User-Agent": "IbnWaqadiStudio/6.0"})
                with urllib.request.urlopen(request, timeout=180) as response, temp.open("wb") as output:
                    shutil.copyfileobj(response, output)
                if temp.stat().st_size <= 100:
                    raise RuntimeError(f"الملف المحمل غير صالح: {target.name}")
                temp.replace(target)
            return {
                "success": True,
                "model": model_name,
                "path": str(model_path),
                "config": str(config_path),
                "message": "تم تجهيز نموذج Piper العربي المحلي.",
            }
        except (OSError, RuntimeError) as e:
            model_path.with_suffix(model_path.suffix + ".part").unlink(missing_ok=True)
            config_path.with_suffix(config_path.suffix + ".part").unlink(missing_ok=True)
            return {"success": False, "model": model_name, "message": str(e)}

    def list_models(self) -> list[dict[str, Any]]:
        available: list[dict[str, Any]] = []
        for name, meta in self.PIPER_MODELS.items():
            model_path = self.models_dir / f"{name}.onnx"
            config_path = self.models_dir / f"{name}.onnx.json"
            downloaded = (
                model_path.exists()
                and model_path.stat().st_size > 100
                and config_path.exists()
                and config_path.stat().st_size > 100
            )
            available.append({
                "name": name,
                "language": meta["language"],
                "speaker": meta["speaker"],
                "quality": meta["quality"],
                "downloaded": downloaded,
                "path": str(model_path) if downloaded else None,
            })
        return available

    def list_voices(self) -> list[dict[str, Any]]:
        voices: list[dict[str, Any]] = []
        for model in self.list_models():
            if model["downloaded"]:
                voices.append({
                    "name": model["speaker"],
                    "model": model["name"],
                    "language": model["language"],
                })
        return voices

    @staticmethod
    @lru_cache(maxsize=4)
    def _load_voice(model_path: str, config_path: str):
        from piper import PiperVoice

        return PiperVoice.load(model_path, config_path=config_path)

    async def generate(
        self,
        text: str,
        voice: str = "kareem",
        language: str = "ar",
        speed: float = 1.0,
    ) -> dict[str, Any]:
        if not self.check():
            return {
                "success": False,
                "engine": self.name,
                "message": "محرك Piper المحلي غير مثبت داخل البرنامج.",
            }
        text = (text or "").strip()
        if not text:
            return {"success": False, "engine": self.name, "message": "النص فارغ."}
        if len(text) > 8000:
            return {"success": False, "engine": self.name, "message": "النص أطول من 8000 حرف."}
        if not 0.5 <= speed <= 2.0:
            return {"success": False, "engine": self.name, "message": "السرعة يجب أن تكون بين 0.5 و2.0."}
        language = (language or "ar").split("-", 1)[0].lower()

        models = self.list_models()
        downloaded = [m for m in models if m["downloaded"] and m["language"] == language]
        if not downloaded:
            model_name = "ar_JO-kareem-medium" if language == "ar" else "en_US-lessac-medium"
            setup = await asyncio.to_thread(self.download_models, model_name)
            if not setup.get("success"):
                return {
                    "success": False,
                    "engine": self.name,
                    "message": f"تعذر تجهيز نموذج Piper المحلي: {setup.get('message', 'خطأ غير معروف')}",
                }
            models = self.list_models()
            downloaded = [m for m in models if m["downloaded"] and m["language"] == language]
        if not downloaded:
            return {"success": False, "engine": self.name, "message": f"لا يوجد نموذج Piper للغة {language}."}
        model = downloaded[0]

        try:
            def render() -> Path:
                from piper.config import SynthesisConfig

                model_path = Path(model["path"])
                config_path = model_path.with_suffix(".onnx.json")
                digest = hashlib.sha256(
                    f"piper-v160|{model_path.name}|{speed:.3f}|{text}".encode()
                ).hexdigest()[:18]
                filepath = OUTPUTS_DIR / f"piper_{digest}.wav"
                if filepath.exists() and filepath.stat().st_size > 44:
                    return filepath
                voice_obj = self._load_voice(str(model_path), str(config_path))
                synthesis = SynthesisConfig(length_scale=1.0 / speed, normalize_audio=True)
                with wave.open(str(filepath), "wb") as wav_file:
                    voice_obj.synthesize_wav(text, wav_file, syn_config=synthesis)
                if filepath.stat().st_size <= 44:
                    filepath.unlink(missing_ok=True)
                    raise RuntimeError("لم يُنشئ Piper بيانات صوتية.")
                return filepath

            filepath = await asyncio.to_thread(render)

            return {
                "success": True,
                "engine": self.name,
                "file": str(filepath),
                "url": f"/api/downloads/{filepath.name}",
                "message": f"تم إنشاء الصوت محليًا باستخدام Piper ({model['name']}).",
            }
        except Exception as e:
            logger.exception("Piper generation failed")
            return {"success": False, "engine": self.name, "message": f"فشل Piper المحلي: {e}"}


PLUGIN_CLASS = PiperPlugin
PLUGIN_NAME = "Piper TTS"
PLUGIN_DESCRIPTION = "صوت عصبي محلي مجاني يعمل على المعالج"
