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
    script = await _ask_gemini(prompt, 0.68)
    return {"success": True, "script": script, "roles": roles, "message": "تم إنشاء سيناريو مقابلة بودكاست احترافي."}


def _parse(script: str) -> list[tuple[str, str]]:
    segments: list[tuple[str, str]] = []
    role = "المذيع_رجل"
    buf: list[str] = []
    for raw in script.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^([^:：]{2,50})[:：]\s*(.+)$", line)
        if m:
            if buf:
                segments.append((role, " ".join(buf)))
            role, buf = m.group(1).strip(), [m.group(2).strip()]
        else:
            buf.append(line)
    if buf:
        segments.append((role, " ".join(buf)))
    return [(r, t) for r, t in segments if t.strip()]


def _voice(role: str, engine: str) -> tuple[str, float]:
    r = role.lower()
    female = any(x in r for x in ("امرأة", "فتاة", "ضيفة", "مذيعة"))
    if engine == "edge":
        if female:
            return ("ar-YE-MaryamNeural" if "مذيعة" in r else "ar-SA-ZariyahNeural", 0.98)
        if "خبير" in r:
            return ("ar-AE-HamdanNeural", 0.94)
        if "ضيف" in r:
            return ("ar-SA-HamedNeural", 0.97)
        return ("ar-YE-SalehNeural", 0.95)
    if female:
        return (("Achernar" if "مذيعة" in r else "Sulafat") + "|podcast_natural", 0.98)
    if "خبير" in r:
        return ("Charon|documentary", 0.92)
    if "ضيف" in r:
        return ("Gacrux|podcast_natural", 0.97)
    return ("Kore|podcast_natural", 0.95)


def _silence(path: Path, ms: int) -> None:
    rate = 24000
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(rate)
        f.writeframes(b"\x00\x00" * int(rate * ms / 1000))


@router.post("/render")
async def render(req: RenderRequest):
    segments = _parse(req.script)
    if not segments:
        raise HTTPException(status_code=400, detail="اكتب الحوار بصيغة اسم المتحدث: النص")
    plugin = tts_registry.get_plugin(req.engine)
    if not plugin:
        raise HTTPException(status_code=503, detail="محرك الصوت المحدد غير متاح.")
    token = uuid.uuid4().hex[:10]
    work = OUTPUTS_DIR / f"ibn_alwaqadi_interview_{token}_parts"
    work.mkdir(parents=True, exist_ok=True)
    pause = work / "pause.wav"
    _silence(pause, req.pause_ms)
    files: list[Path] = []
    for idx, (role, text) in enumerate(segments):
        voice, role_speed = _voice(role, req.engine)
        speed = max(0.75, min(1.20, req.base_speed * role_speed))
        result = await plugin.generate(text=text, voice=voice, language="ar", speed=speed)
        if not result or not result.get("success"):
            raise HTTPException(status_code=502, detail=(result or {}).get("message", f"فشل صوت {role}"))
        source = Path(result.get("file", ""))
        if not source.exists():
            raise HTTPException(status_code=500, detail=f"لم يتم العثور على ملف صوت {role}.")
        files.append(source)
        if idx < len(segments) - 1:
            files.append(pause)
    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        raise HTTPException(status_code=500, detail="FFmpeg غير متاح داخل البرنامج.")
    concat = work / "concat.txt"
    concat.write_text("\n".join("file '" + str(p).replace("'", "'\\''") + "'" for p in files), encoding="utf-8")
    raw = OUTPUTS_DIR / f"ibn_alwaqadi_interview_{token}.wav"
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "1", str(raw)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1200, check=False)
    if proc.returncode != 0 or not raw.exists():
        raise HTTPException(status_code=500, detail=(proc.stderr or "فشل دمج المقابلة")[-1200:])
    final = OUTPUTS_DIR / f"ibn_alwaqadi_podcast_{token}.mp3"
    output = final if process_audio(str(raw), str(final), req.master) else raw
    target = _desktop_exports() / output.name
    shutil.copy2(output, target)
    return {"success": True, "url": f"/api/downloads/{output.name}", "desktop_path": str(target), "segments": len(segments), "speakers": len({r for r, _ in segments}), "message": "تم إنتاج مقابلة بشرية بأسلوب بودكاست وحفظها على سطح المكتب."}
