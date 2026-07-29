"""Pydantic models shared by the advanced voice AI subsystem."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class QualityMode(str, Enum):
    fast = "fast"
    balanced = "balanced"
    high = "high"
    ultra = "ultra"


class TaskType(str, Enum):
    speech_clone = "speech_clone"
    speech_reading = "speech_reading"
    voice_conversion = "voice_conversion"
    song_generation = "song_generation"


class CloneOptions(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    engine: str = "auto"
    language: str = "ar"
    dialect: Optional[str] = None
    quality_mode: QualityMode = QualityMode.balanced
    candidate_count: int = Field(default=2, ge=1, le=8)
    seed: Optional[int] = Field(default=None, ge=0, le=2**31 - 1)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    consent_confirmed: bool = False
    enable_similarity_scoring: bool = True
    enable_intelligibility_scoring: bool = True
    preserve_dynamics: bool = True
    normalize_reference: bool = True
    trim_silence: bool = True
    denoise_level: float = Field(default=0.0, ge=0.0, le=1.0)
    output_format: str = "wav"
    return_candidates: bool = False
    reference_text: Optional[str] = None

    @field_validator("engine")
    @classmethod
    def normalize_engine(cls, value: str) -> str:
        aliases = {
            "coqui": "xtts",
            "coqui-tts": "xtts",
            "coqui_xtts": "xtts",
            "xtts-v2": "xtts",
            "xtts_v2": "xtts",
            "gpt-sovits": "gpt_sovits",
            "gpt-sovits-v2": "gpt_sovits",
            "f5-tts": "f5tts",
            "open-voice": "openvoice",
            "ace-step": "ace_step",
        }
        normalized = (value or "auto").strip().lower()
        return aliases.get(normalized, normalized)

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, value: str) -> str:
        value = value.lower().lstrip(".")
        if value not in {"wav", "mp3", "flac"}:
            raise ValueError("output_format must be wav, mp3, or flac")
        return value


class ReadingRequest(BaseModel):
    text: str = Field(min_length=1, max_length=100_000)
    engine: str = "auto"
    voice_profile_id: Optional[str] = None
    language: str = "ar"
    number_mode: str = "context"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    consent_confirmed: bool = False


class SongRequest(BaseModel):
    lyrics: str = Field(min_length=1, max_length=50_000)
    prompt: str = Field(default="شيلة عربية أصلية بجودة استوديو", max_length=4_000)
    engine: str = "ace_step"
    duration_seconds: int = Field(default=180, ge=15, le=600)
    seed: Optional[int] = Field(default=None, ge=0, le=2**31 - 1)
    voice_profile_id: Optional[str] = None
    consent_confirmed: bool = False
    output_format: str = "wav"


class EngineStatus(BaseModel):
    name: str
    label: str
    task_types: List[str]
    installed: bool
    healthy: bool
    endpoint: Optional[str] = None
    license_name: str
    license_url: str
    repository_url: str
    detail: Optional[str] = None


class CandidateScore(BaseModel):
    file: str
    engine: str
    seed: int
    speaker_similarity: Optional[float] = None
    intelligibility_score: Optional[float] = None
    audio_quality_score: Optional[float] = None
    frequency_similarity_score: Optional[float] = None
    final_score: float = 0.0
    warnings: List[str] = Field(default_factory=list)


class AgentEvent(BaseModel):
    agent: str
    stage: str
    success: bool
    message: str
    data: Dict[str, Any] = Field(default_factory=dict)
