"""Enhanced TTS Engine - Streaming, Batch, GPU/CPU Auto-Detection"""
import os
import asyncio
import hashlib
from typing import Optional, Dict, List, Any, AsyncGenerator
from pathlib import Path

from backend.core.config import settings, GPUConfig
from backend.core.logger import get_logger
from backend.core.audio_utils import generate_sine_wave, save_audio

logger = get_logger("tts_engine")


class TTSEngine:
    """Enhanced TTS engine with streaming, batch, and GPU support"""

    def __init__(self):
        self.engines: Dict[str, Dict] = {}
        self._init_engines()
        self.device = GPUConfig.get_device()
        logger.info(f"TTS Engine initialized - device: {self.device}")

    def _init_engines(self):
        engine_defs = [
            {"name": "kokoro", "label": "Kokoro TTS", "available": self._check_lib("kokoro"), "streaming": False, "gpu": False},
            {"name": "piper", "label": "Piper TTS", "available": self._check_lib("piper") or self._check_lib("piper_tts"), "streaming": True, "gpu": False},
            {"name": "xtts", "label": "XTTS-v2", "available": self._check_lib("TTS"), "streaming": False, "gpu": True},
            {"name": "bark", "label": "Bark", "available": self._check_lib("bark"), "streaming": False, "gpu": True},
            {"name": "melotts", "label": "MeloTTS", "available": self._check_lib("melo") or self._check_lib("melotts"), "streaming": False, "gpu": False},
            {"name": "f5", "label": "F5-TTS", "available": self._check_lib("f5_tts"), "streaming": False, "gpu": True},
            {"name": "fish", "label": "Fish Speech", "available": self._check_lib("fish_speech"), "streaming": True, "gpu": True},
            {"name": "gemini", "label": "Google Gemini TTS", "available": bool(settings.GEMINI_API_KEY), "streaming": False, "gpu": False},
            {"name": "cosyvoice", "label": "CosyVoice", "available": self._check_lib("cosyvoice"), "streaming": False, "gpu": True},
            {"name": "parler", "label": "Parler TTS", "available": self._check_lib("parler_tts"), "streaming": False, "gpu": True},
            {"name": "openvoice", "label": "OpenVoice", "available": self._check_lib("openvoice"), "streaming": False, "gpu": True},
            {"name": "whisper", "label": "Whisper (STT)", "available": self._check_lib("whisper") or self._check_lib("faster_whisper"), "streaming": False, "gpu": True},
            {"name": "fallback", "label": "Fallback (tone)", "available": True, "streaming": False, "gpu": False},
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

    def list_engines(self) -> List[Dict]:
        return list(self.engines.values())

    def get_engine(self, name: str) -> Optional[Dict]:
        return self.engines.get(name)

    def is_available(self, engine: str) -> bool:
        eng = self.engines.get(engine)
        return eng["available"] if eng else False

    async def synthesize(self, text: str, engine: str = "kokoro",
                         language: str = "ar", voice: str = "default",
                         speed: float = 1.0, pitch: float = 0.0) -> Dict[str, Any]:
        """Synthesize speech from text"""
        logger.info(f"TTS request: engine={engine}, lang={language}, text_len={len(text)}")

        if not text.strip():
            return {"success": False, "engine": engine, "message": "Text is empty"}

        if engine == "fallback":
            return await self._synth_fallback(text, language, voice, speed)

        if engine == "gemini" and settings.GEMINI_API_KEY:
            return await self._synth_gemini(text, language, voice, speed)

        if engine == "kokoro" and self.is_available("kokoro"):
            return await self._synth_kokoro(text, language, voice, speed)

        if engine == "xtts" and self.is_available("xtts"):
            return await self._synth_xtts(text, language, voice, speed)

        if engine == "bark" and self.is_available("bark"):
            return await self._synth_bark(text, language, voice, speed)

        if engine == "melotts" and self.is_available("melotts"):
            return await self._synth_melotts(text, language, voice, speed)

        if engine == "f5" and self.is_available("f5"):
            return await self._synth_f5(text, language, voice, speed)

        logger.warning(f"Engine '{engine}' not available, using fallback")
        return await self._synth_fallback(text, language, voice, speed)

    async def synthesize_streaming(self, text: str, engine: str = "piper",
                                    language: str = "ar", voice: str = "default",
                                    speed: float = 1.0) -> AsyncGenerator[bytes, None]:
        """Streaming TTS synthesis"""
        if engine == "piper" and self.is_available("piper"):
            try:
                from piper import PiperVoice
                model_path = settings.MODELS_DIR / "piper" / f"{language}_model.onnx"
                if model_path.exists():
                    voice_obj = PiperVoice.load(str(model_path))
                    # Yield audio chunks
                    audio_data = b""
                    for audio_bytes in voice_obj.synthesize_stream_raw(text):
                        yield audio_bytes
                    return
            except Exception as e:
                logger.error(f"Streaming failed: {e}")

        # Fallback: generate full then yield
        result = await self.synthesize(text, engine, language, voice, speed)
        if result.get("success") and result.get("file"):
            filepath = Path(result["file"])
            if filepath.exists():
                with open(filepath, "rb") as f:
                    while chunk := f.read(4096):
                        yield chunk

    async def synthesize_batch(self, texts: List[str], engine: str = "kokoro",
                                language: str = "ar", voice: str = "default",
                                speed: float = 1.0) -> List[Dict[str, Any]]:
        """Batch TTS synthesis"""
        logger.info(f"Batch TTS: {len(texts)} items, engine={engine}")

        results = []
        semaphore = asyncio.Semaphore(settings.MAX_BATCH_SIZE)

        async def _synth_one(text: str, index: int) -> Dict[str, Any]:
            async with semaphore:
                result = await self.synthesize(text, engine, language, voice, speed)
                result["index"] = index
                result["input_text"] = text[:100]
                return result

        tasks = [_synth_one(text, i) for i, text in enumerate(texts)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return [
            r if isinstance(r, dict) else {"success": False, "error": str(r), "index": i}
            for i, r in enumerate(results)
        ]

    async def clone_voice(self, reference_audio_path: str, text: str,
                          engine: str = "xtts") -> Dict[str, Any]:
        """Clone voice from reference audio"""
        logger.info(f"Voice clone: engine={engine}, ref={reference_audio_path}")

        try:
            if engine == "xtts" and self.is_available("xtts"):
                from TTS.api import TTS as CoquiTTS
                device = self.device if self.device != "cpu" else "cpu"
                model = CoquiTTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2", device=device)
                name_hash = hashlib.md5(text.encode()).hexdigest()[:8]
                filename = f"clone_xtts_{name_hash}.wav"
                filepath = settings.OUTPUTS_DIR / filename
                model.tts_to_file(text=text, language="ar", file_path=str(filepath), speaker_wav=reference_audio_path)
                return {"success": True, "engine": "xtts", "file": str(filepath),
                        "url": f"/api/downloads/{filepath.name}", "message": "Voice cloned with XTTS-v2"}

            elif engine == "openvoice" and self.is_available("openvoice"):
                return await self._clone_openvoice(reference_audio_path, text)

            else:
                return {"success": False, "engine": engine, "file": None, "url": None,
                        "message": f"Engine {engine} not available"}
        except Exception as e:
            logger.error(f"Voice clone failed: {e}")
            return {"success": False, "engine": engine, "file": None, "url": None,
                    "message": f"Voice clone failed: {e}"}

    async def _synth_fallback(self, text: str, language: str, voice: str, speed: float) -> Dict[str, Any]:
        await asyncio.sleep(0.01)
        duration = min(max(len(text) * 0.05, 0.5), 10.0)
        audio_data = generate_sine_wave(frequency=440.0, duration=duration)
        name_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        filename = f"tts_fallback_{name_hash}.wav"
        filepath = save_audio(audio_data, filename)
        return {"success": True, "engine": "fallback", "file": str(filepath),
                "url": f"/api/downloads/{filepath.name}",
                "message": "Generated with fallback engine"}

    async def _synth_kokoro(self, text: str, language: str, voice: str, speed: float) -> Dict[str, Any]:
        try:
            from kokoro import Kokoro
            model = Kokoro()
            audio = model.create(text, voice=voice, speed=speed)
            name_hash = hashlib.md5(text.encode()).hexdigest()[:8]
            filename = f"tts_kokoro_{name_hash}.wav"
            filepath = save_audio(audio, filename, sample_rate=24000)
            return {"success": True, "engine": "kokoro", "file": str(filepath),
                    "url": f"/api/downloads/{filepath.name}", "message": "Generated with Kokoro TTS"}
        except Exception as e:
            logger.error(f"Kokoro failed: {e}")
            return await self._synth_fallback(text, language, voice, speed)

    async def _synth_xtts(self, text: str, language: str, voice: str, speed: float) -> Dict[str, Any]:
        try:
            from TTS.api import TTS as CoquiTTS
            device = self.device if self.device != "cpu" else "cpu"
            model = CoquiTTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2", device=device)
            name_hash = hashlib.md5(text.encode()).hexdigest()[:8]
            filename = f"tts_xtts_{name_hash}.wav"
            filepath = settings.OUTPUTS_DIR / filename
            model.tts_to_file(text=text, language=language, file_path=str(filepath))
            return {"success": True, "engine": "xtts", "file": str(filepath),
                    "url": f"/api/downloads/{filepath.name}", "message": "Generated with XTTS-v2"}
        except Exception as e:
            logger.error(f"XTTS failed: {e}")
            return await self._synth_fallback(text, language, voice, speed)

    async def _synth_bark(self, text: str, language: str, voice: str, speed: float) -> Dict[str, Any]:
        try:
            from bark import generate_audio
            audio = generate_audio(text)
            name_hash = hashlib.md5(text.encode()).hexdigest()[:8]
            filename = f"tts_bark_{name_hash}.wav"
            filepath = settings.OUTPUTS_DIR / filename
            from scipy.io.wavfile import write as write_wav
            write_wav(str(filepath), 24000, audio)
            return {"success": True, "engine": "bark", "file": str(filepath),
                    "url": f"/api/downloads/{filepath.name}", "message": "Generated with Bark"}
        except Exception as e:
            logger.error(f"Bark failed: {e}")
            return await self._synth_fallback(text, language, voice, speed)

    async def _synth_melotts(self, text: str, language: str, voice: str, speed: float) -> Dict[str, Any]:
        try:
            from melo.api import TTS as MeloAPI
            device = self.device if self.device != "cpu" else "cpu"
            melo_lang = "AR" if language == "ar" else "EN"
            model = MeloAPI(language=melo_lang, device=device)
            speaker_ids = model.hps.data.spk2id
            name_hash = hashlib.md5(text.encode()).hexdigest()[:8]
            filename = f"tts_melo_{name_hash}.wav"
            filepath = settings.OUTPUTS_DIR / filename
            speaker_id = speaker_ids.get(voice, list(speaker_ids.values())[0])
            model.tts_to_file(text, speaker_id, output_path=str(filepath), speed=speed)
            return {"success": True, "engine": "melotts", "file": str(filepath),
                    "url": f"/api/downloads/{filepath.name}", "message": f"Generated with MeloTTS ({language})"}
        except Exception as e:
            logger.error(f"MeloTTS failed: {e}")
            return await self._synth_fallback(text, language, voice, speed)

    async def _synth_f5(self, text: str, language: str, voice: str, speed: float) -> Dict[str, Any]:
        try:
            # F5-TTS placeholder - requires actual implementation
            logger.info("F5-TTS synthesis requested")
            return {"success": False, "engine": "f5", "message": "F5-TTS requires manual setup"}
        except Exception as e:
            logger.error(f"F5-TTS failed: {e}")
            return await self._synth_fallback(text, language, voice, speed)

    async def _synth_gemini(self, text: str, language: str, voice: str, speed: float) -> Dict[str, Any]:
        try:
            from google import genai
            from google.genai.types import GenerateContentConfig
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            response = client.models.generate_content(
                model=settings.GEMINI_TTS_MODEL, contents=text,
                config=GenerateContentConfig(response_modalities=["AUDIO"]),
            )
            audio_data = None
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.data:
                    audio_data = part.inline_data.data
                    break
            if not audio_data:
                raise ValueError("No audio in Gemini response")
            name_hash = hashlib.md5(text.encode()).hexdigest()[:8]
            filename = f"tts_gemini_{name_hash}.wav"
            filepath = save_audio(audio_data, filename)
            return {"success": True, "engine": "gemini", "file": str(filepath),
                    "url": f"/api/downloads/{filepath.name}", "message": "Generated with Gemini TTS"}
        except Exception as e:
            logger.error(f"Gemini TTS failed: {e}")
            return await self._synth_fallback(text, language, voice, speed)

    async def _clone_openvoice(self, reference_audio: str, text: str) -> Dict[str, Any]:
        try:
            # OpenVoice placeholder
            logger.info("OpenVoice clone requested")
            return {"success": False, "engine": "openvoice", "message": "OpenVoice requires manual setup"}
        except Exception as e:
            logger.error(f"OpenVoice clone failed: {e}")
            return {"success": False, "engine": "openvoice", "message": str(e)}


tts = TTSEngine()
