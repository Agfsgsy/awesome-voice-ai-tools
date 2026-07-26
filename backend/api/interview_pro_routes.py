"""Additive professional multi-speaker interview production for Ibn Al-Waqadi Studio."""
from __future__ import annotations

import re
import shutil
import subprocess
import uuid
import wave
from pathlib import Path

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
        return {"success": True, "script": script, "roles": roles, "source": "local_fallback", "message": "حصة محرر Gemini غير متاحة حاليًا؛ تم إنشاء سيناريو احتياطي مرتب داخل الاستوديو ويمكنك تعديله."}


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
    rate = 24000
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(b"\x00\x00" * int(rate * milliseconds / 1000))


async def _generate_segments(segments: list[tuple[str, str]], engine: str, base_speed: float) -> tuple[list[Path], list[str]]:
    plugin = tts_registry.get_plugin(engine)
    if not plugin:
        raise HTTPException(status_code=503, detail=f"محرك {engine} غير متاح.")
    files: list[Path] = []
    errors: list[str] = []
    for index, (role, text) in enumerate(segments):
        voice, role_speed = _voice(role, engine)
        natural_variation = (0.992, 1.0, 1.008, 0.997, 1.004)[index % 5]
        speed = max(0.75, min(1.20, base_speed * role_speed * natural_variation))
        result = await plugin.generate(text=text, voice=voice, language="ar", speed=speed)
        if not result or not result.get("success"):
            errors.append((result or {}).get("message", f"فشل صوت {role}"))
            raise HTTPException(status_code=502, detail=errors[-1])
        source = Path(result.get("file", ""))
        if not source.exists():
            raise HTTPException(status_code=500, detail=f"لم يتم العثور على ملف صوت {role}.")
        files.append(source)
    return files, errors


@router.post("/render")
async def render(req: RenderRequest):
    segments = _parse(req.script)
    if not segments:
        raise HTTPException(status_code=400, detail="اكتب الحوار بصيغة اسم المتحدث: النص")

    requested = req.engine if req.engine in {"gemini", "edge", "elevenlabs"} else "gemini"
    candidates = [requested]
    if requested == "gemini":
        candidates.append("edge")
    elif requested == "elevenlabs":
        candidates.extend(["gemini", "edge"])

    generated: list[Path] = []
    used_engine = requested
    failures: list[str] = []
    for candidate in list(dict.fromkeys(candidates)):
        try:
            generated, _ = await _generate_segments(segments, candidate, req.base_speed)
            used_engine = candidate
            break
        except HTTPException as exc:
            failures.append(f"{candidate}: {exc.detail}")
            generated = []
            continue
    if not generated:
        raise HTTPException(status_code=502, detail="تعذر الإنتاج بالمحركات المتاحة. " + " | ".join(failures[-3:]))

    token = uuid.uuid4().hex[:10]
    work = OUTPUTS_DIR / f"ibn_alwaqadi_interview_{token}_parts"
    work.mkdir(parents=True, exist_ok=True)
    pause = work / "pause.wav"
    _silence(pause, req.pause_ms)
    files: list[Path] = []
    for index, source in enumerate(generated):
        files.append(source)
        if index < len(generated) - 1:
            files.append(pause)

    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        raise HTTPException(status_code=500, detail="FFmpeg غير متاح داخل البرنامج.")
    concat = work / "concat.txt"
    concat.write_text("\n".join("file '" + str(path).replace("'", "'\\''") + "'" for path in files), encoding="utf-8")
    raw = OUTPUTS_DIR / f"ibn_alwaqadi_interview_{token}.wav"
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "1", str(raw)]
    process = subprocess.run(command, capture_output=True, text=True, timeout=1200, check=False)
    if process.returncode != 0 or not raw.exists():
        raise HTTPException(status_code=500, detail=(process.stderr or "فشل دمج المقابلة")[-1200:])
    final = OUTPUTS_DIR / f"ibn_alwaqadi_podcast_{token}.mp3"
    output = final if process_audio(str(raw), str(final), req.master) else raw
    target = _desktop_exports() / output.name
    shutil.copy2(output, target)
    fallback = used_engine != requested
    message = "تم إنتاج مقابلة بشرية بأسلوب بودكاست وحفظها على سطح المكتب."
    if fallback:
        message += " انتهت حصة المحرك المطلوب، فانتقل الاستوديو تلقائيًا إلى الأصوات العربية المجانية دون إيقاف الإنتاج."
    return {"success": True, "url": f"/api/downloads/{output.name}", "desktop_path": str(target), "segments": len(segments), "speakers": len({role for role, _ in segments}), "engine_requested": requested, "engine_used": used_engine, "fallback": fallback, "message": message}
