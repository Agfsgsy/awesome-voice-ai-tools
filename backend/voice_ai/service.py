"""High-level voice-cloning, reading, analysis, and song-generation service."""
from __future__ import annotations

import asyncio
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from backend.core.logger import get_logger

from .agents import SupervisorAgent, VoiceTaskContext
from .audio import analyze_audio, safe_resolve_audio, validate_generated_audio
from .engines import VoiceEngine, VoiceEngineRegistry, voice_engine_registry
from .models import CloneOptions, SongRequest
from .numbers import normalize_numbers_in_text

logger = get_logger("voice_ai_suite")


class VoiceAISuite:
    def __init__(self, registry: VoiceEngineRegistry | None = None) -> None:
        self.registry = registry or voice_engine_registry
        self.supervisor = SupervisorAgent()
        self._speaker_model: Any = None
        self._speaker_lock = asyncio.Lock()
        self._whisper_model: Any = None
        self._whisper_lock = asyncio.Lock()

    async def engine_statuses(self) -> List[Dict[str, Any]]:
        statuses = await self.registry.statuses()
        return [status.model_dump() for status in statuses]

    async def clone(self, references: Sequence[str | Path], options: CloneOptions) -> Dict[str, Any]:
        resolved = [safe_resolve_audio(path) for path in references]
        context = VoiceTaskContext(options=options, references=resolved)
        engines = await self.supervisor.prepare(context, self.registry)
        target_count = self._candidate_count(options)
        seeds = self._seeds(options.seed, target_count)
        tasks: List[asyncio.Task[Optional[Dict[str, Any]]]] = []
        for index, seed in enumerate(seeds):
            engine = engines[index % len(engines)]
            tasks.append(asyncio.create_task(self._generate_candidate(context, engine, seed, index)))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, dict):
                context.candidates.append(result)
            elif isinstance(result, Exception):
                context.emit("clone", "candidate", False, str(result))

        if not context.candidates:
            strategy = self.supervisor.repair.next_strategy(0, engines[0].definition.name)
            retry_seed = seeds[0] + int(strategy["seed_delta"])
            retry = await self._generate_candidate(
                context,
                engines[0],
                retry_seed,
                999,
                speed_delta=float(strategy["speed_delta"]),
            )
            if retry:
                context.candidates.append(retry)

        selected = self.supervisor.judge.select(context)
        candidate_payload = context.candidates if options.return_candidates else []
        warnings = [warning for report in context.reference_reports for warning in report.get("warnings", [])]
        return {
            "success": True,
            "task": "voice_clone",
            "engine": selected["engine"],
            "language": options.language,
            "dialect": options.dialect,
            "quality_mode": options.quality_mode.value,
            "candidate_count": len(context.candidates),
            "selected_candidate": selected["candidate_index"],
            "speaker_similarity_raw": selected.get("speaker_similarity"),
            "similarity_status": "measured" if selected.get("speaker_similarity") is not None else "not_measured",
            "intelligibility_score": selected.get("intelligibility_score"),
            "audio_quality_score": selected.get("audio_quality_score"),
            "frequency_similarity_score": selected.get("frequency_similarity_score"),
            "file": selected["file"],
            "url": f"/api/downloads/{Path(selected['file']).name}",
            "duration_seconds": selected.get("duration_seconds"),
            "warnings": warnings + selected.get("warnings", []),
            "reference_analysis": context.reference_reports,
            "candidate_scores": candidate_payload,
            "agent_events": [event.model_dump() for event in context.events],
            "message": "تم إنشاء أفضل نتيجة صوتية متاحة؛ التشابه يعتمد على جودة التسجيل والمحرك",
        }

    async def _generate_candidate(
        self,
        context: VoiceTaskContext,
        engine: VoiceEngine,
        seed: int,
        candidate_index: int,
        speed_delta: float = 0.0,
    ) -> Optional[Dict[str, Any]]:
        try:
            output = await engine.clone(
                text=context.normalized_text or context.options.text,
                references=context.prepared_references,
                language=context.options.language,
                seed=seed,
                speed=max(0.5, min(2.0, context.options.speed + speed_delta)),
                reference_text=context.options.reference_text,
            )
            generated_report = validate_generated_audio(output)
            reference_report = context.reference_reports[0]
            speaker_similarity = (
                await self._speaker_similarity(context.prepared_references[0], output)
                if context.options.enable_similarity_scoring else None
            )
            intelligibility = (
                await self._intelligibility(
                    context.normalized_text or context.options.text,
                    output,
                    context.options.language,
                )
                if context.options.enable_intelligibility_scoring else None
            )
            frequency_similarity = self.supervisor.frequency.compare(reference_report, generated_report)
            audio_quality = float(generated_report.get("quality_score") or 0.0)
            final_score = self._weighted_score(
                speaker_similarity,
                intelligibility,
                audio_quality,
                frequency_similarity,
            )
            context.emit(
                "clone",
                "candidate",
                True,
                "تم إنشاء مرشح",
                engine=engine.definition.name,
                seed=seed,
                score=final_score,
            )
            return {
                "candidate_index": candidate_index,
                "file": str(output),
                "url": f"/api/downloads/{output.name}",
                "engine": engine.definition.name,
                "seed": seed,
                "speaker_similarity": speaker_similarity,
                "intelligibility_score": intelligibility,
                "audio_quality_score": audio_quality,
                "frequency_similarity_score": frequency_similarity,
                "final_score": final_score,
                "duration_seconds": generated_report.get("duration_seconds"),
                "warnings": generated_report.get("warnings", []),
            }
        except Exception as exc:
            logger.exception("Candidate generation failed: engine=%s", engine.definition.name)
            context.emit("clone", "candidate", False, str(exc), engine=engine.definition.name, seed=seed)
            return None

    async def read_text(
        self,
        *,
        text: str,
        references: Sequence[str | Path],
        engine: str = "auto",
        language: str = "ar",
        number_mode: str = "context",
        consent_confirmed: bool = False,
        speed: float = 1.0,
    ) -> Dict[str, Any]:
        normalized = normalize_numbers_in_text(text, mode=number_mode)
        options = CloneOptions(
            text=normalized,
            engine=engine,
            language=language,
            quality_mode="balanced",
            candidate_count=2,
            consent_confirmed=consent_confirmed,
            speed=speed,
        )
        result = await self.clone(references, options)
        result["task"] = "speech_reading"
        result["normalized_text"] = normalized
        return result

    async def analyze(self, path: str | Path) -> Dict[str, Any]:
        resolved = safe_resolve_audio(path)
        return analyze_audio(resolved)

    async def generate_song(self, request: SongRequest) -> Dict[str, Any]:
        if request.voice_profile_id and not request.consent_confirmed:
            raise PermissionError("CONSENT_REQUIRED")
        engine_name = request.engine.strip().lower().replace("-", "_")
        engine = self.registry.get(engine_name)
        status = await engine.health()
        if not status.healthy:
            raise RuntimeError(f"ENGINE_NOT_AVAILABLE: {engine_name}; {status.detail or ''}")
        output = await engine.generate_song(request)
        report = validate_generated_audio(output)
        return {
            "success": True,
            "task": "song_generation",
            "engine": engine_name,
            "file": str(output),
            "url": f"/api/downloads/{output.name}",
            "duration_seconds": report.get("duration_seconds"),
            "audio_quality_score": report.get("quality_score"),
            "warnings": report.get("warnings", []),
            "message": "تم توليد الملف الغنائي بواسطة runtime خارجي معزول",
        }

    @staticmethod
    def _candidate_count(options: CloneOptions) -> int:
        defaults = {"fast": 1, "balanced": 2, "high": 3, "ultra": 5}
        return max(1, min(options.candidate_count, defaults[options.quality_mode.value], 8))

    @staticmethod
    def _seeds(base_seed: Optional[int], count: int) -> List[int]:
        first = base_seed if base_seed is not None else random.SystemRandom().randint(1, 2**31 - 1)
        return [int((first + index * 104_729) % (2**31 - 1)) for index in range(count)]

    @staticmethod
    def _weighted_score(
        speaker_similarity: Optional[float],
        intelligibility: Optional[float],
        audio_quality: Optional[float],
        frequency_similarity: Optional[float],
    ) -> float:
        values = {
            "speaker": (speaker_similarity, 0.55),
            "intelligibility": (intelligibility, 0.20),
            "quality": (audio_quality, 0.15),
            "frequency": (frequency_similarity, 0.10),
        }
        available = [(float(value), weight) for value, weight in values.values() if value is not None]
        if not available:
            return 0.0
        weight_sum = sum(weight for _, weight in available)
        return round(sum(value * weight for value, weight in available) / weight_sum, 4)

    async def _speaker_similarity(self, reference: Path, generated: Path) -> Optional[float]:
        try:
            import torch
            import torchaudio
            from speechbrain.inference.speaker import EncoderClassifier
        except Exception:
            return None
        async with self._speaker_lock:
            if self._speaker_model is None:
                self._speaker_model = await asyncio.to_thread(
                    EncoderClassifier.from_hparams,
                    source="speechbrain/spkrec-ecapa-voxceleb",
                    savedir=str(Path("models") / "speechbrain_ecapa"),
                )
            model = self._speaker_model

        def embed(path: Path) -> Any:
            signal, sample_rate = torchaudio.load(str(path))
            if signal.shape[0] > 1:
                signal = signal.mean(dim=0, keepdim=True)
            if sample_rate != 16_000:
                signal = torchaudio.functional.resample(signal, sample_rate, 16_000)
            return model.encode_batch(signal).squeeze().detach().cpu()

        try:
            left, right = await asyncio.gather(
                asyncio.to_thread(embed, reference),
                asyncio.to_thread(embed, generated),
            )
            similarity = torch.nn.functional.cosine_similarity(
                left.flatten(),
                right.flatten(),
                dim=0,
            ).item()
            return round(max(-1.0, min(1.0, similarity)), 4)
        except Exception:
            logger.exception("Speaker similarity measurement failed")
            return None

    async def _intelligibility(self, target_text: str, generated: Path, language: str) -> Optional[float]:
        try:
            from faster_whisper import WhisperModel
        except Exception:
            return None
        async with self._whisper_lock:
            if self._whisper_model is None:
                self._whisper_model = await asyncio.to_thread(
                    WhisperModel,
                    "small",
                    device="cpu",
                    compute_type="int8",
                )
            model = self._whisper_model

        def transcribe() -> str:
            segments, _ = model.transcribe(str(generated), language=language.split("-")[0])
            return " ".join(segment.text.strip() for segment in segments).strip()

        try:
            hypothesis = await asyncio.to_thread(transcribe)
            return self._character_similarity(target_text, hypothesis)
        except Exception:
            logger.exception("Intelligibility scoring failed")
            return None

    @staticmethod
    def _character_similarity(expected: str, actual: str) -> float:
        def normalize(value: str) -> str:
            replacements = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي"})
            return "".join(
                char for char in value.translate(replacements).lower()
                if char.isalnum() or char.isspace()
            ).strip()

        left, right = normalize(expected), normalize(actual)
        if not left:
            return 0.0
        previous = list(range(len(right) + 1))
        for i, left_char in enumerate(left, 1):
            current = [i]
            for j, right_char in enumerate(right, 1):
                current.append(
                    min(
                        current[-1] + 1,
                        previous[j] + 1,
                        previous[j - 1] + (left_char != right_char),
                    )
                )
            previous = current
        distance = previous[-1]
        return round(max(0.0, 1.0 - distance / max(len(left), len(right), 1)), 4)


voice_ai_suite = VoiceAISuite()
