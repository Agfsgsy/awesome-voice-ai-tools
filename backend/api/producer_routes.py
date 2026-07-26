"""Studio 2.8 producer tools: adaptive ambience, male/female presets and multi-speaker interviews."""
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

from backend.core.config import OUTPUTS_DIR
from backend.core.tts_registry import tts_registry
from backend.plugins.builtin.audio_effects import _ffmpeg_executable, process_audio
from backend.api.studio_pro_routes import _ask_gemini, _desktop_exports

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
    engine: str = Field(default="gemini", max_length=30)
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
    target = _desktop_exports() / output.name
    shutil.copy2(output, target)
    return {
        "success": True,
        "mood": mood,
        "url": f"/api/downloads/{output.name}",
        "desktop_path": str(target),
        "message": "تم إنشاء خلفية موسيقية هادئة داخل البرنامج وحفظها على سطح المكتب.",
    }


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
    script = await _ask_gemini(prompt, 0.6)
    return {"success": True, "script": script, "roles": roles, "message": "تم إنشاء سيناريو مقابلة متعددة الأصوات."}


def _voice_for_role(role: str, engine: str) -> str:
    role = role.lower()
    female = any(x in role for x in ("امرأة", "فتاة", "ضيفة", "مذيعة"))
    if engine == "edge":
        if female:
            return "ar-YE-MaryamNeural" if "يمن" in role else "ar-SA-ZariyahNeural"
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


def _silence(path: Path, milliseconds: int = 360) -> None:
    rate = 24000
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"\x00\x00" * int(rate * milliseconds / 1000))


@router.post("/render-dialogue")
async def render_dialogue(req: DialogueRenderRequest):
    segments = _parse_dialogue(req.script)
    if not segments:
        raise HTTPException(status_code=400, detail="لم أجد حوارًا بصيغة اسم المتحدث: النص")
    plugin = tts_registry.get_plugin(req.engine)
    if not plugin:
        raise HTTPException(status_code=503, detail="محرك الصوت المحدد غير متاح.")
    token = uuid.uuid4().hex[:10]
    work = OUTPUTS_DIR / f"dialogue_{token}_parts"
    work.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    silence = work / "pause.wav"
    _silence(silence)
    for index, (role, text) in enumerate(segments):
        result = await plugin.generate(text=text, voice=_voice_for_role(role, req.engine), language="ar", speed=req.speed)
        if not result or not result.get("success"):
            raise HTTPException(status_code=502, detail=(result or {}).get("message", f"فشل صوت المتحدث {role}"))
        source = Path(result.get("file", ""))
        if not source.exists():
            raise HTTPException(status_code=500, detail=f"ملف المتحدث {role} غير موجود.")
        files.append(source)
        if index < len(segments) - 1:
            files.append(silence)
    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        raise HTTPException(status_code=500, detail="FFmpeg غير متاح داخل البرنامج.")
    concat = work / "concat.txt"
    concat.write_text("\n".join(f"file '{str(p).replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'" for p in files), encoding="utf-8")
    raw = OUTPUTS_DIR / f"interview_{token}.wav"
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1", str(raw)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900, check=False)
    if proc.returncode != 0 or not raw.exists():
        raise HTTPException(status_code=500, detail=(proc.stderr or "فشل دمج أصوات المقابلة")[-1200:])
    final = OUTPUTS_DIR / f"interview_final_{token}.mp3"
    if req.effect != "none" and process_audio(str(raw), str(final), req.effect):
        output = final
    else:
        output = raw
    target = _desktop_exports() / output.name
    shutil.copy2(output, target)
    return {
        "success": True,
        "url": f"/api/downloads/{output.name}",
        "desktop_path": str(target),
        "speakers": len({r for r, _ in segments}),
        "segments": len(segments),
        "message": "تم إنتاج المقابلة بأصوات مختلفة وحفظها على سطح المكتب.",
    }
