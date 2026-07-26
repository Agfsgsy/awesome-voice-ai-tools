"""Quota-safe additive renderer for Dialogue Ultra.

It keeps every existing route and adds a resilient endpoint that tries native/premium
providers first, then immediately completes the whole interview with free Arabic voices
when cloud quotas are exhausted.
"""
from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api import dialogue_ultra_routes as dialogue
from backend.api.studio_pro_routes import _desktop_exports
from backend.core.config import OUTPUTS_DIR
from backend.core.tts_registry import tts_registry
from backend.plugins.builtin.audio_effects import process_audio

router = APIRouter(prefix="/api/dialogue-safe", tags=["Dialogue Safe"])


class SafeRenderRequest(BaseModel):
    script: str = Field(min_length=2, max_length=50000)
    provider: str = Field(default="auto", max_length=40)
    master: str = Field(default="podcast_truth", max_length=60)
    dialect: str = Field(default="yemeni", max_length=30)
    tone: str = Field(default="close_mic", max_length=40)
    gemini_model: str = Field(default="gemini-3.1-flash-tts-preview", max_length=80)
    pause_ms: int = Field(default=260, ge=80, le=1000)
    seed: int = Field(default=0, ge=0, le=4294967295)


EDGE_ROLE_VOICES = {
    "المذيع_رجل": ("ar-YE-SalehNeural", 0.94),
    "المذيعة_امرأة": ("ar-YE-MaryamNeural", 0.97),
    "الضيف_رجل": ("ar-SA-HamedNeural", 0.96),
    "الضيفة_امرأة": ("ar-SA-ZariyahNeural", 0.98),
    "الخبير_رجل": ("ar-AE-HamdanNeural", 0.92),
}


def _clean_edge_text(text: str) -> str:
    value = re.sub(r"^\s*\[[^\]]{1,140}\]\s*", "", text.strip())
    value = re.sub(r"\s+", " ", value)
    return value.strip()


async def _edge_contextual(turns: list[tuple[str, str]], pause_ms: int) -> Path:
    plugin = tts_registry.get_plugin("edge")
    if not plugin:
        raise HTTPException(status_code=503, detail="محرك الأصوات العربية المجانية غير متاح.")
    token = uuid.uuid4().hex[:10]
    paths: list[Path] = []
    variations = (0.997, 1.006, 0.992, 1.003, 0.989)
    for index, (role, text) in enumerate(turns):
        canonical = dialogue._canonical_role(role)
        voice, role_speed = EDGE_ROLE_VOICES[canonical]
        speed = max(0.80, min(1.10, role_speed * variations[index % len(variations)]))
        natural_text = _clean_edge_text(text)
        result = await plugin.generate(text=natural_text, voice=voice, language="ar", speed=speed)
        if not result or not result.get("success"):
            raise HTTPException(status_code=502, detail=(result or {}).get("message", f"فشل الصوت الاحتياطي للشخصية {role}"))
        source = Path(result.get("file", ""))
        if not source.exists():
            raise HTTPException(status_code=500, detail=f"ملف الصوت الاحتياطي للشخصية {role} غير موجود.")
        paths.append(source)
    raw = OUTPUTS_DIR / f"ibn_alwaqadi_edge_safe_{token}.wav"
    dialogue._concat_audio(paths, raw, pause_ms)
    return raw


async def _render_provider(provider: str, req: SafeRenderRequest, turns: list[tuple[str, str]], token: str) -> tuple[Path, str]:
    if provider == "eleven_dialogue":
        paths = await dialogue._eleven_dialogue(turns, req.seed)
        raw = OUTPUTS_DIR / f"ibn_alwaqadi_dialogue_v3_{token}.mp3"
        dialogue._concat_audio(paths, raw, max(100, req.pause_ms // 2), force_mp3=True)
        return raw, "eleven_v3"
    if provider == "gemini_native":
        scene_paths: list[Path] = []
        models: list[str] = []
        for index, scene in enumerate(dialogue._scene_chunks(turns)):
            pcm, model, _key_index = await dialogue._gemini_scene_audio(scene, req.tone, req.dialect, req.gemini_model)
            path = OUTPUTS_DIR / f"gemini_native_safe_{token}_{index}.wav"
            dialogue._save_wav(path, pcm)
            scene_paths.append(path)
            models.append(model)
        raw = OUTPUTS_DIR / f"ibn_alwaqadi_gemini_native_safe_{token}.wav"
        dialogue._concat_audio(scene_paths, raw, req.pause_ms)
        return raw, ",".join(dict.fromkeys(models))
    if provider == "legacy_contextual":
        return await dialogue._legacy_contextual(turns, req.pause_ms), "gemini-segmented"
    if provider == "edge_fallback":
        return await _edge_contextual(turns, req.pause_ms), "edge-arabic-neural"
    raise HTTPException(status_code=400, detail="وضع الإنتاج غير معروف.")


def _provider_order(req: SafeRenderRequest, turns: list[tuple[str, str]]) -> list[str]:
    requested = req.provider
    all_ids = all(dialogue._voice_id_for_role(role) for role, _ in turns)
    eleven_ready = bool(dialogue._eleven_api_key() and all_ids)
    if requested == "auto":
        order = (["eleven_dialogue"] if eleven_ready else []) + ["gemini_native", "edge_fallback", "legacy_contextual"]
    elif requested == "eleven_dialogue":
        order = ["eleven_dialogue", "gemini_native", "edge_fallback", "legacy_contextual"]
    elif requested == "gemini_native":
        order = ["gemini_native", "edge_fallback", "legacy_contextual"]
    elif requested == "legacy_contextual":
        order = ["legacy_contextual", "edge_fallback"]
    else:
        order = ["edge_fallback"]
    return list(dict.fromkeys(order))


@router.post("/render")
async def render_safe(req: SafeRenderRequest):
    turns = dialogue._parse(req.script)
    if len(turns) < 2:
        raise HTTPException(status_code=400, detail="يجب أن يحتوي السيناريو على دورين على الأقل.")

    token = uuid.uuid4().hex[:10]
    requested = req.provider
    errors: list[str] = []
    raw: Path | None = None
    used_provider = ""
    model_used = ""
    for provider in _provider_order(req, turns):
        try:
            raw, model_used = await _render_provider(provider, req, turns, token)
            used_provider = provider
            break
        except HTTPException as exc:
            errors.append(f"{provider}: {exc.detail}")
        except Exception as exc:
            errors.append(f"{provider}: {type(exc).__name__}: {str(exc)[:220]}")

    if raw is None or not raw.exists():
        raise HTTPException(status_code=502, detail="تعذر الإنتاج بكل المحركات المتاحة. " + " | ".join(errors[-4:]))

    final = OUTPUTS_DIR / f"ibn_alwaqadi_quota_safe_{token}.mp3"
    output = final if req.master != "none" and process_audio(str(raw), str(final), req.master) else raw
    target = _desktop_exports() / output.name
    shutil.copy2(output, target)
    fallback = used_provider != requested and requested != "auto"
    used_free_fallback = used_provider == "edge_fallback"
    message = "تم إنتاج المقابلة وحفظها على سطح المكتب."
    if used_free_fallback:
        message += " كانت حصة الخدمات السحابية منتهية، فبدأ الاستوديو فورًا بالأصوات العربية المجانية وأكمل المقابلة كاملة."
    elif fallback:
        message += " انتقل الاستوديو تلقائيًا إلى محرك احتياطي بعد تعذر المحرك المطلوب."
    return {
        "success": True,
        "url": f"/api/downloads/{output.name}",
        "desktop_path": str(target),
        "provider_requested": requested,
        "provider": used_provider,
        "model": model_used,
        "fallback": used_free_fallback or fallback,
        "attempt_errors": errors,
        "turns": len(turns),
        "speakers": len({dialogue._canonical_role(role) for role, _ in turns}),
        "message": message,
    }
