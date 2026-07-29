"""Deterministic agent-style orchestration for voice AI tasks."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .audio import analyze_audio, basic_frequency_similarity, convert_to_wav
from .models import AgentEvent, CloneOptions
from .numbers import normalize_numbers_in_text


@dataclass
class VoiceTaskContext:
    options: CloneOptions
    references: List[Path]
    prepared_references: List[Path] = field(default_factory=list)
    reference_reports: List[Dict[str, Any]] = field(default_factory=list)
    normalized_text: str = ""
    selected_engines: List[str] = field(default_factory=list)
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    selected: Optional[Dict[str, Any]] = None
    events: List[AgentEvent] = field(default_factory=list)

    def emit(self, agent: str, stage: str, success: bool, message: str, **data: Any) -> None:
        self.events.append(AgentEvent(agent=agent, stage=stage, success=success, message=message, data=data))


class ConsentAgent:
    def run(self, context: VoiceTaskContext) -> None:
        if not context.options.consent_confirmed:
            context.emit("consent", "validate", False, "يلزم تأكيد ملكية الصوت أو وجود إذن صريح")
            raise PermissionError("CONSENT_REQUIRED")
        context.emit("consent", "validate", True, "تم تسجيل تأكيد الموافقة")


class NumberAgent:
    def run(self, context: VoiceTaskContext) -> None:
        context.normalized_text = normalize_numbers_in_text(context.options.text, mode="context")
        context.emit(
            "number",
            "normalize",
            True,
            "تمت معالجة الأرقام قبل التوليد",
            changed=context.normalized_text != context.options.text,
        )


class ReferenceAgent:
    def run(self, context: VoiceTaskContext) -> None:
        accepted: List[Path] = []
        reports: List[Dict[str, Any]] = []
        for reference in context.references:
            report = analyze_audio(reference)
            reports.append(report)
            if (report.get("duration_seconds") or 0.0) < 1.0:
                continue
            if report.get("rms") is not None and report["rms"] < 0.0005:
                continue
            prepared = convert_to_wav(reference, sample_rate=24_000, trim_silence=context.options.trim_silence)
            accepted.append(prepared)
        context.reference_reports = reports
        context.prepared_references = accepted
        if not accepted:
            context.emit("reference", "prepare", False, "لم يوجد تسجيل مرجعي صالح")
            raise ValueError("INVALID_REFERENCE_AUDIO")
        context.emit("reference", "prepare", True, "تم تجهيز التسجيلات المرجعية", accepted=len(accepted))


class FrequencyAgent:
    def compare(self, reference_report: Dict[str, Any], generated_report: Dict[str, Any]) -> Optional[float]:
        return basic_frequency_similarity(reference_report, generated_report)


class EngineAgent:
    async def select(self, context: VoiceTaskContext, registry: Any) -> List[Any]:
        if context.options.engine != "auto":
            engines = [registry.get(context.options.engine)]
        else:
            engines = await registry.available_for("speech_clone")
        if not engines:
            context.emit("engine", "select", False, "لا يوجد محرك استنساخ سليم ومثبت")
            raise RuntimeError("ENGINE_NOT_AVAILABLE")
        limits = {"fast": 1, "balanced": 2, "high": 3, "ultra": 5}
        selected = engines[: limits[context.options.quality_mode.value]]
        context.selected_engines = [engine.definition.name for engine in selected]
        context.emit("engine", "select", True, "تم اختيار محركات الاستنساخ", engines=context.selected_engines)
        return selected


class JudgeAgent:
    def select(self, context: VoiceTaskContext) -> Dict[str, Any]:
        if not context.candidates:
            context.emit("judge", "rank", False, "لم ينتج أي مرشح صالح")
            raise RuntimeError("NO_VALID_CANDIDATE")
        selected = max(context.candidates, key=lambda item: float(item.get("final_score", 0.0)))
        context.selected = selected
        context.emit("judge", "rank", True, "تم اختيار المرشح الأعلى تقييمًا", score=selected.get("final_score"))
        return selected


class RepairAgent:
    @staticmethod
    def next_strategy(attempt: int, current_engine: str) -> Dict[str, Any]:
        strategies = [
            {"speed_delta": -0.03, "seed_delta": 101, "note": "تقليل السرعة قليلًا"},
            {"speed_delta": 0.03, "seed_delta": 211, "note": "زيادة السرعة قليلًا"},
            {"speed_delta": 0.0, "seed_delta": 997, "note": "تغيير العينة العشوائية"},
        ]
        return strategies[min(attempt, len(strategies) - 1)] | {"engine": current_engine}


class SupervisorAgent:
    def __init__(self) -> None:
        self.consent = ConsentAgent()
        self.numbers = NumberAgent()
        self.reference = ReferenceAgent()
        self.engine = EngineAgent()
        self.judge = JudgeAgent()
        self.repair = RepairAgent()
        self.frequency = FrequencyAgent()

    async def prepare(self, context: VoiceTaskContext, registry: Any) -> List[Any]:
        self.consent.run(context)
        self.numbers.run(context)
        self.reference.run(context)
        return await self.engine.select(context, registry)
