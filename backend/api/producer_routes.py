"""Studio producer tools with quota-safe interview rendering and local script fallback."""
from __future__ import annotations

import math
import random
import re
import shutil
import struct
import subprocess
import uuid
import wave
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api.studio_pro_routes import _ask_gemini, _copy_to_desktop, _desktop_note
from backend.core.config import OUTPUTS_DIR
from backend.core.tts_registry import tts_registry
from backend.plugins.builtin.audio_effects import _ffmpeg_executable, process_audio

router = APIRouter(prefix="/api/producer", tags=["Producer"])


class AmbientRequest(BaseModel):
    text: str = Field(default="", max_length=30000)
    mood: str = Field(default="auto", max_length=40)
    duration_seconds: int = Field(default=90, ge=10, le=900)


class InterviewRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=2000)
    speakers: int = Field(default=3, ge=2, le=4)
    duration_minutes: int = Field(default=4, ge=1, le=30)
    dialect: str = Field(default="msa", max_length=30)


class DialogueRenderRequest(BaseModel):
    script: str = Field(min_length=2, max_length=30000)
    engine: str = Field(default="edge", max_length=30)
    effect: str = Field(default="podcast", max_length=50)
    speed: float = Field(default=1.0, ge=0.7, le=1.25)


MOODS = {
    "calm": ([110.0, 164.81, 220.0], 0.032),
    "spiritual": ([98.0, 146.83, 196.0], 0.028),
    "hope": ([130.81, 196.0, 261.63], 0.034),
    "cinematic": ([82.41, 123.47, 164.81], 0.038),
    "podcast": ([116.54, 174.61, 233.08], 0.024),
}


def _infer_mood(text: str, requested: str) -> str:
    if requested in MOODS:
        return requested
    sample = text[:3000]
    if any(x in sample for x in ("اللهم", "دعاء", "خشوع", "توبة", "الصلاة")):
        return "spiritual"
    if any(x in sample for x in ("أمل", "نجاح", "فرح", "بداية", "قوة")):
        return "hope"
    if any(x in sample for x in ("قصة", "وثائقي", "ملحمة", "رحلة")):
        return "cinematic"
    if any(x in sample for x in ("بودكاست", "حوار", "مقابلة")):
        return "podcast"
    return "calm"


def _write_ambient(path: Path, mood: str, seconds: int) -> None:
    rate = 24000
    frames = seconds * rate
    freqs, gain = MOODS[mood]
    rnd = random.Random(hash((mood, seconds)) & 0xFFFFFFFF)
    phases = [rnd.random() * math.tau for _ in freqs]
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        chunk = bytearray()
        for i in range(frames):
            t = i / rate
            fade = min(1.0, t / 3.0, (seconds - t) / 4.0)
            breathe = 0.72 + 0.28 * math.sin(math.tau * t / 11.0)
            value = 0.0
            for n, freq in enumerate(freqs):
                value += math.sin(math.tau * freq * t + phases[n]) / (n + 1)
                value += 0.18 * math.sin(math.tau * (freq / 2.0) * t + phases[n] / 2)
            value *= gain * max(0.0, fade) * breathe
            sample = max(-32767, min(32767, int(value * 32767)))
            chunk += struct.pack("<h", sample)
            if len(chunk) >= 65536:
                out.writeframesraw(chunk)
                chunk.clear()
        if chunk:
            out.writeframesraw(chunk)


@router.post("/ambient")
async def generate_ambient(req: AmbientRequest):
    mood = _infer_mood(req.text, req.mood)
    output = OUTPUTS_DIR / f"ambient_{mood}_{uuid.uuid4().hex[:10]}.wav"
    _write_ambient(output, mood, req.duration_seconds)
    target = _copy_to_desktop(output)
    return {
        "success": True,
        "mood": mood,
        "url": f"/api/downloads/{output.name}",
        "desktop_path": str(target) if target else None,
        "desktop_exported": bool(target),
        "message": "تم إنشاء خلفية موسيقية هادئة داخل البرنامج." + _desktop_note(target),
    }


def _local_interview_script(topic: str, roles: list[str], dialect: str) -> str:
    host = roles[0]
    guest = roles[1]
    extra = roles[2:]
    lines = [
        f"{host}: أهلًا بكم في حلقة جديدة. موضوعنا اليوم هو: {topic}. سنناقشه بهدوء وبخطوات عملية واضحة.",
        f"{guest}: شكرًا على الاستضافة. هذا موضوع مهم، والبداية الصحيحة فيه هي فهم الواقع قبل اتخاذ أي قرار.",
        f"{host}: ما أول نقطة ينبغي أن يعرفها المستمع حتى يتعامل مع هذا الموضوع بصورة أفضل؟",
        f"{guest}: أول نقطة هي تحديد الهدف بوضوح، ثم تقسيمه إلى خطوات صغيرة يمكن قياسها والاستمرار عليها.",
    ]
    if extra:
        lines += [
            f"{extra[0]}: وأضيف أن الهدوء وعدم مقارنة النفس بالآخرين يساعدان على اتخاذ قرارات أنضج وأكثر واقعية.",
            f"{host}: هذه نقطة مهمة. ما الخطأ الأكثر شيوعًا الذي ينبغي تجنبه؟",
            f"{extra[0]}: التسرع وانتظار نتيجة فورية. التحسن الحقيقي يحتاج إلى تعلم ومراجعة وصبر.",
        ]
    if len(extra) > 1:
        lines += [
            f"{extra[1]}: من الناحية العملية، من المفيد كتابة خطة أسبوعية ومراجعة النتائج بدل العمل بلا اتجاه واضح.",
            f"{host}: كيف يحافظ الشخص على الاستمرار عندما تقل الحماسة؟",
            f"{extra[1]}: يعتمد على العادات الصغيرة والالتزام بالموعد، لا على الحماسة وحدها.",
        ]
    lines += [
        f"{guest}: والخلاصة أن النجاح في هذا الموضوع لا يأتي من خطوة ضخمة واحدة، بل من قرارات صغيرة صحيحة تتكرر.",
        f"{host}: شكرًا لكم. تذكروا أن البداية الواضحة والاستمرار الهادئ يصنعان فرقًا كبيرًا. نلتقي في حلقة جديدة.",
    ]
    return "\n\n".join(lines)


@router.post("/interview-script")
async def interview_script(req: InterviewRequest):
    roles = ["المذيع_رجل", "الضيف_رجل"]
    if req.speakers >= 3:
        roles.append("الضيفة_امرأة")
    if req.speakers >= 4:
        roles.append("الخبير_رجل")
    dialect = {"yemeni": "يمني طبيعي مفهوم", "gulf": "خليجي طبيعي", "msa": "فصحى سهلة"}.get(req.dialect, "فصحى سهلة")
    prompt = f"""اكتب سيناريو مقابلة صوتية عربية احترافية حول: {req.topic}
المدة التقريبية: {req.duration_minutes} دقائق. الأسلوب: {dialect}.
المتحدثون بالترتيب: {', '.join(roles)}.
كل سطر يجب أن يبدأ حرفيًا باسم المتحدث ثم نقطتين، مثل: المذيع_رجل: النص
اجعل الحوار طبيعيًا، بأسئلة قصيرة، إجابات مفيدة، انتقالات سلسة، وخاتمة واضحة.
لا تضف وصفًا للمشهد ولا تعليمات أداء، وأعد الحوار فقط."""
    try:
        script = await _ask_gemini(prompt, 0.6)
        if not str(script).strip():
            raise RuntimeError("empty script")
        return {"success": True, "script": script, "roles": roles, "fallback": False, "message": "تم إنشاء سيناريو مقابلة متعددة الأصوات."}
    except Exception:
        script = _local_interview_script(req.topic, roles, dialect)
        return {
            "success": True,
            "script": script,
            "roles": roles,
            "fallback": True,
            "message": "حصة محرر Gemini غير متاحة حاليًا؛ أنشأ الاستوديو سيناريو احترافيًا محليًا لتتمكن من متابعة العمل.",
        }


def _voice_for_role(role: str, engine: str) -> str:
    role = role.lower()
    female = any(x in role for x in ("امرأة", "فتاة", "ضيفة", "مذيعة"))
    if engine == "edge":
        if female:
            return "ar-YE-MaryamNeural" if "مذيعة" in role else "ar-SA-ZariyahNeural"
        if "خبير" in role:
            return "ar-AE-HamdanNeural"
        if "ضيف" in role:
            return "ar-SA-HamedNeural"
        return "ar-YE-SalehNeural"
    if female:
        return "Sulafat|podcast_natural" if "ضيفة" in role else "Achernar|podcast_natural"
    if "ضيف" in role:
        return "Gacrux|podcast_natural"
    if "خبير" in role:
        return "Charon|documentary"
    return "Kore|broadcast_power"


def _parse_dialogue(script: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    current_role = "المذيع_رجل"
    buffer: list[str] = []
    for raw in script.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = re.match(r"^([^:：]{2,40})[:：]\s*(.+)$", line)
        if match:
            if buffer:
                result.append((current_role, " ".join(buffer)))
                buffer = []
            current_role = match.group(1).strip()
            buffer.append(match.group(2).strip())
        else:
            buffer.append(line)
    if buffer:
        result.append((current_role, " ".join(buffer)))
    return [(r, t) for r, t in result if t]


def _clean_spoken_text(text: str) -> str:
    value = re.sub(r"^\s*\[[^\]]{1,120}\]\s*", "", text.strip())
    return re.sub(r"\s+", " ", value).strip()


def _speed_for_role(role: str, base_speed: float, index: int) -> float:
    low = role.lower()
    factor = 1.0
    if "مذيع" in low:
        factor = 0.96
    elif "خبير" in low:
        factor = 0.93
    elif "ضيفة" in low or "مذيعة" in low:
        factor = 0.99
    elif "ضيف" in low:
        factor = 0.97
    variation = (1.0, 1.008, 0.994, 1.004, 0.989)[index % 5]
    return max(0.75, min(1.20, base_speed * factor * variation))


def _normalize_and_concat(sources: list[Path], output: Path, pause_ms: int = 340) -> None:
    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        raise RuntimeError("FFmpeg غير متاح داخل البرنامج.")
    work = OUTPUTS_DIR / f".producer_concat_{uuid.uuid4().hex[:8]}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        normalized: list[Path] = []
        for index, source in enumerate(sources):
            target = work / f"part_{index:04d}.wav"
            cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-vn", "-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1", str(target)]
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
            if completed.returncode != 0 or not target.exists():
                raise RuntimeError((completed.stderr or "فشل توحيد مقطع صوتي")[-1200:])
            normalized.append(target)
        pause = work / "pause.wav"
        with wave.open(str(pause), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(24000)
            out.writeframes(b"\x00\x00" * int(24000 * pause_ms / 1000))
        sequence: list[Path] = []
        for index, source in enumerate(normalized):
            sequence.append(source)
            if index < len(normalized) - 1:
                sequence.append(pause)
        manifest = work / "files.txt"
        manifest.write_text("\n".join("file '" + str(path).replace("'", "'\\''") + "'" for path in sequence), encoding="utf-8")
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1", str(output)]
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=1200, check=False)
        if completed.returncode != 0 or not output.exists():
            raise RuntimeError((completed.stderr or "فشل دمج أصوات المقابلة")[-1200:])
    finally:
        shutil.rmtree(work, ignore_errors=True)


async def _render_with_engine(segments: list[tuple[str, str]], engine: str, speed: float, token: str) -> Path:
    plugin = tts_registry.get_plugin(engine)
    if not plugin:
        raise RuntimeError(f"محرك {engine} غير متاح.")
    sources: list[Path] = []
    for index, (role, text) in enumerate(segments):
        spoken = _clean_spoken_text(text) if engine == "edge" else text
        result = await plugin.generate(
            text=spoken,
            voice=_voice_for_role(role, engine),
            language="ar",
            speed=_speed_for_role(role, speed, index),
        )
        if not result or not result.get("success"):
            raise RuntimeError((result or {}).get("message", f"فشل صوت المتحدث {role}"))
        source = Path(result.get("file", ""))
        if not source.exists():
            raise RuntimeError(f"ملف المتحدث {role} غير موجود.")
        sources.append(source)
    raw = OUTPUTS_DIR / f"interview_{engine}_{token}.wav"
    _normalize_and_concat(sources, raw)
    return raw


def _engine_order(requested: str) -> list[str]:
    if requested == "edge":
        return ["edge"]
    if requested == "elevenlabs":
        return ["elevenlabs", "gemini", "edge"]
    if requested == "gemini":
        return ["gemini", "edge"]
    return [requested, "edge"]


@router.post("/render-dialogue")
async def render_dialogue(req: DialogueRenderRequest):
    segments = _parse_dialogue(req.script)
    if not segments:
        raise HTTPException(status_code=400, detail="لم أجد حوارًا بصيغة اسم المتحدث: النص")

    token = uuid.uuid4().hex[:10]
    errors: list[str] = []
    raw: Path | None = None
    engine_used = ""
    for engine in _engine_order(req.engine):
        try:
            raw = await _render_with_engine(segments, engine, req.speed, token)
            engine_used = engine
            break
        except Exception as exc:
            errors.append(f"{engine}: {str(exc)[:300]}")

    if raw is None or not raw.exists():
        raise HTTPException(status_code=502, detail="تعذر إنتاج المقابلة بالمحركات المتاحة. " + " | ".join(errors[-3:]))

    final = OUTPUTS_DIR / f"interview_final_{token}.mp3"
    if req.effect != "none" and process_audio(str(raw), str(final), req.effect):
        output = final
    else:
        output = raw
    target = _copy_to_desktop(output)
    fallback = engine_used != req.engine
    message = "تم إنتاج المقابلة بأصوات مختلفة." + _desktop_note(target)
    if fallback and engine_used == "edge":
        message += " انتهت حصة Gemini، لذلك انتقل الاستوديو فورًا إلى الأصوات العربية المجانية وأكمل الملف بالكامل."
    elif fallback:
        message += f" تم الانتقال تلقائيًا إلى المحرك الاحتياطي {engine_used}."
    return {
        "success": True,
        "url": f"/api/downloads/{output.name}",
        "desktop_path": str(target) if target else None,
        "desktop_exported": bool(target),
        "speakers": len({r for r, _ in segments}),
        "segments": len(segments),
        "engine_requested": req.engine,
        "engine_used": engine_used,
        "fallback": fallback,
        "attempt_errors": errors,
        "message": message,
    }
