"""Professional unified TTS engine with safe validation and graceful fallbacks."""
from __future__ import annotations

import asyncio
import hashlib
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.config import GEMINI_API_KEY, GEMINI_TTS_MODEL, OUTPUTS_DIR, UPLOADS_DIR
from backend.core.logger import get_logger

logger = get_logger("tts_engine")

MAX_TEXT_LENGTH = 5000
SUPPORTED_LANGUAGES = {"ar", "en", "fr", "de", "es", "it", "tr"}
DEFAULT_EDGE_VOICES = {
    "ar": "ar-SA-HamedNeural",
    "en": "en-US-GuyNeural",
    "fr": "fr-FR-HenriNeural",
    "de": "de-DE-ConradNeural",
    "es": "es-ES-AlvaroNeural",
    "it": "it-IT-DiegoNeural",
    "tr": "tr-TR-AhmetNeural",
}


class TTSEngine:
    """Unified asynchronous TTS service.

    Heavy local models are loaded once and blocking inference is moved to a
    worker thread so FastAPI's event loop remains responsive.
    """

    def __init__(self) -> None:
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        self.engines: Dict[str, Dict[str, Any]] = {}
        self._init_engines()

    def _init_engines(self) -> None:
        definitions = [
            {
                "name": "edge",
                "label": "Microsoft Edge Neural TTS",
                "available": self._check_lib("edge_tts"),
                "quality": "high",
                "requires_internet": True,
            },
            {
                "name": "xtts",
                "label": "Coqui XTTS-v2",
                "available": self._check_lib("TTS"),
                "quality": "high",
                "requires_internet": False,
            },
            {
                "name": "kokoro",
                "label": "Kokoro TTS",
                "available": self._check_lib("kokoro"),
                "quality": "high",
                "requires_internet": False,
            },
            {
                "name": "bark",
                "label": "Bark",
                "available": self._check_lib("bark"),
                "quality": "experimental",
                "requires_internet": False,
            },
            {
                "name": "gemini",
                "label": "Google Gemini TTS",
                "available": bool(GEMINI_API_KEY) and self._check_lib("google.genai"),
                "quality": "high",
                "requires_internet": True,
            },
        ]
        self.engines = {item["name"]: item for item in definitions}

    @staticmethod
    def _check_lib(name: str) -> bool:
        try:
            __import__(name)
            return True
        except Exception:
            return False

    def list_engines(self) -> List[Dict[str, Any]]:
        return list(self.engines.values())

    def get_engine(self, name: str) -> Optional[Dict[str, Any]]:
        return self.engines.get(name)

    def _validate(
        self, text: str, language: str, speed: float, pitch: float
    ) -> Optional[str]:
        if not text or not text.strip():
            return "النص فارغ."
        if len(text) > MAX_TEXT_LENGTH:
            return f"النص طويل جدًا. الحد الأقصى {MAX_TEXT_LENGTH} حرف."
        if language not in SUPPORTED_LANGUAGES:
            return f"اللغة غير مدعومة: {language}"
        if not 0.5 <= speed <= 2.0:
            return "السرعة يجب أن تكون بين 0.5 و2.0."
        if not -50.0 <= pitch <= 50.0:
            return "طبقة الصوت يجب أن تكون بين -50 و50."
        return None

    def _output_path(
        self, engine: str, text: str, language: str, voice: str, speed: float, ext: str
    ) -> Path:
        key = f"{engine}|{language}|{voice}|{speed:.2f}|{text}".encode("utf-8")
        digest = hashlib.sha256(key).hexdigest()[:16]
        safe_engine = re.sub(r"[^a-z0-9_-]", "", engine.lower()) or "tts"
        return OUTPUTS_DIR / f"{safe_engine}_{digest}.{ext}"

    @staticmethod
    def _result(path: Path, engine: str, message: str) -> Dict[str, Any]:
        return {
            "success": True,
            "engine": engine,
            "file": str(path),
            "url": f"/api/downloads/{path.name}",
            "message": message,
        }

    @staticmethod
    def _failure(engine: str, message: str) -> Dict[str, Any]:
        return {
            "success": False,
            "engine": engine,
            "file": None,
            "url": None,
            "message": message,
        }

    def _auto_select(self) -> Optional[str]:
        for name in ("edge", "gemini", "xtts", "kokoro", "bark"):
            if self.engines.get(name, {}).get("available"):
                return name
        return None

    async def synthesize(
        self,
        text: str,
        engine: str = "auto",
        language: str = "ar",
        voice: str = "default",
        speed: float = 1.0,
        pitch: float = 0.0,
    ) -> Dict[str, Any]:
        text = text.strip()
        error = self._validate(text, language, speed, pitch)
        if error:
            return self._failure(engine, error)

        selected = self._auto_select() if engine == "auto" else engine
        if not selected:
            return self._failure(
                "none",
                "لا يوجد محرك صوت حقيقي مثبت. ثبّت edge-tts أو أحد المحركات المحلية.",
            )

        info = self.engines.get(selected)
        if not info:
            return self._failure(selected, f"محرك غير معروف: {selected}")
        if not info["available"]:
            return self._failure(selected, f"المحرك {selected} غير مثبت أو غير مهيأ.")

        logger.info(
            "TTS request engine=%s lang=%s chars=%s", selected, language, len(text)
        )

        try:
            if selected == "edge":
                return await self._synth_edge(text, language, voice, speed, pitch)
            if selected == "xtts":
                return await self._synth_xtts(text, language, voice, speed)
            if selected == "kokoro":
                return await self._synth_kokoro(text, language, voice, speed)
            if selected == "bark":
                return await self._synth_bark(text, language, voice, speed)
            if selected == "gemini":
                return await self._synth_gemini(text, language, voice, speed)
        except Exception as exc:
            logger.exception("TTS engine %s failed", selected)
            if engine == "auto":
                for fallback in ("edge", "gemini", "xtts", "kokoro", "bark"):
                    if fallback == selected or not self.engines.get(fallback, {}).get("available"):
                        continue
                    try:
                        return await self.synthesize(
                            text, fallback, language, voice, speed, pitch
                        )
                    except Exception:
                        logger.exception("Fallback engine %s failed", fallback)
            return self._failure(selected, f"فشل إنشاء الصوت: {exc}")

        return self._failure(selected, "المحرك المحدد غير منفذ.")

    async def _synth_edge(
        self, text: str, language: str, voice: str, speed: float, pitch: float
    ) -> Dict[str, Any]:
        import edge_tts

        selected_voice = (
            DEFAULT_EDGE_VOICES.get(language, DEFAULT_EDGE_VOICES["ar"])
            if voice in {"", "default", None}
            else voice
        )
        rate = round((speed - 1.0) * 100)
        pitch_hz = round(pitch)
        path = self._output_path("edge", text, language, selected_voice, speed, "mp3")
        if not path.exists():
            communicate = edge_tts.Communicate(
                text=text,
                voice=selected_voice,
                rate=f"{rate:+d}%",
                pitch=f"{pitch_hz:+d}Hz",
            )
            await communicate.save(str(path))
        return self._result(path, "edge", "تم إنشاء صوت عصبي احترافي.")

    @staticmethod
    @lru_cache(maxsize=1)
    def _xtts_model():
        from TTS.api import TTS as CoquiTTS

        return CoquiTTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2")

    async def _synth_xtts(
        self, text: str, language: str, voice: str, speed: float
    ) -> Dict[str, Any]:
        path = self._output_path("xtts", text, language, voice, speed, "wav")
        if not path.exists():
            model = await asyncio.to_thread(self._xtts_model)
            kwargs: Dict[str, Any] = {
                "text": text,
                "language": language,
                "file_path": str(path),
                "speed": speed,
            }
            if voice not in {"", "default"} and Path(voice).exists():
                kwargs["speaker_wav"] = voice
            await asyncio.to_thread(model.tts_to_file, **kwargs)
        return self._result(path, "xtts", "تم إنشاء الصوت باستخدام XTTS-v2.")

    async def _synth_kokoro(
        self, text: str, language: str, voice: str, speed: float
    ) -> Dict[str, Any]:
        def generate() -> Path:
            from kokoro import Kokoro
            import soundfile as sf

            selected_voice = "af_heart" if voice in {"", "default"} else voice
            model = Kokoro()
            audio = model.create(text, voice=selected_voice, speed=speed)
            path = self._output_path("kokoro", text, language, selected_voice, speed, "wav")
            sf.write(str(path), audio, 24000)
            return path

        path = await asyncio.to_thread(generate)
        return self._result(path, "kokoro", "تم إنشاء الصوت باستخدام Kokoro.")

    async def _synth_bark(
        self, text: str, language: str, voice: str, speed: float
    ) -> Dict[str, Any]:
        def generate() -> Path:
            from bark import generate_audio
            from scipy.io.wavfile import write as write_wav

            path = self._output_path("bark", text, language, voice, speed, "wav")
            write_wav(str(path), 24000, generate_audio(text))
            return path

        path = await asyncio.to_thread(generate)
        return self._result(path, "bark", "تم إنشاء الصوت باستخدام Bark.")

    async def _synth_gemini(
        self, text: str, language: str, voice: str, speed: float
    ) -> Dict[str, Any]:
        from google import genai
        from google.genai.types import GenerateContentConfig

        def generate() -> bytes:
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model=GEMINI_TTS_MODEL,
                contents=text,
                config=GenerateContentConfig(response_modalities=["AUDIO"]),
            )
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.data:
                    return part.inline_data.data
            raise ValueError("لم تُرجع الخدمة بيانات صوتية.")

        audio_data = await asyncio.to_thread(generate)
        path = self._output_path("gemini", text, language, voice, speed, "wav")
        path.write_bytes(audio_data)
        return self._result(path, "gemini", "تم إنشاء الصوت باستخدام Gemini.")

    async def clone_voice(
        self,
        reference_audio_path: str,
        text: str,
        engine: str = "xtts",
        language: str = "ar",
    ) -> Dict[str, Any]:
        reference = Path(reference_audio_path).resolve()
        uploads_root = UPLOADS_DIR.resolve()
        if not reference.exists() or not reference.is_file():
            return self._failure(engine, "ملف الصوت المرجعي غير موجود.")
        if uploads_root not in reference.parents:
            return self._failure(engine, "يجب استخدام ملف مرفوع داخل مجلد uploads.")
        if engine != "xtts" or not self.engines["xtts"]["available"]:
            return self._failure(engine, "استنساخ الصوت يتطلب XTTS-v2.")
        if not text.strip() or len(text) > MAX_TEXT_LENGTH:
            return self._failure(engine, "النص فارغ أو أطول من الحد المسموح.")

        path = self._output_path("clone_xtts", text, language, reference.name, 1.0, "wav")
        try:
            model = await asyncio.to_thread(self._xtts_model)
            await asyncio.to_thread(
                model.tts_to_file,
                text=text.strip(),
                language=language,
                file_path=str(path),
                speaker_wav=str(reference),
            )
            return self._result(path, "xtts", "تم استنساخ الصوت باستخدام XTTS-v2.")
        except Exception as exc:
            logger.exception("Voice cloning failed")
            return self._failure(engine, f"فشل استنساخ الصوت: {exc}")


tts = TTSEngine()
