"""Professional multi-speaker interview production with resumable Cloud-Only jobs."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
import wave
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api.studio_pro_routes import _ask_gemini, _desktop_exports
from backend.core.config import OUTPUTS_DIR
from backend.core.tts_registry import tts_registry
from backend.plugins.builtin.audio_effects import _ffmpeg_executable, process_audio

router = APIRouter(prefix="/api/interview-pro", tags=["Interview Pro"])


class ScenarioRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=2000)
    duration_minutes: int = Field(default=6, ge=1, le=45)
    format: str = Field(default="host_two_guests", max_length=50)
    dialect: str = Field(default="yemeni", max_length=30)
    tone: str = Field(default="calm_powerful", max_length=40)
    audience: str = Field(default="الجمهور العربي العام", max_length=200)


class RenderRequest(BaseModel):
    script: str = Field(min_length=2, max_length=50000)
    engine: str = Field(default="gemini", max_length=30)
    master: str = Field(default="podcast_ultra", max_length=50)
    base_speed: float = Field(default=0.96, ge=0.75, le=1.20)
    pause_ms: int = Field(default=420, ge=150, le=1400)


FORMATS = {
    "host_guest": ["المذيع_رجل", "الضيف_رجل"],
    "host_female_guest": ["المذيعة_امرأة", "الضيف_رجل"],
    "host_two_guests": ["المذيع_رجل", "الضيف_رجل", "الضيفة_امرأة"],
    "panel_four": ["المذيع_رجل", "الضيف_رجل", "الضيفة_امرأة", "الخبير_رجل"],
}

ENGINE_LABELS = {
    "gemini": "Gemini TTS السحابي",
    "elevenlabs": "ElevenLabs المدفوع",
    "edge": "الصوت المجاني المختار يدويًا",
}


def _local_scenario(topic: str, roles: list[str]) -> str:
    host = roles[0]
    guest = roles[1]
    lines = [
        f"{host}: أهلًا وسهلًا بكم. موضوع حلقتنا اليوم هو: {topic}. سنناقشه بهدوء ووضوح، ونحاول الوصول إلى خطوات عملية.",
        f"{guest}: شكرًا على الاستضافة. هذا موضوع مهم، وأفضل بداية هي أن نفهم المشكلة كما هي، بعيدًا عن التهويل أو الأحكام السريعة.",
        f"{host}: ما الفكرة الأساسية التي ينبغي أن يعرفها المستمع قبل أن يبدأ؟",
        f"{guest}: أن التغيير الحقيقي يبدأ بخطوة صغيرة واضحة، ثم بالاستمرار. القرارات الكبيرة لا تنجح من دون عادات يومية بسيطة.",
    ]
    if len(roles) >= 3:
        lines.extend([
            f"{roles[2]}: وأضيف أن الجانب الإنساني مهم جدًا. يحتاج الشخص إلى فهم ظروفه وقدرته الحالية، ثم يضع خطة واقعية تناسبه.",
            f"{host}: هذه نقطة مهمة. كيف نتجنب الحماس المؤقت ثم التوقف؟",
            f"{roles[2]}: بتحديد هدف قابل للقياس، ومراجعة التقدم كل أسبوع، وعدم معاقبة النفس عند التعثر.",
        ])
    if len(roles) >= 4:
        lines.extend([
            f"{roles[3]}: من الناحية العملية، أنصح بكتابة الأولويات، وتقليل المشتتات، وطلب المشورة عند الحاجة.",
            f"{host}: وما الخطأ الأكثر شيوعًا؟",
            f"{roles[3]}: انتظار الظروف المثالية. البداية الجيدة ليست كاملة، لكنها واضحة وقابلة للاستمرار.",
        ])
    lines.extend([
        f"{host}: نصل الآن إلى الخلاصة. ما الرسالة الأخيرة للمستمع؟",
        f"{guest}: ابدأ بما تستطيع اليوم، واستمر بهدوء، ولا تقارن طريقك بطريق الآخرين.",
        f"{host}: شكرًا لكم، وشكرًا لكل من استمع إلينا. نلتقي في حلقة جديدة من استوديو ابن الواقدي.",
    ])
    return "\n\n".join(lines)


@router.post("/scenario")
async def create_scenario(req: ScenarioRequest):
    roles = FORMATS.get(req.format, FORMATS["host_two_guests"])
    dialect = {
        "yemeni": "يمني طبيعي مفهوم، مع روح يمنية خفيفة دون ألفاظ محلية غامضة",
        "gulf": "خليجي طبيعي راقٍ وسهل الفهم",
        "msa": "فصحى محكية سهلة وغير متكلفة",
    }.get(req.dialect, "فصحى محكية سهلة")
    tone = {
        "calm_powerful": "هادئ وواثق وقوي مثل أفضل البودكاست العربية",
        "emotional": "إنساني مؤثر ودافئ",
        "informative": "معلوماتي واضح واحترافي",
        "energetic": "حيوي وسريع دون صراخ",
    }.get(req.tone, "هادئ وواثق")
    words = max(220, req.duration_minutes * 125)
    prompt = f"""أنت منتج وكاتب بودكاست عربي محترف. أنشئ سيناريو مقابلة جاهزًا للتسجيل.
الموضوع: {req.topic}
الجمهور: {req.audience}
الطول التقريبي: {words} كلمة
اللهجة: {dialect}
النبرة: {tone}
الشخصيات بالترتيب: {', '.join(roles)}

قواعد الإنتاج:
- كل فقرة تبدأ حرفيًا باسم الشخصية ثم نقطتين، مثل: المذيع_رجل: النص
- افتتح بخطاف قصير قوي، ثم تعريف بالموضوع والضيوف.
- اجعل الأسئلة قصيرة وطبيعية، والإجابات متنوعة الطول وليست آلية.
- أضف مقاطعات لطيفة وانتقالات بشرية مثل: صحيح، أتفق، دعني أوضح، وهذه نقطة مهمة؛ دون إفراط.
- لا تكرر الأفكار، ولا تكتب تعليمات أداء أو مؤثرات داخل النص.
- اختم بخلاصة عملية ورسالة يتذكرها المستمع.
- لا تختلق حقائق أو اقتباسات. أعد الحوار فقط."""
    try:
        script = await _ask_gemini(prompt, 0.68)
        return {"success": True, "script": script, "roles": roles, "source": "gemini", "message": "تم إنشاء سيناريو مقابلة بودكاست احترافي."}
    except Exception:
        script = _local_scenario(req.topic, roles)
        return {"success": True, "script": script, "roles": roles, "source": "local_fallback", "message": "تعذر محرر Gemini مؤقتًا؛ تم إنشاء سيناريو محلي مرتب ويمكنك تعديله."}


def _parse(script: str) -> list[tuple[str, str]]:
    segments: list[tuple[str, str]] = []
    role = "المذيع_رجل"
    buf: list[str] = []
    for raw in script.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = re.match(r"^([^:：]{2,50})[:：]\s*(.+)$", line)
        if match:
            if buf:
                segments.append((role, " ".join(buf)))
            role, buf = match.group(1).strip(), [match.group(2).strip()]
        else:
            buf.append(line)
    if buf:
        segments.append((role, " ".join(buf)))
    return [(role, text) for role, text in segments if text.strip()]


def _voice(role: str, engine: str) -> tuple[str, float]:
    low = role.lower()
    female = any(value in low for value in ("امرأة", "فتاة", "ضيفة", "مذيعة"))
    if engine == "edge":
        if female:
            return ("ar-YE-MaryamNeural" if "مذيعة" in low else "ar-SA-ZariyahNeural", 0.98)
        if "خبير" in low:
            return ("ar-AE-HamdanNeural", 0.94)
        if "ضيف" in low:
            return ("ar-SA-HamedNeural", 0.97)
        return ("ar-YE-SalehNeural", 0.95)
    if female:
        return (("Achernar" if "مذيعة" in low else "Sulafat") + "|podcast_natural", 0.98)
    if "خبير" in low:
        return ("Charon|documentary", 0.92)
    if "ضيف" in low:
        return ("Gacrux|podcast_natural", 0.97)
    return ("Kore|podcast_natural", 0.95)


def _silence(path: Path, milliseconds: int) -> None:
    rate = 48000
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(b"\x00\x00" * int(rate * milliseconds / 1000))


def _plain_message(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        for key in ("message", "detail", "error", "reason", "status"):
            if key in value:
                nested = _plain_message(value.get(key))
                if nested:
                    return nested
        try:
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return repr(value)
    if isinstance(value, (list, tuple, set)):
        parts = [_plain_message(item) for item in value]
        return " | ".join(part for part in parts if part)
    return str(value)


def _retry_after_seconds(message: str) -> int:
    patterns = (
        r"retry(?:\s+in|\s+after)?\s*([0-9]+(?:\.[0-9]+)?)\s*s",
        r"بعد\s*(\d+)\s*ث",
        r"(\d+)\s*seconds?",
        r"(\d+)\s*ثانية",
    )
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return max(1, min(600, int(float(match.group(1)) + 1)))
    return 0


def _is_temporary(message: str) -> bool:
    low = message.lower()
    return any(token in low for token in ("429", "rate limit", "resource_exhausted", "temporar", "timeout", "timed out", "connection", "حد مؤقت", "انتظار", "أعد المحاولة", "retry"))


def _job_id(req: RenderRequest) -> str:
    normalized = {
        "script": "\n".join(line.strip() for line in req.script.splitlines() if line.strip()),
        "engine": req.engine,
        "master": req.master,
        "base_speed": round(req.base_speed, 4),
        "pause_ms": req.pause_ms,
    }
    raw = json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:18]


def _write_manifest(work: Path, payload: dict[str, Any]) -> None:
    payload = dict(payload)
    payload["updated_at"] = int(time.time())
    path = work / "progress.json"
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _normalize_audio(source: Path, target: Path, ffmpeg: str) -> None:
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-vn", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "1", str(target)]
    process = subprocess.run(command, capture_output=True, text=True, timeout=600, check=False)
    if process.returncode != 0 or not target.exists() or target.stat().st_size <= 44:
        target.unlink(missing_ok=True)
        raise RuntimeError((process.stderr or "فشل تجهيز ملف المشهد الصوتي")[-1200:])


async def _generate_segments(segments: list[tuple[str, str]], engine: str, base_speed: float, work: Path, ffmpeg: str) -> tuple[list[Path], int]:
    plugin = tts_registry.get_plugin(engine)
    if not plugin:
        raise HTTPException(status_code=503, detail={"message": f"محرك {engine} غير متاح.", "engine": engine})
    files: list[Path] = []
    resumed = 0
    total = len(segments)
    for index, (role, text) in enumerate(segments):
        target = work / f"part_{index:04d}.wav"
        if target.exists() and target.stat().st_size > 44:
            files.append(target)
            resumed += 1
            continue
        voice, role_speed = _voice(role, engine)
        natural_variation = (0.992, 1.0, 1.008, 0.997, 1.004)[index % 5]
        speed = max(0.75, min(1.20, base_speed * role_speed * natural_variation))
        try:
            result = await plugin.generate(text=text, voice=voice, language="ar", speed=speed)
        except Exception as exc:
            result = {"success": False, "message": f"{type(exc).__name__}: {exc}"}
        if not isinstance(result, dict) or not result.get("success"):
            message = _plain_message(result.get("message") if isinstance(result, dict) else result) or f"تعذر إنشاء صوت المتحدث {role}."
            retry_after = _retry_after_seconds(message)
            temporary = _is_temporary(message) or retry_after > 0
            _write_manifest(work, {"status": "waiting" if temporary else "failed", "engine": engine, "completed": len(files), "total": total, "failed_segment": index + 1, "failed_role": role, "retry_after_seconds": retry_after, "message": message})
            raise HTTPException(status_code=429 if temporary else 502, detail={"message": message, "engine": engine, "engine_label": ENGINE_LABELS.get(engine, engine), "completed": len(files), "total": total, "failed_segment": index + 1, "failed_role": role, "retry_after_seconds": retry_after, "temporary": temporary, "resume_supported": True})
        source_text = _plain_message(result.get("file"))
        source = Path(source_text) if source_text else Path()
        if not source_text or not source.exists():
            raise HTTPException(status_code=500, detail={"message": f"المحرك نجح لكن ملف صوت المتحدث {role} غير موجود.", "completed": len(files), "total": total, "failed_segment": index + 1, "failed_role": role, "resume_supported": True})
        try:
            _normalize_audio(source, target, ffmpeg)
        except Exception as exc:
            raise HTTPException(status_code=500, detail={"message": _plain_message(exc), "completed": len(files), "total": total, "failed_segment": index + 1, "failed_role": role, "resume_supported": True}) from exc
        files.append(target)
        _write_manifest(work, {"status": "generating", "engine": engine, "completed": len(files), "total": total, "current_segment": index + 1, "current_role": role, "message": f"تم حفظ المشهد {index + 1} من {total}."})
    return files, resumed


@router.post("/render")
async def render(req: RenderRequest):
    segments = _parse(req.script)
    if not segments:
        raise HTTPException(status_code=400, detail={"message": "اكتب الحوار بصيغة اسم المتحدث: النص"})
    requested = req.engine if req.engine in {"gemini", "edge", "elevenlabs"} else "gemini"
    engine_label = ENGINE_LABELS.get(requested, requested)
    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        raise HTTPException(status_code=500, detail={"message": "FFmpeg غير متاح داخل البرنامج."})
    job_id = _job_id(req)
    work = OUTPUTS_DIR / "interview_jobs" / job_id
    work.mkdir(parents=True, exist_ok=True)
    final = OUTPUTS_DIR / f"ibn_alwaqadi_podcast_{job_id}.mp3"
    raw = OUTPUTS_DIR / f"ibn_alwaqadi_interview_{job_id}.wav"
    if final.exists() and final.stat().st_size > 256:
        target = _desktop_exports() / final.name
        if not target.exists() or target.stat().st_size != final.stat().st_size:
            shutil.copy2(final, target)
        return {"success": True, "url": f"/api/downloads/{final.name}", "desktop_path": str(target), "segments": len(segments), "speakers": len({role for role, _ in segments}), "engine_requested": requested, "engine_used": requested, "fallback": False, "cached": True, "job_id": job_id, "message": "المقابلة جاهزة من الجلسة المحفوظة، ولم تُرسل طلبات صوت جديدة."}
    generated, resumed = await _generate_segments(segments, requested, req.base_speed, work, ffmpeg)
    pause = work / f"pause_{req.pause_ms}.wav"
    if not pause.exists() or pause.stat().st_size <= 44:
        _silence(pause, req.pause_ms)
    files: list[Path] = []
    for index, source in enumerate(generated):
        files.append(source)
        if index < len(generated) - 1:
            files.append(pause)
    concat = work / "concat.txt"
    concat.write_text("\n".join("file '" + str(path).replace("'", "'\\''") + "'" for path in files), encoding="utf-8")
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "1", str(raw)]
    process = subprocess.run(command, capture_output=True, text=True, timeout=1200, check=False)
    if process.returncode != 0 or not raw.exists() or raw.stat().st_size <= 44:
        raise HTTPException(status_code=500, detail={"message": (process.stderr or "فشل دمج المقابلة")[-1200:], "completed": len(generated), "total": len(segments), "resume_supported": True})
    output = final if process_audio(str(raw), str(final), req.master) else raw
    target = _desktop_exports() / output.name
    shutil.copy2(output, target)
    _write_manifest(work, {"status": "completed", "engine": requested, "completed": len(segments), "total": len(segments), "output": str(output), "desktop_path": str(target)})
    resume_note = f" تم استعادة {resumed} مشهد محفوظ." if resumed else ""
    return {"success": True, "url": f"/api/downloads/{output.name}", "desktop_path": str(target), "segments": len(segments), "speakers": len({role for role, _ in segments}), "engine_requested": requested, "engine_used": requested, "fallback": False, "cached": False, "resumed_segments": resumed, "job_id": job_id, "message": f"تم إنتاج المقابلة باستخدام {engine_label} فقط وحفظها على سطح المكتب.{resume_note}"}
