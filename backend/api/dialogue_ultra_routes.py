"""Ultra-natural podcast dialogue production using native multi-speaker engines.

This module is additive: it keeps all legacy interview routes and adds:
- Gemini native multi-speaker rendering with conversational context.
- ElevenLabs Text-to-Dialogue v3 for premium multi-speaker podcasts.
- AI script humanization with restrained audio-direction tags.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
import wave
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api.studio_pro_routes import _ask_gemini, _desktop_exports
from backend.core.config import CONFIG_DIR, OUTPUTS_DIR
from backend.core.tts_registry import tts_registry
from backend.plugins.builtin.audio_effects import _ffmpeg_executable, process_audio

router = APIRouter(prefix="/api/dialogue-ultra", tags=["Dialogue Ultra"])
SETTINGS_FILE = CONFIG_DIR / "dialogue_ultra.json"
HUMAN_PRO_FILE = CONFIG_DIR / "human_pro.json"

GEMINI_MODELS = (
    "gemini-3.1-flash-tts-preview",
    "gemini-2.5-pro-preview-tts",
    "gemini-2.5-flash-preview-tts",
)

ROLE_DEFAULTS = {
    "المذيع_رجل": {"alias": "Host", "gemini_voice": "Algieba", "tag": "[warm, calm, close-mic, conversational]"},
    "المذيعة_امرأة": {"alias": "HostWoman", "gemini_voice": "Achernar", "tag": "[warm, clear, close-mic, conversational]"},
    "الضيف_رجل": {"alias": "Guest", "gemini_voice": "Gacrux", "tag": "[thoughtful, relaxed, natural pace]"},
    "الضيفة_امرأة": {"alias": "GuestWoman", "gemini_voice": "Sulafat", "tag": "[warm, sincere, natural pace]"},
    "الخبير_رجل": {"alias": "Expert", "gemini_voice": "Charon", "tag": "[measured, knowledgeable, calm]"},
}


class UltraSettings(BaseModel):
    eleven_api_key: str = Field(default="", max_length=400)
    host_male_voice_id: str = Field(default="", max_length=150)
    host_female_voice_id: str = Field(default="", max_length=150)
    guest_male_voice_id: str = Field(default="", max_length=150)
    guest_female_voice_id: str = Field(default="", max_length=150)
    expert_male_voice_id: str = Field(default="", max_length=150)
    default_provider: str = Field(default="auto", max_length=40)


class HumanizeRequest(BaseModel):
    script: str = Field(min_length=2, max_length=50000)
    dialect: str = Field(default="yemeni", max_length=30)
    tone: str = Field(default="close_mic", max_length=40)
    preserve_facts: bool = True


class RenderUltraRequest(BaseModel):
    script: str = Field(min_length=2, max_length=50000)
    provider: str = Field(default="auto", max_length=40)
    master: str = Field(default="podcast_truth", max_length=60)
    dialect: str = Field(default="yemeni", max_length=30)
    tone: str = Field(default="close_mic", max_length=40)
    gemini_model: str = Field(default="gemini-3.1-flash-tts-preview", max_length=80)
    pause_ms: int = Field(default=260, ge=80, le=1000)
    seed: int = Field(default=0, ge=0, le=4294967295)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
    except Exception:
        pass
    return {}


def _settings() -> dict[str, Any]:
    return _read_json(SETTINGS_FILE)


def _eleven_api_key() -> str:
    own = str(_settings().get("eleven_api_key", "")).strip()
    if own:
        return own
    human = _read_json(HUMAN_PRO_FILE)
    return str(human.get("api_key", "") or os.getenv("ELEVENLABS_API_KEY", "")).strip()


def _gemini_keys() -> list[str]:
    cfg = _read_json(CONFIG_DIR / "gemini.json")
    values: list[str] = []
    values.extend(cfg.get("api_keys") or [])
    if cfg.get("api_key"):
        values.append(cfg["api_key"])
    raw = os.getenv("GEMINI_API_KEYS", "") or os.getenv("GEMINI_API_KEY", "")
    values.extend(re.split(r"[\n,;|]+", raw))
    return list(dict.fromkeys(str(v).strip() for v in values if len(str(v).strip()) >= 20))


def _parse(script: str) -> list[tuple[str, str]]:
    turns: list[tuple[str, str]] = []
    role = "المذيع_رجل"
    buffer: list[str] = []
    for raw in script.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = re.match(r"^([^:：]{2,60})[:：]\s*(.+)$", line)
        if match:
            if buffer:
                turns.append((role, " ".join(buffer).strip()))
            role = match.group(1).strip()
            buffer = [match.group(2).strip()]
        else:
            buffer.append(line)
    if buffer:
        turns.append((role, " ".join(buffer).strip()))
    return [(role, text) for role, text in turns if text]


def _canonical_role(role: str) -> str:
    low = role.lower()
    if "مذيعة" in low:
        return "المذيعة_امرأة"
    if "ضيفة" in low or ("ضيف" in low and any(x in low for x in ("امرأة", "فتاة"))):
        return "الضيفة_امرأة"
    if "خبير" in low:
        return "الخبير_رجل"
    if "ضيف" in low:
        return "الضيف_رجل"
    return "المذيع_رجل"


def _role_meta(role: str) -> dict[str, str]:
    return ROLE_DEFAULTS[_canonical_role(role)]


def _voice_id_for_role(role: str) -> str:
    cfg = _settings()
    key_map = {
        "المذيع_رجل": "host_male_voice_id",
        "المذيعة_امرأة": "host_female_voice_id",
        "الضيف_رجل": "guest_male_voice_id",
        "الضيفة_امرأة": "guest_female_voice_id",
        "الخبير_رجل": "expert_male_voice_id",
    }
    canonical = _canonical_role(role)
    return str(cfg.get(key_map[canonical], "")).strip()


def _tone_notes(tone: str, dialect: str) -> str:
    tones = {
        "close_mic": "intimate close-mic podcast; relaxed confidence; subtle breaths; no announcer voice",
        "calm_deep": "calm, deep and grounded; thoughtful pauses; low emotional exaggeration",
        "human_story": "warm human storytelling; sincere reactions; restrained emotion; natural turn-taking",
        "executive": "premium executive podcast; precise articulation; measured pace; calm authority",
    }
    dialects = {
        "yemeni": "Natural understandable Yemeni Arabic flavor, subtle and never caricatured.",
        "gulf": "Natural polished Gulf Arabic flavor, warm and easy to understand.",
        "msa": "Easy conversational Modern Standard Arabic, never formal or theatrical.",
    }
    return tones.get(tone, tones["close_mic"]) + " " + dialects.get(dialect, dialects["msa"])


def _humanized_turn_text(role: str, text: str, index: int) -> str:
    base_tag = _role_meta(role)["tag"]
    text = re.sub(r"\s+", " ", text).strip()
    if not text.startswith("["):
        if index % 7 == 3:
            base_tag = "[thoughtful, brief natural pause before speaking]"
        elif index % 9 == 5:
            base_tag = "[gently, conversational, slightly slower]"
        text = f"{base_tag} {text}"
    return text


def _gemini_scene_prompt(turns: list[tuple[str, str]], tone: str, dialect: str) -> tuple[str, list[dict[str, str]]]:
    unique: list[str] = []
    for role, _ in turns:
        canonical = _canonical_role(role)
        if canonical not in unique:
            unique.append(canonical)
    if len(unique) > 2:
        raise ValueError("Gemini native multi-speaker supports up to two speakers per scene.")

    lines: list[str] = []
    speech_config: list[dict[str, str]] = []
    for role in unique:
        meta = ROLE_DEFAULTS[role]
        speech_config.append({"speaker": meta["alias"], "voice": meta["gemini_voice"]})
    for index, (role, text) in enumerate(turns):
        meta = _role_meta(role)
        lines.append(f"{meta['alias']}: {_humanized_turn_text(role, text, index)}")

    notes = _tone_notes(tone, dialect)
    prompt = f"""# AUDIO PROFILE
Premium Arabic podcast recorded in a quiet treated studio with close microphones.

# SCENE
A real, calm conversation. The speakers listen to each other and respond naturally.
No background music, no echo, no radio-announcer delivery.

# DIRECTOR'S NOTES
- {notes}
- Preserve every spoken Arabic word and meaning.
- Natural breathing, tiny hesitations and varied sentence rhythm.
- Questions should sound curious; answers should sound considered.
- Avoid robotic cadence, repeated pitch patterns, melodrama, shouting and exaggerated smiles.
- Keep transitions tight; use short realistic silences rather than long dead air.
- Do not read speaker labels aloud.

# TRANSCRIPT
{chr(10).join(lines)}
"""
    return prompt, speech_config


def _scene_chunks(turns: list[tuple[str, str]], max_chars: int = 3500) -> list[list[tuple[str, str]]]:
    chunks: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    roles: set[str] = set()
    chars = 0
    for turn in turns:
        role = _canonical_role(turn[0])
        turn_chars = len(turn[1]) + len(turn[0]) + 4
        new_roles = roles | {role}
        if current and (len(new_roles) > 2 or chars + turn_chars > max_chars):
            chunks.append(current)
            current = []
            roles = set()
            chars = 0
        current.append(turn)
        roles.add(role)
        chars += turn_chars
    if current:
        chunks.append(current)
    return chunks


def _extract_interaction_audio(payload: dict[str, Any]) -> bytes | None:
    output_audio = payload.get("output_audio") or payload.get("outputAudio") or {}
    data = output_audio.get("data")
    if data:
        return base64.b64decode(data)
    outputs = payload.get("outputs") or []
    for item in outputs:
        audio = item.get("audio") or item.get("output_audio") or item.get("outputAudio") or {}
        data = audio.get("data")
        if data:
            return base64.b64decode(data)
    return None


def _save_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(pcm)


async def _gemini_scene_audio(turns: list[tuple[str, str]], tone: str, dialect: str, preferred_model: str) -> tuple[bytes, str, int]:
    keys = _gemini_keys()
    if not keys:
        raise HTTPException(status_code=400, detail="أضف مفتاح Gemini صالحًا أولًا.")
    prompt, speech_config = _gemini_scene_prompt(turns, tone, dialect)
    models = list(dict.fromkeys([preferred_model, *GEMINI_MODELS]))
    errors: list[str] = []
    for key_index, key in enumerate(keys, start=1):
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=30.0)) as client:
            for model in models:
                payload = {"model": model, "input": prompt, "response_format": {"type": "audio"}, "generation_config": {"speech_config": speech_config}}
                try:
                    response = await client.post(
                        "https://generativelanguage.googleapis.com/v1beta/interactions",
                        headers={"x-goog-api-key": key, "Content-Type": "application/json", "Api-Revision": "2026-05-20"},
                        json=payload,
                    )
                    if response.status_code in {401, 403, 429}:
                        errors.append(f"key {key_index}: HTTP {response.status_code}")
                        break
                    if response.status_code in {400, 404}:
                        errors.append(f"{model}: HTTP {response.status_code}")
                        continue
                    response.raise_for_status()
                    pcm = _extract_interaction_audio(response.json())
                    if pcm:
                        return pcm, model, key_index
                    errors.append(f"{model}: no audio")
                except Exception as exc:
                    errors.append(f"{model}: {str(exc)[:160]}")
    raise HTTPException(status_code=502, detail="تعذر إنشاء الحوار الطبيعي عبر Gemini. " + "; ".join(errors[-5:]))


def _silence(path: Path, milliseconds: int) -> None:
    rate = 24000
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(b"\x00\x00" * int(rate * milliseconds / 1000))


def _concat_audio(paths: list[Path], output: Path, pause_ms: int, force_mp3: bool = False) -> None:
    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        raise HTTPException(status_code=500, detail="FFmpeg غير متاح داخل البرنامج.")
    work = output.parent / f".concat_{uuid.uuid4().hex[:8]}"
    work.mkdir(parents=True, exist_ok=True)
    pause = work / "pause.wav"
    _silence(pause, pause_ms)
    concat_paths: list[Path] = []
    for index, path in enumerate(paths):
        concat_paths.append(path)
        if index < len(paths) - 1:
            concat_paths.append(pause)
    manifest = work / "files.txt"
    manifest.write_text("\n".join("file '" + str(path).replace("'", "'\\''") + "'" for path in concat_paths), encoding="utf-8")
    codec = ["-c:a", "libmp3lame", "-b:a", "192k", "-ar", "48000", "-ac", "1"] if force_mp3 or output.suffix.lower() == ".mp3" else ["-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1"]
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), *codec, str(output)]
    completed = subprocess.run(cmd, capture_output=True, text=True, timeout=1500, check=False)
    shutil.rmtree(work, ignore_errors=True)
    if completed.returncode != 0 or not output.exists():
        raise HTTPException(status_code=500, detail=(completed.stderr or "فشل دمج مشاهد الحوار")[-1400:])


def _eleven_chunks(turns: list[tuple[str, str]], max_chars: int = 1900) -> list[list[tuple[str, str]]]:
    chunks: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    total = 0
    for role, text in turns:
        length = len(text) + 40
        if current and total + length > max_chars:
            chunks.append(current)
            current = []
            total = 0
        current.append((role, text))
        total += length
    if current:
        chunks.append(current)
    return chunks


async def _eleven_dialogue(turns: list[tuple[str, str]], seed: int) -> list[Path]:
    api_key = _eleven_api_key()
    if not api_key:
        raise HTTPException(status_code=400, detail="أضف مفتاح ElevenLabs أولًا لاستخدام Text to Dialogue v3.")
    missing = sorted({_canonical_role(role) for role, _ in turns if not _voice_id_for_role(role)})
    if missing:
        raise HTTPException(status_code=400, detail="أدخل Voice ID لكل شخصية مستخدمة. الناقص: " + "، ".join(missing))
    outputs: list[Path] = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(360.0, connect=30.0)) as client:
        for chunk_index, chunk in enumerate(_eleven_chunks(turns)):
            inputs = [{"text": _humanized_turn_text(role, text, index), "voice_id": _voice_id_for_role(role)} for index, (role, text) in enumerate(chunk)]
            payload = {"inputs": inputs, "model_id": "eleven_v3", "language_code": "ar", "seed": seed or int(hashlib.sha256(str(inputs).encode()).hexdigest()[:8], 16), "apply_text_normalization": "auto"}
            response = await client.post(
                "https://api.elevenlabs.io/v1/text-to-dialogue",
                params={"output_format": "mp3_44100_128"},
                headers={"xi-api-key": api_key, "Content-Type": "application/json"},
                json=payload,
            )
            if response.status_code >= 400:
                try:
                    body = response.json()
                    detail = body.get("detail") if isinstance(body, dict) else body
                except Exception:
                    detail = response.text[:1000]
                raise HTTPException(status_code=502, detail=f"ElevenLabs Dialogue: {detail}")
            path = OUTPUTS_DIR / f"eleven_dialogue_{uuid.uuid4().hex[:10]}_{chunk_index}.mp3"
            path.write_bytes(response.content)
            if path.stat().st_size < 1000:
                raise HTTPException(status_code=502, detail="رجع ElevenLabs ملفًا صوتيًا فارغًا.")
            outputs.append(path)
    return outputs


async def _legacy_contextual(turns: list[tuple[str, str]], pause_ms: int) -> Path:
    plugin = tts_registry.get_plugin("gemini")
    if not plugin:
        raise HTTPException(status_code=503, detail="محرك Gemini غير متاح.")
    token = uuid.uuid4().hex[:10]
    paths: list[Path] = []
    for index, (role, text) in enumerate(turns):
        meta = _role_meta(role)
        result = await plugin.generate(text=_humanized_turn_text(role, text, index), voice=f"{meta['gemini_voice']}|podcast_natural", language="ar", speed=0.96)
        if not result or not result.get("success"):
            raise HTTPException(status_code=502, detail=(result or {}).get("message", f"فشل صوت {role}"))
        source = Path(result.get("file", ""))
        if not source.exists():
            raise HTTPException(status_code=500, detail=f"ملف صوت {role} غير موجود.")
        paths.append(source)
    raw = OUTPUTS_DIR / f"legacy_ultra_{token}.wav"
    _concat_audio(paths, raw, pause_ms)
    return raw


@router.get("/settings")
async def get_settings():
    data = _settings()
    return {"success": True, "eleven_api_key_set": bool(_eleven_api_key()), "host_male_voice_id": data.get("host_male_voice_id", ""), "host_female_voice_id": data.get("host_female_voice_id", ""), "guest_male_voice_id": data.get("guest_male_voice_id", ""), "guest_female_voice_id": data.get("guest_female_voice_id", ""), "expert_male_voice_id": data.get("expert_male_voice_id", ""), "default_provider": data.get("default_provider", "auto")}


@router.post("/settings")
async def save_settings(req: UltraSettings):
    previous = _settings()
    api_key = req.eleven_api_key.strip() or str(previous.get("eleven_api_key", "")).strip()
    data = {"eleven_api_key": api_key, "host_male_voice_id": req.host_male_voice_id.strip(), "host_female_voice_id": req.host_female_voice_id.strip(), "guest_male_voice_id": req.guest_male_voice_id.strip(), "guest_female_voice_id": req.guest_female_voice_id.strip(), "expert_male_voice_id": req.expert_male_voice_id.strip(), "default_provider": req.default_provider.strip() or "auto"}
    for key, value in data.items():
        if key.endswith("_voice_id") and value and len(value) < 8:
            raise HTTPException(status_code=400, detail=f"{key} غير صحيح.")
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"success": True, "message": "تم حفظ إعدادات المقابلات فائقة الواقعية على هذا الجهاز."}


@router.post("/humanize")
async def humanize(req: HumanizeRequest):
    dialect = {"yemeni": "يمني طبيعي مفهوم، خفيف وغير متكلف", "gulf": "خليجي طبيعي راقٍ وسهل", "msa": "فصحى محكية بسيطة"}.get(req.dialect, "فصحى محكية بسيطة")
    tone = {"close_mic": "بودكاست قريب من الميكروفون، هادئ وحميم", "calm_deep": "هادئ وعميق ومتزن", "human_story": "إنساني قصصي دافئ", "executive": "احترافي رزين ودقيق"}.get(req.tone, "بودكاست هادئ")
    prompt = f"""أنت مخرج حوار صوتي عربي بمستوى استوديو عالمي.
حرّر السيناريو التالي ليبدو كحديث حقيقي لا كقراءة مكتوبة.

اللهجة: {dialect}
الأسلوب: {tone}

قواعد صارمة:
- حافظ على الحقائق والمعنى ولا تضف ادعاءات جديدة.
- أبقِ أسماء المتحدثين وصيغة: اسم_المتحدث: النص.
- نوّع طول الجمل والأدوار، واجعل الأسئلة قصيرة والإجابات طبيعية.
- أضف باعتدال كلمات وصل بشرية مثل: صحيح، بالضبط، لحظة، دعني أوضح، وهذه نقطة مهمة.
- استخدم الحذف والنقاط الثلاث نادرًا فقط عندما يخدم التردد الطبيعي.
- أضف في بداية بعض الأدوار وسم أداء إنجليزيًا قصيرًا مثل [warmly] أو [thoughtful] أو [curious]، ولا تضع أكثر من وسم واحد في الدور.
- لا تضف ضحكًا أو تنهدًا إلا إذا كان مناسبًا جدًا للمعنى.
- تجنب الخطابة والصراخ والتكرار والمبالغة العاطفية.
- لا تغيّر الآيات أو الأحاديث أو الاقتباسات.
- أعد السيناريو فقط.

السيناريو:
{req.script}"""
    result = await _ask_gemini(prompt, 0.48)
    return {"success": True, "script": result, "message": "تم تحويل السيناريو إلى حوار أكثر طبيعية وهدوءًا."}


@router.post("/render")
async def render_ultra(req: RenderUltraRequest):
    turns = _parse(req.script)
    if len(turns) < 2:
        raise HTTPException(status_code=400, detail="يجب أن يحتوي السيناريو على دورين على الأقل.")
    provider = req.provider
    if provider == "auto":
        all_ids = all(_voice_id_for_role(role) for role, _ in turns)
        provider = "eleven_dialogue" if _eleven_api_key() and all_ids else "gemini_native"
    token = uuid.uuid4().hex[:10]
    used_provider = provider
    model_used = ""
    if provider == "eleven_dialogue":
        paths = await _eleven_dialogue(turns, req.seed)
        raw = OUTPUTS_DIR / f"ibn_alwaqadi_dialogue_v3_{token}.mp3"
        _concat_audio(paths, raw, max(100, req.pause_ms // 2), force_mp3=True)
        model_used = "eleven_v3"
    elif provider == "gemini_native":
        scene_paths: list[Path] = []
        models: list[str] = []
        for index, scene in enumerate(_scene_chunks(turns)):
            pcm, model, _key_index = await _gemini_scene_audio(scene, req.tone, req.dialect, req.gemini_model)
            path = OUTPUTS_DIR / f"gemini_native_scene_{token}_{index}.wav"
            _save_wav(path, pcm)
            scene_paths.append(path)
            models.append(model)
        raw = OUTPUTS_DIR / f"ibn_alwaqadi_gemini_native_{token}.wav"
        _concat_audio(scene_paths, raw, req.pause_ms)
        model_used = ",".join(dict.fromkeys(models))
    else:
        raw = await _legacy_contextual(turns, req.pause_ms)
        used_provider = "legacy_contextual"
        model_used = "gemini-segmented"
    final = OUTPUTS_DIR / f"ibn_alwaqadi_true_podcast_{token}.mp3"
    output = final if req.master != "none" and process_audio(str(raw), str(final), req.master) else raw
    target = _desktop_exports() / output.name
    shutil.copy2(output, target)
    return {"success": True, "url": f"/api/downloads/{output.name}", "desktop_path": str(target), "provider": used_provider, "model": model_used, "turns": len(turns), "speakers": len({_canonical_role(role) for role, _ in turns}), "message": "تم إنتاج المقابلة بوضع الحوار الطبيعي وحفظها على سطح المكتب."}
