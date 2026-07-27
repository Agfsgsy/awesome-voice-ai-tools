"""Additive reliability layer for Yemeni Creative.

This module does not replace or delete the original Yemeni Creative implementation.
It exposes safe endpoints used by the repaired UI: fast local writing, bounded Gemini
writing, strict provider selection, resilient music mixing, and Desktop project packs.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api import yemeni_creative_routes as legacy
from backend.api.studio_pro_routes import _ask_gemini
from backend.api.ultimate_studio_routes import SynthesisRequest, _synthesize_strict
from backend.core.config import OUTPUTS_DIR
from backend.core.logger import get_logger
from backend.plugins.builtin.audio_effects import _ffmpeg_executable

router = APIRouter(prefix="/api/yemeni-creative-safe", tags=["Yemeni Creative Safe"])
logger = get_logger("yemeni_creative_safe")


class SafeWriteRequest(BaseModel):
    content_type: str = Field(default="shila", max_length=30)
    title: str = Field(default="", max_length=160)
    recipient: str = Field(default="", max_length=180)
    occasion: str = Field(default="نجاح وتفوق", max_length=240)
    subject: str = Field(default="", max_length=1400)
    keywords: str = Field(default="", max_length=900)
    dialect: str = Field(default="yemeni_white", max_length=30)
    mood: Literal["proud", "warm", "emotional", "joyful", "powerful"] = "proud"
    verses: int = Field(default=12, ge=6, le=40)
    writer_provider: Literal["local", "gemini", "auto"] = "local"
    include_recipient: bool = True


class SafeProduceRequest(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    text: str = Field(min_length=2, max_length=12000)
    content_type: str = Field(default="shila", max_length=30)
    provider: str = Field(default="edge", max_length=40)
    gender: Literal["male", "female"] = "male"
    voice_id: str = Field(default="auto", max_length=180)
    tone: str = Field(default="energetic", max_length=40)
    speed: float = Field(default=0.96, ge=0.75, le=1.20)
    music_style: str = Field(default="shila_modern", max_length=40)
    music_volume: float = Field(default=0.18, ge=0.0, le=0.45)
    include_music: bool = True
    master_loudness: float = Field(default=-14.0, ge=-20.0, le=-10.0)


def _plain(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("message", "detail", "error", "reason"):
            if value.get(key):
                return _plain(value[key])
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return " | ".join(_plain(item) for item in value)
    return str(value)


def _legacy_request(request: SafeWriteRequest) -> legacy.WriteRequest:
    return legacy.WriteRequest(
        content_type=request.content_type,
        title=request.title,
        recipient=request.recipient,
        occasion=request.occasion,
        subject=request.subject,
        keywords=request.keywords,
        dialect=request.dialect,
        mood=request.mood,
        verses=request.verses,
        writer_provider=request.writer_provider,
        include_recipient=request.include_recipient,
    )


def _write_local(request: SafeWriteRequest) -> tuple[str, str]:
    return legacy._local_original(_legacy_request(request))


def _parse_ai(text: str, request: SafeWriteRequest) -> tuple[str, str]:
    fallback_title, fallback_body = _write_local(request)
    title, body = legacy._parse_written(text, fallback_title)
    if len(body.strip()) < 30:
        return fallback_title, fallback_body
    return title, body


def _safe_component(value: str, fallback: str = "عمل يمني") -> str:
    return legacy._safe_name(value, fallback)


def _desktop_root() -> Path:
    return legacy._desktop() / "استوديو ابن الواقدي" / "الأعمال اليمنية"


def _run(command: list[str], timeout: int = 1200) -> None:
    completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "فشل تجهيز الصوت")[-1800:])


def _simple_mix(ffmpeg: str, voice: Path, music: Path, output: Path, volume: float, loudness: float) -> None:
    """Fallback mixer for FFmpeg builds where sidechaincompress is unavailable."""
    graph = (
        "[0:a]aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=65,"
        "acompressor=threshold=-20dB:ratio=2.5:attack=12:release=180[voice];"
        f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={volume:.4f}[bed];"
        f"[voice][bed]amix=inputs=2:duration=first:dropout_transition=2,"
        f"loudnorm=I={loudness}:TP=-1.0:LRA=9,alimiter=limit=0.96[out]"
    )
    _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(voice),
            "-stream_loop",
            "-1",
            "-i",
            str(music),
            "-filter_complex",
            graph,
            "-map",
            "[out]",
            "-shortest",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "320k",
            str(output),
        ]
    )


def _project_pack(
    *,
    token: str,
    title: str,
    content_type: str,
    provider: str,
    text: str,
    final_audio: Path,
    voice_audio: Path,
    instrumental: Path | None,
    warnings: list[str],
    voice_metadata: Any,
    music_style: str,
) -> Path:
    label = legacy.CONTENT_TYPES.get(content_type, legacy.CONTENT_TYPES["dedication"])["label"]
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    directory = _desktop_root() / _safe_component(label) / _safe_component(f"{title}_{stamp}_{token[:5]}")
    directory.mkdir(parents=True, exist_ok=True)

    final_target = directory / f"{_safe_component(title)} - الماستر النهائي{final_audio.suffix.lower()}"
    voice_target = directory / f"{_safe_component(title)} - الصوت المنفرد{voice_audio.suffix.lower()}"
    shutil.copy2(final_audio, final_target)
    shutil.copy2(voice_audio, voice_target)
    if instrumental and instrumental.exists():
        shutil.copy2(instrumental, directory / f"{_safe_component(title)} - الموسيقى الأصلية.mp3")
    (directory / f"{_safe_component(title)} - الكلمات.txt").write_text(text, encoding="utf-8-sig")
    metadata = {
        "title": title,
        "content_type": content_type,
        "content_label": label,
        "provider": provider,
        "voice": voice_metadata,
        "music_style": music_style,
        "quality": "MP3 320kbps / 48kHz stereo",
        "warnings": warnings,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "original_text_and_music": True,
        "safe_hotfix": True,
    }
    (directory / "معلومات العمل.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return directory


@router.get("/health")
async def health():
    ffmpeg = _ffmpeg_executable()
    return {
        "success": True,
        "writer_local": True,
        "gemini_optional": True,
        "ffmpeg_ready": bool(ffmpeg),
        "content_types": list(legacy.CONTENT_TYPES),
        "shila_ready": "shila" in legacy.CONTENT_TYPES,
        "zamil_ready": "zamil" in legacy.CONTENT_TYPES,
        "message": "محرك الشيلات والزامل جاهز. الإنشاء المحلي يعمل دون مفتاح Gemini.",
    }


@router.post("/write")
async def write_safe(request: SafeWriteRequest):
    if request.content_type not in legacy.CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="نوع العمل غير معروف.")

    # Local writing is deliberately instant and is the default. Gemini is bounded
    # by a short timeout so the button never appears frozen for minutes.
    if request.writer_provider == "local":
        title, body = _write_local(request)
        return {
            "success": True,
            "title": title,
            "text": body,
            "writer_used": "local",
            "original": True,
            "message": "تم إنشاء النص فورًا بالكاتب المحلي الأصلي.",
        }

    legacy_request = _legacy_request(request)
    try:
        generated = await asyncio.wait_for(_ask_gemini(legacy._writer_prompt(legacy_request), 0.76), timeout=35.0)
        title, body = _parse_ai(generated, request)
        return {
            "success": True,
            "title": title,
            "text": body,
            "writer_used": "gemini",
            "original": True,
            "message": "تم إنشاء النص عبر Gemini وتجهيزه للشيلة أو الزامل.",
        }
    except Exception as exc:
        if request.writer_provider == "gemini":
            raise HTTPException(status_code=502, detail=f"تعذر استخدام Gemini خلال المهلة: {_plain(exc)}") from exc
        title, body = _write_local(request)
        return {
            "success": True,
            "title": title,
            "text": body,
            "writer_used": "local",
            "original": True,
            "warning": _plain(exc),
            "message": "تعذر Gemini بسرعة، لذلك أُنشئ النص فورًا بالكاتب المحلي بدل تعليق الزر.",
        }


@router.post("/produce")
async def produce_safe(request: SafeProduceRequest):
    if request.content_type not in legacy.CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="نوع العمل غير معروف.")
    if request.include_music and request.music_style not in legacy.MUSIC_STYLES:
        raise HTTPException(status_code=422, detail="النمط الموسيقي غير معروف.")

    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        raise HTTPException(status_code=503, detail="FFmpeg غير جاهز داخل النسخة الحالية. شغّل إصلاح البرنامج مرة أخرى.")

    provider = (request.provider or "edge").strip().lower()
    locale = "ar-YE" if provider == "edge" else None
    synthesis = SynthesisRequest(
        text=request.text,
        provider=provider,
        language="ar",
        gender=request.gender,
        locale=locale,
        voice_id=request.voice_id or "auto",
        tone=request.tone,
        speed=request.speed,
        effect="none",
    )

    try:
        result = await asyncio.wait_for(_synthesize_strict(synthesis), timeout=360.0)
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="انتهت مهلة محرك الصوت. افحص الإنترنت ثم أعد المحاولة.") from exc

    voice = Path(str(result.get("file", "")))
    if not voice.exists() or voice.stat().st_size < 256:
        raise HTTPException(status_code=502, detail="لم يُنشأ ملف الصوت رغم اكتمال الطلب.")

    token = uuid.uuid4().hex[:12]
    final = OUTPUTS_DIR / f"yemeni_safe_{request.content_type}_{provider}_{token}_master.mp3"
    instrumental: Path | None = None
    music_wav: Path | None = None
    warnings: list[str] = []

    if request.include_music and request.music_volume > 0:
        try:
            # A 12-second original loop is enough because FFmpeg repeats it. This
            # keeps the button responsive while the final output remains 48 kHz.
            music_wav = OUTPUTS_DIR / f"yemeni_safe_music_{request.music_style}_{token}.wav"
            instrumental = OUTPUTS_DIR / f"yemeni_safe_music_{request.music_style}_{token}_instrumental.mp3"
            legacy._music_sample(legacy.MUSIC_STYLES[request.music_style], 12, token, music_wav)
            legacy._instrumental_mp3(ffmpeg, music_wav, instrumental)
            try:
                legacy._master_with_music(ffmpeg, voice, music_wav, final, request.music_volume, request.master_loudness)
            except Exception as advanced_exc:
                logger.warning("Advanced Yemeni mix failed; using compatible mix: %s", advanced_exc)
                warnings.append("استُخدم الدمج المتوافق لأن الدمج المتقدم غير مدعوم في FFmpeg الحالي.")
                _simple_mix(ffmpeg, voice, music_wav, final, request.music_volume, request.master_loudness)
        except Exception as music_exc:
            logger.warning("Yemeni music failed; preserving voice master: %s", music_exc)
            warnings.append("تعذرت الموسيقى، فتم حفظ الصوت بماستر واضح بدل فقدان النتيجة.")
            instrumental = None
            legacy._master_voice(ffmpeg, voice, final, request.master_loudness)
    else:
        legacy._master_voice(ffmpeg, voice, final, request.master_loudness)

    if not final.exists() or final.stat().st_size < 1024:
        raise HTTPException(status_code=500, detail="لم يكتمل ملف الماستر النهائي.")

    project = _project_pack(
        token=token,
        title=request.title,
        content_type=request.content_type,
        provider=provider,
        text=request.text,
        final_audio=final,
        voice_audio=voice,
        instrumental=instrumental,
        warnings=warnings,
        voice_metadata=result.get("voice_metadata") or result.get("voice"),
        music_style=request.music_style if request.include_music else "none",
    )

    return {
        "success": True,
        "title": request.title,
        "provider": provider,
        "url": f"/api/downloads/{final.name}",
        "voice_url": result.get("url") or f"/api/downloads/{voice.name}",
        "instrumental_url": f"/api/downloads/{instrumental.name}" if instrumental and instrumental.exists() else None,
        "desktop_project": str(project),
        "quality": "MP3 320kbps / 48kHz stereo",
        "warnings": warnings,
        "message": "تم إنتاج العمل وحفظ حزمته على سطح المكتب." + (" توجد ملاحظة موضحة في النتيجة." if warnings else ""),
    }


@router.post("/open-project")
async def open_project(path: str):
    project = Path(path).resolve()
    allowed = _desktop_root().resolve()
    try:
        project.relative_to(allowed)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="المسار خارج مجلد الأعمال اليمنية.") from exc
    if not project.is_dir():
        raise HTTPException(status_code=404, detail="مجلد المشروع غير موجود.")
    try:
        if os.name == "nt":
            os.startfile(str(project))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(project)])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"تعذر فتح المجلد: {exc}") from exc
    return {"success": True, "path": str(project)}
