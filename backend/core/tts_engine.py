"""محرك TTS - واجهة موحدة لجميع محركات الصوت"""
import os
import asyncio
import hashlib
from typing import Optional, Dict, List, Any
from backend.core.config import (
    GEMINI_API_KEY, GEMINI_TTS_MODEL, IS_TERMUX,
    OUTPUTS_DIR, VOICES_DIR, CACHE_DIR, ENGINE_PRIORITY
)
from backend.core.logger import get_logger
from backend.core.audio_utils import generate_sine_wave, save_audio

logger = get_logger("tts_engine")


class TTSEngine:
    """محرك صوت موحد - يدعم محركات متعددة مع fallback"""

    def __init__(self):
        self.engines: Dict[str, Dict] = {}
        self._init_engines()

    def _init_engines(self):
        engine_defs = [
            {"name": "kokoro", "label": "Kokoro TTS", "available": self._check_lib("kokoro")},
            {"name": "piper", "label": "Piper TTS", "available": self._check_lib("piper_tts")},
            {"name": "xtts", "label": "XTTS-v2", "available": self._check_lib("TTS")},
            {"name": "bark", "label": "Bark", "available": self._check_lib("bark")},
            {"name": "melotts", "label": "MeloTTS", "available": self._check_lib("melotts")},
            {"name": "gemini", "label": "Google Gemini TTS", "available": bool(GEMINI_API_KEY)},
            {"name": "fallback", "label": "Fallback (tone)", "available": True},
        ]
        for e in engine_defs:
            self.engines[e["name"]] = e

    @staticmethod
    def _check_lib(name: str) -> bool:
        try:
            __import__(name)
            return True
        except ImportError:
            return False
        except Exception:
            return False

    def list_engines(self) -> List[Dict]:
        return list(self.engines.values())

    def get_engine(self, name: str) -> Optional[Dict]:
        return self.engines.get(name)

    async def synthesize(
        self,
        text: str,
        engine: str = "kokoro",
        language: str = "ar",
        voice: str = "default",
        speed: float = 1.0,
        pitch: float = 0.0,
    ) -> Dict[str, Any]:
        logger.info(f"TTS request: engine={engine}, lang={language}, text_len={len(text)}")

        if not text.strip():
            return {"success": False, "engine": engine, "message": "Text is empty", "file": None, "url": None}

        if engine == "fallback":
            return await self._synth_fallback(text, language, voice, speed)

        if engine == "gemini" and GEMINI_API_KEY:
            return await self._synth_gemini(text, language, voice, speed)

        if engine == "kokoro" and self._check_lib("kokoro"):
            return await self._synth_kokoro(text, language, voice, speed)

        if engine == "xtts" and self._check_lib("TTS"):
            return await self._synth_xtts(text, language, voice, speed)

        if engine == "bark" and self._check_lib("bark"):
            return await self._synth_bark(text, language, voice, speed)

        logger.warning(f"Engine '{engine}' not available, using fallback")
        return await self._synth_fallback(text, language, voice, speed)

    async def _synth_fallback(self, text: str, language: str, voice: str, speed: float) -> Dict:
        await asyncio.sleep(0.01)
        duration = min(max(len(text) * 0.05, 0.5), 10.0)
        audio_data = generate_sine_wave(frequency=440.0, duration=duration)
        name_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        filename = f"tts_fallback_{name_hash}.wav"
        filepath = save_audio(audio_data, filename)
        return {
            "success": True,
            "engine": "fallback",
            "file": str(filepath),
            "url": f"/api/downloads/{filepath.name}",
            "message": "Generated with fallback engine (test tone). Install kokoro or TTS for real speech.",
        }

    async def _synth_kokoro(self, text: str, language: str, voice: str, speed: float) -> Dict:
        try:
            from kokoro import Kokoro
            model = Kokoro()
            audio = model.create(text, voice=voice, speed=speed)
            name_hash = hashlib.md5(text.encode()).hexdigest()[:8]
            filename = f"tts_kokoro_{name_hash}.wav"
            if hasattr(audio, "tobytes"):
                import soundfile as sf
                filepath = OUTPUTS_DIR / filename
                sf.write(str(filepath), audio, 24000)
            else:
                filepath = save_audio(audio, filename)
            return {
                "success": True, "engine": "kokoro",
                "file": str(filepath),
                "url": f"/api/downloads/{filepath.name}",
                "message": "Generated with Kokoro TTS",
            }
        except Exception as e:
            logger.error(f"Kokoro TTS failed: {e}")
            return await self._synth_fallback(text, language, voice, speed)

    async def _synth_xtts(self, text: str, language: str, voice: str, speed: float) -> Dict:
        try:
            from TTS.api import TTS as CoquiTTS
            model = CoquiTTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2")
            name_hash = hashlib.md5(text.encode()).hexdigest()[:8]
            filename = f"tts_xtts_{name_hash}.wav"
            filepath = OUTPUTS_DIR / filename
            model.tts_to_file(text=text, language=language, file_path=str(filepath))
            return {
                "success": True, "engine": "xtts",
                "file": str(filepath),
                "url": f"/api/downloads/{filepath.name}",
                "message": "Generated with XTTS-v2",
            }
        except Exception as e:
            logger.error(f"XTTS failed: {e}")
            return await self._synth_fallback(text, language, voice, speed)

    async def _synth_bark(self, text: str, language: str, voice: str, speed: float) -> Dict:
        try:
            from bark import generate_audio
            from scipy.io.wavfile import write as write_wav
            audio = generate_audio(text)
            name_hash = hashlib.md5(text.encode()).hexdigest()[:8]
            filename = f"tts_bark_{name_hash}.wav"
            filepath = OUTPUTS_DIR / filename
            write_wav(str(filepath), 24000, audio)
            return {
                "success": True, "engine": "bark",
                "file": str(filepath),
                "url": f"/api/downloads/{filepath.name}",
                "message": "Generated with Bark",
            }
        except Exception as e:
            logger.error(f"Bark failed: {e}")
            return await self._synth_fallback(text, language, voice, speed)

    async def _synth_gemini(self, text: str, language: str, voice: str, speed: float) -> Dict:
        try:
            from google import genai
            from google.genai.types import GenerateContentConfig

            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model=GEMINI_TTS_MODEL,
                contents=text,
                config=GenerateContentConfig(
                    response_modalities=["AUDIO"],
                ),
            )
            audio_data = None
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.data:
                    audio_data = part.inline_data.data
                    break
            if not audio_data:
                raise ValueError("No audio data in Gemini response")

            name_hash = hashlib.md5(text.encode()).hexdigest()[:8]
            filename = f"tts_gemini_{name_hash}.wav"
            filepath = save_audio(audio_data, filename)
            return {
                "success": True, "engine": "gemini",
                "file": str(filepath),
                "url": f"/api/downloads/{filepath.name}",
                "message": "Generated with Google Gemini TTS",
            }
        except Exception as e:
            logger.error(f"Gemini TTS failed: {e}")
            return await self._synth_fallback(text, language, voice, speed)

    async def clone_voice(
        self, reference_audio_path: str, text: str, engine: str = "xtts"
    ) -> Dict[str, Any]:
        logger.info(f"Voice clone: engine={engine}, ref={reference_audio_path}")
        try:
            if engine == "xtts" and self._check_lib("TTS"):
                from TTS.api import TTS as CoquiTTS
                model = CoquiTTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2")
                name_hash = hashlib.md5(text.encode()).hexdigest()[:8]
                filename = f"clone_xtts_{name_hash}.wav"
                filepath = OUTPUTS_DIR / filename
                model.tts_to_file(
                    text=text,
                    language="ar",
                    file_path=str(filepath),
                    speaker_wav=reference_audio_path,
                )
                return {
                    "success": True, "engine": "xtts",
                    "file": str(filepath),
                    "url": f"/api/downloads/{filepath.name}",
                    "message": "Voice cloned with XTTS-v2",
                }
            else:
                return {
                    "success": False, "engine": engine,
                    "file": None, "url": None,
                    "message": f"Engine {engine} not available. Install TTS: pip install TTS",
                }
        except Exception as e:
            logger.error(f"Voice clone failed: {e}")
            return {
                "success": False, "engine": engine,
                "file": None, "url": None,
                "message": f"Voice clone failed: {e}",
            }


tts = TTSEngine()
