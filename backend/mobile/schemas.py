"""نماذج طلبات API الجوال مع تحقق صارم للمدخلات."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class PairRequest(BaseModel):
    pairing_id: str = Field(min_length=10, max_length=80)
    pairing_code: str = Field(min_length=8, max_length=16)
    device_name: str = Field(min_length=1, max_length=120)
    platform: str = Field(default="android", max_length=60)
    app_version: str = Field(default="1.0.0", max_length=40)


class AuthRequest(BaseModel):
    device_id: str = Field(min_length=10, max_length=80)
    device_token: str = Field(min_length=32, max_length=256)


class VoiceCloneRequest(BaseModel):
    reference_file_id: str = Field(min_length=10, max_length=500)
    text: str = Field(min_length=1, max_length=5000)
    engine: str = Field(default="xtts", min_length=2, max_length=50)
    language: str = Field(default="ar", min_length=2, max_length=20)
    candidate_count: int = Field(default=3, ge=1, le=5)
    consent_confirmed: bool
    voice_rights: Literal["self", "explicit_authorization"]
    consent_statement: str = Field(min_length=12, max_length=500)

    @field_validator("text", "consent_statement")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("القيمة لا يمكن أن تكون فارغة")
        return value.strip()


class VoiceSynthesisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    engine: str = Field(default="auto", min_length=2, max_length=50)
    language: str = Field(default="ar", min_length=2, max_length=20)
    voice: str = Field(default="default", min_length=1, max_length=120)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    candidate_count: int = Field(default=1, ge=1, le=5)


class PrepareEngineRequest(BaseModel):
    model_name: str = Field(default="default", min_length=1, max_length=120)


class SongGenerateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    lyrics: str = Field(min_length=1, max_length=12000)
    style: str = Field(default="شيلة عربية", min_length=2, max_length=120)
    engine: str = Field(default="auto", min_length=2, max_length=50)
    language: str = Field(default="ar", min_length=2, max_length=20)
    voice: str = Field(default="default", min_length=1, max_length=120)
    candidate_count: int = Field(default=3, ge=1, le=5)
    tempo: float = Field(default=1.0, ge=0.5, le=2.0)
    pitch_semitones: float = Field(default=0.0, ge=-6.0, le=6.0)
    reverb: float = Field(default=0.25, ge=0.0, le=1.0)
    instrumental_file_id: str | None = Field(default=None, max_length=500)

    @field_validator("title", "lyrics", "style")
    @classmethod
    def strip_values(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("القيمة لا يمكن أن تكون فارغة")
        return value.strip()
