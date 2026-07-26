"""Unified, production-oriented text-to-speech engine.

The module keeps expensive models in memory, runs blocking inference outside the
FastAPI event loop, validates requests, and never reports a test tone as a
successful speech generation.
"""
from __future__ import annotations

import asyncio
import hashlib
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.config import GEMINI_API_KEY, GEMINI_TTS_MODEL, OUTPUTS_DIR
from backend.core.logger import get_logger

logger = get_logger("tts_engine")


class TTSEngine:
    """Unified TTS facade with model caching and predictable error handling."""

    MAX_TEXT_LENGTH = 5000
    MIN_SPEED = 0.5
    MAX_SPEED = 2.0

    def __init__(self) -> None:
        self.engines: Dict[str, Dict[str, Any]] = {}
        self._models: Dict[str, Any] = {}
        self._model_lock = threading.Lock()
        self._init_engines()

    def _init_engines(self) -> None:
        definitions = [
            {"name": "kokoro", "label": "Kokoro TTS", "available": self._check_lib("kokoro")},
            {"name": "xtts", "label": "XTTS-v2", "available": self._check_lib("TTS")},
            {"name": "bark", "label": "Bark", "available": self._check_lib("bark")},
            {"name": "gemini", "label": "Google Gemini TTS", "available": bool(GEMINI_API_KEY)},
        ]
        self.engines = {item["name"]: item for item in definitions}

    @staticmethod
    def _check_lib(name: str) -> bool:
        try:
            __import__(name)
            return True
        except Exception:
            return False

    def refresh_engines(self) -> None:
        """Refresh dependency/API-key availability without restarting the app."""
        self._init_engines()

    def list_engines(self) -> List[Dict[str, Any]]:
        return list(self.engines.values())

    def get_engine(self, name: str) -> Optional[Dict[str, Any]]:
        return self.engines.get(name)

    def _validate(self, text: str, speed: float) -> Optional[str]:
        if not text or not text.strip():
            return "Text is required"
        if len(text) > self.MAX_TEXT_LENGTH:
            return f"Text is too long (maximum {self.MAX_TEXT_LENGTH} characters)"
        if not self.MIN_SPEED <= speed <= self.MAX_SPEED:
            return f"Speed must be between {self.MIN_SPEED} and {self.MAX_SPEED}"
        return None

    @staticmethod
    def _result_error(engine: str, message: str) -> Dict[str, Any]:
        return {
            "success": False,
            "engine": engine,
            "file": None,
            "url": None,
            "message": message,
        }

    @staticmethod
    def _filename(prefix: str, text: str, *parts: object) -> str:
        fingerprint = "|".join([text, *(str(part) for part in parts)])
        digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]
        return f"{prefix}_{digest}.wav"

    def _cached_model(self, key: str, factory) -> Any:
        model = self._models.get(key)
        if model is not None:
            return model
        with self._model_lock:
            model = self._models.get(key)
            if model is None:
                logger.info("Loading TTS model: %s", key)
                model = factory()
                self._models[key] = model
        return model

    async def synthesize(
        self,
        text: str,
        engine: str = "auto",
        language: str = "ar",
        voice: str = "default",
        speed: float = 1.0,
        pitch: float = 0.0,
    ) -> Dict[str, Any]:
        error = self._validate(text, speed)
        if error:
            return self._result_error(engine, error)

        text = text.strip()
        language = (language or "ar").strip().lower()
        voice = (voice or "default").strip()

        from backend.core.tts_registry import tts_registry

        if engine == "auto":
            engine = tts_registry.auto_select_engine() or self._best_builtin_engine()

        if not engine:
            return self._result_error(
                "auto",
                "No real TTS engine is installed. Install Kokoro or XTTS-v2, then restart the application.",
            )

        info = self.get_engine(engine)
        if info and not info.get("available"):
            return self._result_error(engine, f"TTS engine '{engine}' is not installed or configured")

        logger.info("TTS request: engine=%s lang=%s chars=%s", engine, language, len(text))

        handlers = {
            "kokoro": self._synth_kokoro,
            "xtts": self._synth_xtts,
            "bark": self._synth_bark,
            "gemini": self._synth_gemini,
        }
        handler = handlers.get(engine)
        if handler is None:
            return self._result_error(engine, f"Unsupported TTS engine: {engine}")

        try:
            return await handler(text, language, voice, speed)
        except Exception as exc:
            logger.exception("%s TTS failed", engine)
            return self._result_error(engine, f"Speech generation failed: {exc}")

    def _best_builtin_engine(self) -> Optional[str]:
        for name in ("kokoro", "xtts", "gemini", "bark"):
            if self.engines.get(name, {}).get("available"):
                return name
        return None

    async def _synth_kokoro(self, text: str, language: str, voice: str, speed: float) -> Dict[str, Any]:
        def generate() -> Path:
            import numpy as np
            import soundfile as sf
            from kokoro import KPipeline

            lang_code = "a" if language.startswith("en") else "a"
            pipeline = self._cached_model(f"kokoro:{lang_code}", lambda: KPipeline(lang_code=lang_code))
            selected_voice = voice if voice != "default" else "af_heart"
            chunks = []
            sample_rate = 24000
            for _graphemes, _phonemes, audio in pipeline(text, voice=selected_voice, speed=speed):
                chunks.append(np.asarray(audio, dtype=np.float32))
            if not chunks:
                raise RuntimeError("Kokoro returned no audio")
            output = OUTPUTS_DIR / self._filename("tts_kokoro", text, language, selected_voice, speed)
            sf.write(str(output), np.concatenate(chunks), sample_rate)
            return output

        filepath = await asyncio.to_thread(generate)
        return self._success("kokoro", filepath, "Generated with Kokoro TTS")

    async def _synth_xtts(self, text: str, language: str, voice: str, speed: float) -> Dict[str, Any]:
        def generate() -> Path:
            from TTS.api import TTS as CoquiTTS

            model = self._cached_model(
                "xtts-v2",
                lambda: CoquiTTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2"),
            )
            output = OUTPUTS_DIR / self._filename("tts_xtts", text, language, voice, speed)
            kwargs: Dict[str, Any] = {
                "text": text,
                "language": language.split("-")[0],
                "file_path": str(output),
            }
            if voice and voice != "default" and Path(voice).is_file():
                kwargs["speaker_wav"] = voice
            elif getattr(model, "speakers", None):
                kwargs["speaker"] = model.speakers[0]
            else:
                raise ValueError("XTTS requires a reference voice file for this model")
            model.tts_to_file(**kwargs)
            return output

        filepath = await asyncio.to_thread(generate)
        return self._success("xtts", filepath, "Generated with XTTS-v2")

    async def _synth_bark(self, text: str, language: str, voice: str, speed: float) -> Dict[str, Any]:
        def generate() -> Path:
            from bark import SAMPLE_RATE, generate_audio, preload_models
            from scipy.io.wavfile import write as write_wav

            self._cached_model("bark", lambda: (preload_models(), True)[1])
            preset = None if voice == "default" else voice
            audio = generate_audio(text, history_prompt=preset)
            output = OUTPUTS_DIR / self._filename("tts_bark", text, language, voice)
            write_wav(str(output), SAMPLE_RATE, audio)
            return output

        filepath = await asyncio.to_thread(generate)
        return self._success("bark", filepath, "Generated with Bark")

    async def _synth_gemini(self, text: str, language: str, voice: str, speed: float) -> Dict[str, Any]:
        if not GEMINI_API_KEY:
            return self._result_error("gemini", "GEMINI_API_KEY is not configured")

        def generate() -> Path:
            import wave
            from google import genai
            from google.genai import types

            client = self._cached_model("gemini-client", lambda: genai.Client(api_key=GEMINI_API_KEY))
            selected_voice = voice if voice != "default" else "Kore"
            response = client.models.generate_content(
                model=GEMINI_TTS_MODEL,
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=selected_voice)
                        )
                    ),
                ),
            )
            parts = response.candidates[0].content.parts if response.candidates else []
            audio_data = next(
                (part.inline_data.data for part in parts if getattr(part, "inline_data", None) and part.inline_data.data),
                None,
            )
            if not audio_data:
                raise RuntimeError("Gemini returned no audio")
            output = OUTPUTS_DIR / self._filename("tts_gemini", text, language, selected_voice)
            with wave.open(str(output), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(24000)
                wav_file.writeframes(audio_data)
            return output

        filepath = await asyncio.to_thread(generate)
        return self._success("gemini", filepath, "Generated with Google Gemini TTS")

    async def clone_voice(
        self,
        reference_audio_path: str,
        text: str,
        engine: str = "xtts",
        language: str = "ar",
    ) -> Dict[str, Any]:
        error = self._validate(text, 1.0)
        if error:
            return self._result_error(engine, error)

        reference = Path(reference_audio_path).expanduser().resolve()
        if not reference.is_file():
            return self._result_error(engine, "Reference audio file was not found")
        if engine != "xtts" or not self._check_lib("TTS"):
            return self._result_error(engine, "Voice cloning requires XTTS-v2 (pip install TTS)")

        def generate() -> Path:
            from TTS.api import TTS as CoquiTTS

            model = self._cached_model(
                "xtts-v2",
                lambda: CoquiTTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2"),
            )
            output = OUTPUTS_DIR / self._filename("clone_xtts", text, reference, language)
            model.tts_to_file(
                text=text.strip(),
                language=language.split("-")[0],
                speaker_wav=str(reference),
                file_path=str(output),
            )
            return output

        try:
            filepath = await asyncio.to_thread(generate)
            return self._success("xtts", filepath, "Voice cloned with XTTS-v2")
        except Exception as exc:
            logger.exception("Voice cloning failed")
            return self._result_error(engine, f"Voice cloning failed: {exc}")

    @staticmethod
    def _success(engine: str, filepath: Path, message: str) -> Dict[str, Any]:
        return {
            "success": True,
            "engine": engine,
            "file": str(filepath),
            "url": f"/api/downloads/{filepath.name}",
            "message": message,
        }


tts = TTSEngine()
