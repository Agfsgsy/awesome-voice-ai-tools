"""Engine adapters for native XTTS and isolated optional voice/music runtimes."""
from __future__ import annotations

import asyncio
import importlib.util
import inspect
import os
import random
import threading
from abc import ABC
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from backend.core.logger import get_logger

from .audio import unique_output, validate_generated_audio
from .models import EngineStatus, SongRequest

logger = get_logger("voice_ai_engines")


@dataclass(frozen=True)
class EngineDefinition:
    name: str
    label: str
    repository_url: str
    license_name: str
    license_url: str
    task_types: tuple[str, ...]
    env_endpoint: Optional[str] = None
    default_endpoint: Optional[str] = None


ENGINE_DEFINITIONS: Dict[str, EngineDefinition] = {
    "xtts": EngineDefinition(
        "xtts", "Coqui XTTS-v2", "https://github.com/coqui-ai/TTS",
        "MPL-2.0 code; model license must be reviewed", "https://github.com/coqui-ai/TTS/blob/dev/LICENSE.txt",
        ("speech_clone", "speech_reading"),
    ),
    "openvoice": EngineDefinition(
        "openvoice", "OpenVoice V2", "https://github.com/myshell-ai/OpenVoice",
        "MIT", "https://github.com/myshell-ai/OpenVoice/blob/main/LICENSE",
        ("speech_clone", "voice_conversion"), "OPENVOICE_ENDPOINT", "http://127.0.0.1:8101",
    ),
    "f5tts": EngineDefinition(
        "f5tts", "F5-TTS", "https://github.com/SWivid/F5-TTS",
        "MIT code; model licenses vary", "https://github.com/SWivid/F5-TTS/blob/main/LICENSE",
        ("speech_clone", "speech_reading"), "F5TTS_ENDPOINT", "http://127.0.0.1:8102",
    ),
    "gpt_sovits": EngineDefinition(
        "gpt_sovits", "GPT-SoVITS", "https://github.com/RVC-Boss/GPT-SoVITS",
        "Project/model licenses must be reviewed", "https://github.com/RVC-Boss/GPT-SoVITS",
        ("speech_clone", "speech_reading"), "GPT_SOVITS_ENDPOINT", "http://127.0.0.1:8103",
    ),
    "cosyvoice": EngineDefinition(
        "cosyvoice", "CosyVoice", "https://github.com/FunAudioLLM/CosyVoice",
        "Apache-2.0 code; model terms apply", "https://github.com/FunAudioLLM/CosyVoice/blob/main/LICENSE",
        ("speech_clone", "speech_reading"), "COSYVOICE_ENDPOINT", "http://127.0.0.1:8104",
    ),
    "rvc": EngineDefinition(
        "rvc", "Retrieval-based Voice Conversion", "https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI",
        "MIT", "https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI/blob/master/LICENSE",
        ("voice_conversion",), "RVC_ENDPOINT", "http://127.0.0.1:8110",
    ),
    "ace_step": EngineDefinition(
        "ace_step", "ACE-Step", "https://github.com/ace-step/ACE-Step",
        "Review repository and model terms", "https://github.com/ace-step/ACE-Step",
        ("song_generation",), "ACE_STEP_ENDPOINT", "http://127.0.0.1:8120",
    ),
    "yue": EngineDefinition(
        "yue", "YuE", "https://github.com/multimodal-art-projection/YuE",
        "Review repository and model terms", "https://github.com/multimodal-art-projection/YuE",
        ("song_generation",), "YUE_ENDPOINT", "http://127.0.0.1:8121",
    ),
    "gemini": EngineDefinition(
        "gemini", "Gemini prebuilt TTS", "https://ai.google.dev/gemini-api/docs/speech-generation",
        "Google service terms", "https://ai.google.dev/gemini-api/terms",
        ("speech_reading",),
    ),
    "google_custom_voice": EngineDefinition(
        "google_custom_voice", "Google Cloud Custom Voice", "https://cloud.google.com/text-to-speech/docs/chirp3-instant-custom-voice",
        "Google Cloud service terms", "https://cloud.google.com/terms",
        ("speech_clone", "speech_reading"), "GOOGLE_CUSTOM_VOICE_ENDPOINT", None,
    ),
}


class VoiceEngine(ABC):
    definition: EngineDefinition

    async def health(self) -> EngineStatus:
        raise NotImplementedError

    async def clone(
        self,
        *,
        text: str,
        references: Sequence[Path],
        language: str,
        seed: int,
        speed: float = 1.0,
        reference_text: Optional[str] = None,
    ) -> Path:
        raise RuntimeError(f"{self.definition.name} does not implement speech cloning")

    async def generate_song(self, request: SongRequest) -> Path:
        raise RuntimeError(f"{self.definition.name} does not implement song generation")


class NativeXTTSEngine(VoiceEngine):
    definition = ENGINE_DEFINITIONS["xtts"]

    def __init__(self) -> None:
        self._model: Any = None
        self._model_lock = threading.Lock()
        self._inference_lock = asyncio.Lock()

    def _installed(self) -> bool:
        return importlib.util.find_spec("TTS") is not None

    async def health(self) -> EngineStatus:
        installed = self._installed()
        return EngineStatus(
            name=self.definition.name,
            label=self.definition.label,
            task_types=list(self.definition.task_types),
            installed=installed,
            healthy=installed,
            license_name=self.definition.license_name,
            license_url=self.definition.license_url,
            repository_url=self.definition.repository_url,
            detail=None if installed else "ثبت الحزمة الاختيارية TTS لتفعيل XTTS-v2",
        )

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        with self._model_lock:
            if self._model is None:
                from TTS.api import TTS as CoquiTTS

                model = CoquiTTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2")
                try:
                    import torch
                    if torch.cuda.is_available() and hasattr(model, "to"):
                        model = model.to("cuda")
                except Exception:
                    logger.info("XTTS is using its default device")
                self._model = model
        return self._model

    async def clone(
        self,
        *,
        text: str,
        references: Sequence[Path],
        language: str,
        seed: int,
        speed: float = 1.0,
        reference_text: Optional[str] = None,
    ) -> Path:
        if not references:
            raise ValueError("REFERENCE_AUDIO_NOT_FOUND")
        if not self._installed():
            raise RuntimeError("ENGINE_NOT_INSTALLED: xtts")
        output = unique_output("clone_xtts")

        def infer() -> None:
            try:
                import numpy as np
                import torch
                random.seed(seed)
                np.random.seed(seed % (2**32 - 1))
                torch.manual_seed(seed)
                if torch.cuda.is_available():
                    torch.cuda.manual_seed_all(seed)
            except Exception:
                pass

            model = self._get_model()
            kwargs: Dict[str, Any] = {
                "text": text,
                "language": language.split("-")[0],
                "speaker_wav": [str(item) for item in references] if len(references) > 1 else str(references[0]),
                "file_path": str(output),
            }
            signature = inspect.signature(model.tts_to_file)
            if "speed" in signature.parameters:
                kwargs["speed"] = speed
            if "split_sentences" in signature.parameters:
                kwargs["split_sentences"] = True
            model.tts_to_file(**kwargs)

        async with self._inference_lock:
            await asyncio.to_thread(infer)
        validate_generated_audio(output)
        return output


class HttpRuntimeEngine(VoiceEngine):
    """Uniform adapter for isolated official-tool runtimes.

    Each optional runtime exposes `/health`, `/clone`, or `/song/generate`,
    keeping incompatible Torch/CUDA dependencies outside the main process.
    """

    def __init__(self, definition: EngineDefinition) -> None:
        self.definition = definition
        self.endpoint = os.getenv(definition.env_endpoint or "", definition.default_endpoint or "").rstrip("/") or None

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self.endpoint:
            raise RuntimeError(f"ENGINE_ENDPOINT_NOT_CONFIGURED: {self.definition.name}")
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required for runtime engines") from exc
        timeout = httpx.Timeout(900.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method, f"{self.endpoint}{path}", **kwargs)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                return response.json()
            return response.content

    async def health(self) -> EngineStatus:
        if not self.endpoint:
            return EngineStatus(
                name=self.definition.name,
                label=self.definition.label,
                task_types=list(self.definition.task_types),
                installed=False,
                healthy=False,
                endpoint=None,
                license_name=self.definition.license_name,
                license_url=self.definition.license_url,
                repository_url=self.definition.repository_url,
                detail=f"اضبط {self.definition.env_endpoint} بعد تشغيل runtime الرسمي",
            )
        try:
            data = await self._request("GET", "/health")
            healthy = bool(data.get("healthy", data.get("status") in {"ok", "healthy", "running"})) if isinstance(data, dict) else True
            return EngineStatus(
                name=self.definition.name,
                label=self.definition.label,
                task_types=list(self.definition.task_types),
                installed=True,
                healthy=healthy,
                endpoint=self.endpoint,
                license_name=self.definition.license_name,
                license_url=self.definition.license_url,
                repository_url=self.definition.repository_url,
                detail=data.get("message") if isinstance(data, dict) else None,
            )
        except Exception as exc:
            return EngineStatus(
                name=self.definition.name,
                label=self.definition.label,
                task_types=list(self.definition.task_types),
                installed=True,
                healthy=False,
                endpoint=self.endpoint,
                license_name=self.definition.license_name,
                license_url=self.definition.license_url,
                repository_url=self.definition.repository_url,
                detail=str(exc),
            )

    async def clone(
        self,
        *,
        text: str,
        references: Sequence[Path],
        language: str,
        seed: int,
        speed: float = 1.0,
        reference_text: Optional[str] = None,
    ) -> Path:
        files = [("references", (path.name, path.read_bytes(), "audio/wav")) for path in references]
        data = {
            "text": text,
            "language": language,
            "seed": str(seed),
            "speed": str(speed),
            "reference_text": reference_text or "",
        }
        result = await self._request("POST", "/clone", files=files, data=data)
        return await self._materialize_result(result, f"clone_{self.definition.name}")

    async def generate_song(self, request: SongRequest) -> Path:
        result = await self._request("POST", "/song/generate", json=request.model_dump())
        return await self._materialize_result(result, f"song_{self.definition.name}")

    async def _materialize_result(self, result: Any, prefix: str) -> Path:
        if isinstance(result, bytes):
            output = unique_output(prefix)
            output.write_bytes(result)
            validate_generated_audio(output)
            return output
        if isinstance(result, dict):
            candidate = result.get("file") or result.get("path")
            if candidate:
                path = Path(candidate).expanduser().resolve()
                validate_generated_audio(path)
                return path
            encoded = result.get("audio_base64")
            if encoded:
                import base64
                output = unique_output(prefix)
                output.write_bytes(base64.b64decode(encoded))
                validate_generated_audio(output)
                return output
        raise RuntimeError("RUNTIME_OUTPUT_INVALID")


class VoiceEngineRegistry:
    def __init__(self) -> None:
        self.engines: Dict[str, VoiceEngine] = {"xtts": NativeXTTSEngine()}
        for name, definition in ENGINE_DEFINITIONS.items():
            if name not in self.engines and definition.default_endpoint is not None:
                self.engines[name] = HttpRuntimeEngine(definition)

    def get(self, name: str) -> VoiceEngine:
        normalized = name.strip().lower()
        aliases = {
            "coqui": "xtts", "coqui-tts": "xtts", "xtts-v2": "xtts", "xtts_v2": "xtts",
            "f5-tts": "f5tts", "gpt-sovits": "gpt_sovits", "ace-step": "ace_step",
        }
        normalized = aliases.get(normalized, normalized)
        if normalized not in self.engines:
            raise KeyError(f"ENGINE_NOT_REGISTERED: {normalized}")
        return self.engines[normalized]

    async def statuses(self) -> List[EngineStatus]:
        return await asyncio.gather(*(engine.health() for engine in self.engines.values()))

    async def available_for(self, task_type: str) -> List[VoiceEngine]:
        candidates: List[VoiceEngine] = []
        for engine in self.engines.values():
            if task_type not in engine.definition.task_types:
                continue
            status = await engine.health()
            if status.healthy:
                candidates.append(engine)
        priority = {"xtts": 0, "f5tts": 1, "gpt_sovits": 2, "openvoice": 3, "cosyvoice": 4, "ace_step": 0, "yue": 1}
        return sorted(candidates, key=lambda item: priority.get(item.definition.name, 99))


voice_engine_registry = VoiceEngineRegistry()
