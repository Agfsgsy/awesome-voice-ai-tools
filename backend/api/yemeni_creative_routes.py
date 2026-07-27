"""Yemeni creative studio for original dedications, poetry, zamil and musical spoken works.

The feature is additive: it never deletes or changes an existing generated file. Every
production creates a project pack containing the text, isolated voice, original
instrumental loop and a mastered 320 kbps / 48 kHz MP3 on the Windows Desktop.
"""
from __future__ import annotations

import json
import math
import os
import random
import re
import shutil
import struct
import subprocess
import uuid
import wave
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api.studio_pro_routes import _ask_gemini
from backend.api.ultimate_studio_routes import SynthesisRequest, _synthesize_strict
from backend.core.config import OUTPUTS_DIR
from backend.core.logger import get_logger
from backend.plugins.builtin.audio_effects import _ffmpeg_executable

router = APIRouter(prefix="/api/yemeni-creative", tags=["Yemeni Creative Studio"])
logger = get_logger("yemeni_creative")


CONTENT_TYPES: dict[str, dict[str, str]] = {
    "zamil": {"label": "زامل يمني أصلي", "delivery": "إلقاء جماهيري قوي بإيقاع موزون"},
    "shila": {"label": "شيلة يمنية أصلية", "delivery": "أداء لحني إلقائي دافئ وواضح"},
    "poem": {"label": "قصيدة يمنية", "delivery": "إلقاء شعري رزين ووجداني"},
    "song": {"label": "أغنية عربية أصلية", "delivery": "أداء غنائي إلقائي خفيف ومبهج"},
    "success": {"label": "نشيد نجاح وتفوق", "delivery": "أداء احتفالي ملهم ومشرق"},
    "dedication": {"label": "إهداء شخصي", "delivery": "أداء حميم وصادق ومؤثر"},
    "graduation": {"label": "إهداء تخرج", "delivery": "أداء فخور واحتفالي"},
    "wedding": {"label": "إهداء فرح وزفاف", "delivery": "أداء فرائحي راقٍ دون مبالغة"},
}

MUSIC_STYLES: dict[str, dict[str, Any]] = {
    "yemeni_oud": {
        "label": "عود يمني دافئ",
        "bpm": 88,
        "base": 196.0,
        "scale": (1.0, 16 / 15, 5 / 4, 4 / 3, 3 / 2, 8 / 5, 15 / 8),
        "density": 0.72,
        "percussion": 0.42,
        "brightness": 0.64,
    },
    "zamil_power": {
        "label": "زامل يمني حماسي",
        "bpm": 104,
        "base": 174.61,
        "scale": (1.0, 16 / 15, 5 / 4, 4 / 3, 3 / 2, 8 / 5, 15 / 8),
        "density": 0.90,
        "percussion": 0.90,
        "brightness": 0.70,
    },
    "shila_modern": {
        "label": "شيلة حديثة راقية",
        "bpm": 96,
        "base": 220.0,
        "scale": (1.0, 9 / 8, 5 / 4, 4 / 3, 3 / 2, 5 / 3, 15 / 8),
        "density": 0.82,
        "percussion": 0.68,
        "brightness": 0.78,
    },
    "success_cinematic": {
        "label": "نجاح سينمائي ملهم",
        "bpm": 100,
        "base": 196.0,
        "scale": (1.0, 9 / 8, 5 / 4, 4 / 3, 3 / 2, 5 / 3, 15 / 8),
        "density": 0.76,
        "percussion": 0.62,
        "brightness": 0.86,
    },
    "dedication_warm": {
        "label": "إهداء دافئ وهادئ",
        "bpm": 78,
        "base": 185.0,
        "scale": (1.0, 9 / 8, 6 / 5, 4 / 3, 3 / 2, 8 / 5, 9 / 5),
        "density": 0.58,
        "percussion": 0.28,
        "brightness": 0.58,
    },
    "poetry_minimal": {
        "label": "شعر يمني هادئ",
        "bpm": 72,
        "base": 174.61,
        "scale": (1.0, 16 / 15, 6 / 5, 4 / 3, 3 / 2, 8 / 5, 9 / 5),
        "density": 0.46,
        "percussion": 0.16,
        "brightness": 0.46,
    },
}

DIALECTS = {
    "yemeni_white": "لهجة يمنية بيضاء مفهومة عربيًا",
    "sanaani": "لهجة صنعانية مهذبة ومفهومة دون كلمات غامضة",
    "taizzi": "لهجة تعزية خفيفة ومفهومة",
    "adeni": "لهجة عدنية لطيفة ومفهومة",
    "hadrami": "لهجة حضرمية خفيفة ومفهومة",
    "msa": "فصحى عربية سهلة بروح يمنية",
}


class WriteRequest(BaseModel):
    content_type: str = Field(default="success", max_length=30)
    title: str = Field(default="", max_length=160)
    recipient: str = Field(default="", max_length=180)
    occasion: str = Field(default="نجاح وتفوق", max_length=240)
    subject: str = Field(default="", max_length=1200)
    keywords: str = Field(default="", max_length=800)
    dialect: str = Field(default="yemeni_white", max_length=30)
    mood: Literal["proud", "warm", "emotional", "joyful", "powerful"] = "proud"
    verses: int = Field(default=12, ge=6, le=36)
    writer_provider: Literal["auto", "gemini", "local"] = "auto"
    include_recipient: bool = True


class ProduceRequest(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    text: str = Field(min_length=2, max_length=12000)
    content_type: str = Field(default="success", max_length=30)
    provider: str = Field(default="edge", max_length=40)
    gender: Literal["male", "female"] = "male"
    voice_id: str = Field(default="auto", max_length=180)
    tone: str = Field(default="energetic", max_length=40)
    speed: float = Field(default=0.96, ge=0.75, le=1.20)
    music_style: str = Field(default="success_cinematic", max_length=40)
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


def _safe_name(value: str, fallback: str = "عمل يمني") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", (value or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .-")
    return (cleaned[:90] or fallback)


def _desktop() -> Path:
    candidates: list[Path] = []
    for key in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        root = os.getenv(key, "").strip()
        if root:
            candidates.append(Path(root) / "Desktop")
    profile = os.getenv("USERPROFILE", "").strip()
    if profile:
        candidates.append(Path(profile) / "Desktop")
    candidates.append(Path.home() / "Desktop")
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    fallback = Path(profile) / "Desktop" if profile else Path.home() / "Desktop"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _title_for(request: WriteRequest) -> str:
    if request.title.strip():
        return _safe_name(request.title)
    recipient = request.recipient.strip()
    type_label = CONTENT_TYPES.get(request.content_type, CONTENT_TYPES["dedication"])["label"]
    return _safe_name(f"{type_label} - {recipient}" if recipient else f"{type_label} - {request.occasion}")


def _writer_prompt(request: WriteRequest) -> str:
    metadata = CONTENT_TYPES.get(request.content_type, CONTENT_TYPES["dedication"])
    dialect = DIALECTS.get(request.dialect, DIALECTS["yemeni_white"])
    recipient = request.recipient.strip() if request.include_recipient else ""
    return f"""أنت شاعر وكاتب أغانٍ وإهداءات يمني محترف داخل استوديو ابن الواقدي.
اكتب عملًا عربيًا أصليًا بالكامل، لا يقتبس ولا يعيد صياغة كلمات أغنية منشورة، ولا يقلد فنانًا أو شاعرًا بعينه.

نوع العمل: {metadata['label']}
طريقة الأداء: {metadata['delivery']}
اللهجة: {dialect}
المناسبة: {request.occasion}
اسم المهدى إليه: {recipient or 'لا تذكر اسمًا محددًا'}
الفكرة: {request.subject or 'النجاح والإصرار والوفاء والفرح بالإنجاز'}
الكلمات المهمة: {request.keywords or 'الأمل، العزيمة، التفوق، الوفاء'}
المزاج: {request.mood}
عدد الأسطر التقريبي: {request.verses}

قواعد إلزامية:
- اكتب عنوانًا في السطر الأول بهذه الصيغة: العنوان: ...
- اجعل النص سهل النطق والتسجيل، وقسّمه إلى مقاطع قصيرة.
- استخدم قافية لطيفة غير متكلفة، وصورًا يمنية أصيلة مثل الجبل والبُنّ والمطر والنور من دون حشو.
- تجنب الادعاءات والمبالغة المؤذية، ولا تكتب أي إساءة أو قبلية أو تحريض.
- لا تضع أسماء فنانين ولا عبارة «على لحن» ولا تعليمات تقنية تُقرأ بصوت مرتفع.
- عند كتابة زامل أو شيلة، اجعله أداءً إيقاعيًا أصليًا لا نسخة من عمل معروف.
- أعد العنوان والنص النهائي فقط.
"""


def _local_original(request: WriteRequest) -> tuple[str, str]:
    """Deterministic original fallback that does not imitate existing lyrics."""
    recipient = request.recipient.strip() if request.include_recipient else ""
    name = recipient or "صاحب الإنجاز"
    occasion = request.occasion.strip() or "النجاح"
    title = _title_for(request)
    seed = hash((request.content_type, name, occasion, request.subject, request.keywords)) & 0xFFFFFFFF
    rnd = random.Random(seed)

    openings = [
        f"يا {name} يا ضوّ المعالي في دروب المجتهدين",
        f"من أرض اليمن نهدي {name} فرحة الطموح",
        f"هذا نهار المجد، واسم {name} فوق السحاب",
        f"يا مرحبا بالإنجاز يوم أقبل مبتسم",
    ]
    middles = [
        "خطوة وراء خطوة، وصبرٍ ما عرف يوم انكسار",
        "من شَمّة البُنّ ابتدينا، للجبل معنى الثبات",
        "كل التعب صار ابتسامة، وكل حلمٍ صار باب",
        "من يزرع العزم بصدق، يحصد من الأيام نور",
        "والقلب يشهد أن الوفا للناس أجمل انتصار",
        "نمشي على درب الأمل، والعين ما ترضى القليل",
        "في كل عثرة درس قوة، وفي التقدم ألف عيد",
        "ما ضاع جهدٍ صادقٍ، دام الطموح له دليل",
        "يا نجم هذا اليوم، خلّي فرحتك تسكن قلوب",
        "تبقى المواقف والنجاحات الجميلة خير ذكر",
    ]
    closings = [
        f"مبروك يا {name}، وإلى نجاحٍ بعد نجاح",
        f"هذا إهداء القلب في يوم {occasion}، والعمر أفراح",
        f"تبقى على قمة طموحك، والفرح يمشي معاك",
        "والله يجعل كل خطوة في طريقك خير ونور",
    ]
    chorus = [
        f"رددوا باسم {name}، هذا يومه وهذا الإنجاز",
        "عزيمةٌ ثم عزيمة، والمستحيل اليوم جاز",
        "من اليمن نهدي سلامًا، بالوفا والعز فاز",
    ]

    target = max(6, request.verses)
    lines = [rnd.choice(openings)]
    pool = middles[:]
    rnd.shuffle(pool)
    while len(lines) < max(3, target - 4):
        lines.append(pool[(len(lines) - 1) % len(pool)])
    if request.content_type in {"zamil", "shila", "song", "success", "graduation", "wedding"}:
        lines.extend(chorus)
    lines.extend(rnd.sample(closings, k=min(2, len(closings))))
    lines = lines[:target]
    return title, "\n".join(lines)


def _parse_written(text: str, fallback_title: str) -> tuple[str, str]:
    value = (text or "").strip()
    first, *rest = value.splitlines()
    if first.strip().startswith("العنوان:"):
        title = _safe_name(first.split(":", 1)[1].strip(), fallback_title)
        body = "\n".join(rest).strip()
        return title, body or value
    return fallback_title, value


def _music_sample(config: dict[str, Any], seconds: int, token: str, output: Path) -> None:
    """Create an original stereo 48 kHz instrumental loop with plucked strings and percussion."""
    rate = 48000
    frames = rate * seconds
    bpm = float(config["bpm"])
    beat_seconds = 60.0 / bpm
    base = float(config["base"])
    scale = tuple(float(item) for item in config["scale"])
    density = float(config["density"])
    percussion = float(config["percussion"])
    brightness = float(config["brightness"])
    rng = random.Random(int(token[:8], 16))
    pattern = [0, 3, 4, 2, 5, 4, 3, 1, 0, 4, 5, 3, 2, 1, 4, 3]
    variation = [rng.choice((-1, 0, 0, 0, 1)) for _ in pattern]

    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(rate)
        buffer = bytearray()
        for index in range(frames):
            t = index / rate
            beat = t / beat_seconds
            half = beat * 2.0
            step = int(half)
            local = half - step
            note_index = (pattern[step % len(pattern)] + variation[step % len(pattern)]) % len(scale)
            freq = base * scale[note_index]

            # Oud/qanbus-inspired pluck: decaying harmonics, never sampled from a recording.
            env = math.exp(-7.8 * local) * density
            phase_t = local * (beat_seconds / 2.0)
            pluck = (
                math.sin(math.tau * freq * phase_t)
                + 0.47 * math.sin(math.tau * freq * 2.0 * phase_t + 0.22)
                + 0.22 * math.sin(math.tau * freq * 3.0 * phase_t + 0.47)
            ) * env * 0.19

            # Soft ney-like layer and drone.
            vibrato = 1.0 + 0.004 * math.sin(math.tau * 5.1 * t)
            melody = math.sin(math.tau * (base * 2.0) * vibrato * t + 0.35 * math.sin(math.tau * 0.18 * t))
            melody *= (0.035 + 0.025 * brightness) * (0.72 + 0.28 * math.sin(math.tau * 0.08 * t))
            drone = (math.sin(math.tau * (base / 2.0) * t) + 0.4 * math.sin(math.tau * base * t)) * 0.028

            # Original percussion synthesis: kick, hand drum and shaker.
            beat_local = beat - math.floor(beat)
            beat_number = int(beat) % 4
            kick = 0.0
            if beat_number in (0, 2):
                kick_env = math.exp(-22.0 * beat_local)
                kick = math.sin(math.tau * (68.0 - 24.0 * beat_local) * beat_local) * kick_env * 0.23 * percussion
            clap_local = (beat_local if beat_number in (1, 3) else 1.0)
            noise = math.sin((index * 12.9898 + 78.233) * 43758.5453)
            clap = noise * math.exp(-36.0 * clap_local) * 0.07 * percussion if beat_number in (1, 3) else 0.0
            eighth = (beat * 2.0) % 1.0
            shaker_noise = math.sin((index * 0.754877666 + 0.569840296) * 12345.678)
            shaker = shaker_noise * math.exp(-45.0 * eighth) * 0.025 * percussion

            fade = min(1.0, t / 1.2, (seconds - t) / 1.4)
            fade = max(0.0, fade)
            pan = 0.18 * math.sin(math.tau * 0.035 * t + (step % 2) * math.pi)
            common = (melody + drone + kick + clap + shaker) * fade
            left = common + pluck * (0.82 - pan)
            right = common + pluck * (0.82 + pan)
            left = math.tanh(left * 1.12)
            right = math.tanh(right * 1.12)
            buffer.extend(struct.pack("<hh", int(max(-1.0, min(1.0, left)) * 32767), int(max(-1.0, min(1.0, right)) * 32767)))
            if len(buffer) >= 262144:
                out.writeframesraw(buffer)
                buffer.clear()
        if buffer:
            out.writeframesraw(buffer)


def _run(command: list[str], timeout: int = 1200) -> None:
    completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "فشل تجهيز الملف الصوتي")[-1800:])


def _master_voice(ffmpeg: str, voice: Path, output: Path, loudness: float) -> None:
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(voice),
        "-vn",
        "-af",
        f"highpass=f=65,acompressor=threshold=-20dB:ratio=2.6:attack=12:release=180,loudnorm=I={loudness}:TP=-1.0:LRA=8,alimiter=limit=0.96",
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
    _run(command)


def _master_with_music(ffmpeg: str, voice: Path, music_loop: Path, output: Path, volume: float, loudness: float) -> None:
    graph = (
        f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=65,"
        "acompressor=threshold=-20dB:ratio=2.5:attack=12:release=180[voice];"
        f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={volume:.4f},lowpass=f=12000[bed];"
        "[bed][voice]sidechaincompress=threshold=0.018:ratio=8:attack=18:release=430:makeup=1[ducked];"
        f"[voice][ducked]amix=inputs=2:duration=first:dropout_transition=2,loudnorm=I={loudness}:TP=-1.0:LRA=9,alimiter=limit=0.96[out]"
    )
    command = [
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
        str(music_loop),
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
    _run(command)


def _instrumental_mp3(ffmpeg: str, source: Path, output: Path) -> None:
    _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-af",
            "loudnorm=I=-18:TP=-1.5:LRA=10,alimiter=limit=0.95",
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
    metadata: dict[str, Any],
) -> Path:
    style_label = CONTENT_TYPES.get(content_type, CONTENT_TYPES["dedication"])["label"]
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    directory = _desktop() / "استوديو ابن الواقدي" / "الأعمال اليمنية" / _safe_name(style_label) / _safe_name(f"{title}_{stamp}_{token[:5]}")
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copy2(final_audio, directory / f"{_safe_name(title)} - الماستر النهائي.mp3")
    shutil.copy2(voice_audio, directory / f"{_safe_name(title)} - الصوت المنفرد{voice_audio.suffix.lower()}")
    if instrumental and instrumental.exists():
        shutil.copy2(instrumental, directory / f"{_safe_name(title)} - الموسيقى الأصلية.mp3")
    (directory / f"{_safe_name(title)} - الكلمات.txt").write_text(text, encoding="utf-8-sig")
    (directory / "معلومات العمل.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return directory


@router.get("/catalog")
async def catalog():
    return {
        "success": True,
        "content_types": [{"id": key, **value} for key, value in CONTENT_TYPES.items()],
        "music_styles": [{"id": key, "label": value["label"], "bpm": value["bpm"]} for key, value in MUSIC_STYLES.items()],
        "dialects": [{"id": key, "label": value} for key, value in DIALECTS.items()],
        "quality": "MP3 320kbps / 48kHz stereo",
        "original_only": True,
    }


@router.post("/write")
async def write_original(request: WriteRequest):
    if request.content_type not in CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="نوع العمل غير معروف.")
    fallback_title = _title_for(request)
    used = "local"
    title = fallback_title
    body = ""
    if request.writer_provider in {"auto", "gemini"}:
        try:
            generated = await _ask_gemini(_writer_prompt(request), 0.76)
            title, body = _parse_written(generated, fallback_title)
            if len(body.strip()) < 30:
                raise RuntimeError("النص المولد قصير جدًا")
            used = "gemini"
        except Exception as exc:
            if request.writer_provider == "gemini":
                raise HTTPException(status_code=502, detail=f"تعذر إنشاء النص عبر Gemini: {_plain(exc)}") from exc
            logger.warning("Gemini Yemeni writing unavailable; using original local writer: %s", exc)
    if not body:
        title, body = _local_original(request)
    return {
        "success": True,
        "title": title,
        "text": body,
        "writer_used": used,
        "original": True,
        "message": "تم إنشاء نص أصلي جاهز للمراجعة والإنتاج، من دون تقليد عمل منشور.",
    }


@router.post("/produce")
async def produce_original(request: ProduceRequest):
    if request.content_type not in CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="نوع العمل غير معروف.")
    if request.include_music and request.music_style not in MUSIC_STYLES:
        raise HTTPException(status_code=422, detail="النمط الموسيقي غير معروف.")
    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        raise HTTPException(status_code=503, detail="FFmpeg غير متاح؛ لا يمكن إنشاء الماستر عالي الجودة.")

    token = uuid.uuid4().hex[:12]
    provider = request.provider
    locale = "ar-YE" if provider in {"edge", "azure"} else None
    synthesis = SynthesisRequest(
        text=request.text,
        provider=provider,
        language="ar",
        gender=request.gender,
        locale=locale,
        voice_id=request.voice_id,
        tone=request.tone,
        speed=request.speed,
        effect="none",
    )
    result = await _synthesize_strict(synthesis)
    voice = Path(result.get("file", ""))
    if not voice.exists() or voice.stat().st_size == 0:
        raise HTTPException(status_code=502, detail="نجح الطلب لكن ملف الصوت المنفرد لم يُنشأ.")

    safe_style = _safe_name(request.content_type, "dedication")
    final = OUTPUTS_DIR / f"yemeni_{safe_style}_{provider}_{token}_master.mp3"
    music_wav: Path | None = None
    instrumental: Path | None = None
    try:
        if request.include_music and request.music_volume > 0:
            music_wav = OUTPUTS_DIR / f"yemeni_music_{request.music_style}_{token}.wav"
            instrumental = OUTPUTS_DIR / f"yemeni_music_{request.music_style}_{token}_instrumental.mp3"
            _music_sample(MUSIC_STYLES[request.music_style], 28, token, music_wav)
            _instrumental_mp3(ffmpeg, music_wav, instrumental)
            _master_with_music(ffmpeg, voice, music_wav, final, request.music_volume, request.master_loudness)
        else:
            _master_voice(ffmpeg, voice, final, request.master_loudness)
    except Exception as exc:
        final.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"تعذر إنشاء الماستر النهائي: {_plain(exc)}") from exc

    if not final.exists() or final.stat().st_size < 1024:
        raise HTTPException(status_code=500, detail="لم يكتمل ملف الماستر النهائي.")

    metadata = {
        "title": request.title,
        "content_type": request.content_type,
        "content_label": CONTENT_TYPES[request.content_type]["label"],
        "provider": provider,
        "gender": request.gender,
        "voice": result.get("voice_metadata") or result.get("voice"),
        "music_style": request.music_style if request.include_music else "none",
        "music_label": MUSIC_STYLES.get(request.music_style, {}).get("label") if request.include_music else "بدون موسيقى",
        "quality": "MP3 320kbps / 48kHz stereo",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "original_text_and_music": True,
    }
    project_dir = _project_pack(
        token=token,
        title=request.title,
        content_type=request.content_type,
        provider=provider,
        text=request.text,
        final_audio=final,
        voice_audio=voice,
        instrumental=instrumental,
        metadata=metadata,
    )
    return {
        "success": True,
        "token": token,
        "title": request.title,
        "provider": provider,
        "voice_url": result.get("url") or f"/api/downloads/{voice.name}",
        "instrumental_url": f"/api/downloads/{instrumental.name}" if instrumental and instrumental.exists() else None,
        "url": f"/api/downloads/{final.name}",
        "file": str(final),
        "desktop_project": str(project_dir),
        "quality": metadata["quality"],
        "message": "تم إنشاء حزمة العمل اليمني كاملة وحفظها على سطح المكتب: الكلمات، الصوت المنفرد، الموسيقى الأصلية، والماستر النهائي.",
    }


@router.post("/open-project")
async def open_project(path: str):
    project = Path(path).resolve()
    allowed_root = (_desktop() / "استوديو ابن الواقدي" / "الأعمال اليمنية").resolve()
    try:
        project.relative_to(allowed_root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="لا يمكن فتح مسار خارج مجلد الأعمال اليمنية.") from exc
    if not project.exists() or not project.is_dir():
        raise HTTPException(status_code=404, detail="مجلد العمل غير موجود.")
    try:
        if os.name == "nt":
            os.startfile(str(project))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(project)])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"تعذر فتح المجلد: {exc}") from exc
    return {"success": True, "path": str(project)}
