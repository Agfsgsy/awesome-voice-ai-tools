"""منطق تنفيذ وظائف الاستنساخ والقراءة والاستوديو بعيدًا عن طبقة HTTP."""

from __future__ import annotations

import asyncio
import hashlib
import shutil
from pathlib import Path
from typing import Any

from backend.core.config import OUTPUTS_DIR
from backend.core.model_manager import model_manager
from backend.core.tts_engine import tts
from backend.core.tts_registry import tts_registry
from backend.mobile.audio import (
    analyze_audio,
    apply_vocal_style,
    concatenate_audio,
    convert_audio,
    mix_audio,
)
from backend.mobile.documents import extract_document, normalize_text_for_speech, split_text
from backend.mobile.files import mobile_file_store
from backend.mobile.jobs import JobContext
from backend.mobile.providers import synthesize_elevenlabs, synthesize_gemini


class MobileOperationError(RuntimeError):
    """فشل عملية صوتية مع رسالة صالحة للواجهة العربية."""


def _safe_output_name(prefix: str, identifier: str, index: int, extension: str = ".wav") -> Path:
    digest = hashlib.sha256(f"{identifier}:{index}".encode()).hexdigest()[:14]
    return OUTPUTS_DIR / f"{prefix}_{digest}{extension}"


async def synthesize_text(
    *,
    text: str,
    engine: str,
    language: str,
    voice: str,
    speed: float,
    output_hint: str,
    index: int,
    gemini_key: str | None = None,
    gemini_model: str | None = None,
    elevenlabs_key: str | None = None,
    elevenlabs_model: str | None = None,
) -> Path:
    selected = (engine or "auto").strip().lower()
    if selected == "elevenlabs":
        output = _safe_output_name(output_hint, text, index, ".mp3")
        return await synthesize_elevenlabs(
            text=text,
            api_key=elevenlabs_key or "",
            voice_id=voice,
            model_id=elevenlabs_model or "eleven_multilingual_v2",
            output_path=output,
        )
    if selected == "gemini" and gemini_key:
        output = _safe_output_name(output_hint, text, index)
        return await synthesize_gemini(
            text=text,
            api_key=gemini_key,
            voice_name=voice,
            model_id=gemini_model or "gemini-3.1-flash-tts-preview",
            output_path=output,
        )

    if selected == "auto":
        selected = tts_registry.auto_select_engine() or "auto"
    if selected == "coqui":
        selected = "xtts"

    if selected in {"xtts", "bark", "gemini", "kokoro"}:
        result = await tts.synthesize(
            text=text,
            engine=selected,
            language=language,
            voice=voice,
            speed=speed,
        )
    else:
        plugin = tts_registry.get_plugin(selected)
        if not plugin:
            raise MobileOperationError("المحرك غير جاهز أو غير معروف")
        result = await plugin.generate(text=text, voice=voice, language=language, speed=speed)
    if not result.get("success") or not result.get("file"):
        message = str(result.get("message") or "المحرك غير جاهز")
        if "download" in message.lower():
            message = "النموذج قيد التنزيل أو لم يكتمل تجهيزه"
        raise MobileOperationError(message)
    path = Path(str(result["file"])).expanduser().resolve()
    if not path.is_file() or path.stat().st_size < 44:
        raise MobileOperationError("الملف الناتج غير صالح")
    unique_output = _safe_output_name(output_hint, f"{text}:{path}:{index}", index, path.suffix or ".wav")
    if path != unique_output:
        shutil.copy2(path, unique_output)
    return unique_output


async def clone_voice_job(
    context: JobContext,
    *,
    reference_file_id: str,
    text: str,
    engine: str,
    language: str,
    candidate_count: int,
) -> dict[str, Any]:
    _, source = mobile_file_store.resolve_file_id(reference_file_id)
    await context.update(5, "جارٍ تحليل التسجيل المرجعي")
    analysis = await asyncio.to_thread(analyze_audio, source)
    if not analysis["clear_speech"]:
        raise MobileOperationError("التسجيل لا يحتوي كلامًا واضحًا")
    normalized_reference = OUTPUTS_DIR / f"reference_{context.job_id}.wav"
    await asyncio.to_thread(convert_audio, source, normalized_reference, 24000)
    await context.update(15, "تم تجهيز التسجيل المرجعي")

    selected_engine = "xtts" if engine.lower() in {"coqui", "xtts", "auto"} else engine.lower()
    candidates: list[dict[str, Any]] = []
    for index in range(candidate_count):
        context.raise_if_cancelled()
        progress = 18 + int((index / max(1, candidate_count)) * 70)
        await context.update(progress, f"جارٍ إنشاء المرشح {index + 1} من {candidate_count}")
        result = await tts.clone_voice(
            reference_audio_path=str(normalized_reference),
            text=text,
            engine=selected_engine,
            language=language,
        )
        if not result.get("success") or not result.get("file"):
            raise MobileOperationError(str(result.get("message") or "فشل استنساخ الصوت"))
        generated = Path(str(result["file"])).resolve()
        if not generated.is_file():
            raise MobileOperationError("الملف الناتج غير صالح")
        candidate_path = _safe_output_name("mobile_clone", f"{context.job_id}:{generated}", index)
        shutil.copy2(generated, candidate_path)
        candidate_analysis = await asyncio.to_thread(analyze_audio, candidate_path)
        file_id = mobile_file_store.encode_file_id("output", candidate_path.name)
        candidates.append(
            {
                "candidate_id": f"{context.job_id}-{index + 1}",
                "file_id": file_id,
                "name": candidate_path.name,
                "url": f"/api/mobile/files/{file_id}",
                "quality_score": candidate_analysis["quality_score"],
                "duration_seconds": candidate_analysis["duration_seconds"],
            }
        )
    normalized_reference.unlink(missing_ok=True)
    best = max(candidates, key=lambda item: item["quality_score"])
    await context.update(92, "تم تقييم المرشحين واختيار النتيجة الأعلى جودة")
    return {"candidates": candidates, "best_candidate_id": best["candidate_id"], "reference_analysis": analysis}


async def prepare_engine_job(context: JobContext, *, engine: str, model_name: str) -> dict[str, Any]:
    normalized = "coqui" if engine.lower() in {"xtts", "coqui"} else engine.lower()
    plugin = tts_registry.get_plugin(normalized)
    if not plugin:
        raise MobileOperationError("المحرك غير معروف")
    await context.update(5, "جارٍ فحص المحرك")
    installed = await asyncio.to_thread(plugin.check)
    if not installed:
        await context.update(12, "جارٍ تثبيت اعتماديات المحرك")
        install_result = await asyncio.to_thread(plugin.install)
        if not install_result.get("success"):
            raise MobileOperationError(str(install_result.get("message") or "فشل تثبيت المحرك"))
    await context.update(30, "بدأ تنزيل النموذج؛ قد يستغرق ذلك عدة دقائق")
    selected_model = model_name
    if normalized == "coqui" and model_name == "default":
        selected_model = "xtts_v2"
    download = asyncio.create_task(
        asyncio.to_thread(model_manager.download_model, normalized, selected_model),
        name=f"mobile-model-download-{context.job_id}",
    )
    elapsed_seconds = 0
    try:
        while not download.done():
            done, _ = await asyncio.wait({download}, timeout=2)
            if done:
                break
            elapsed_seconds += 2
            await context.update(
                min(88, 30 + elapsed_seconds // 3),
                f"النموذج قيد التنزيل منذ {elapsed_seconds} ثانية",
            )
        result = await download
    except asyncio.CancelledError:
        download.cancel()
        raise
    if not result.get("success"):
        raise MobileOperationError(str(result.get("message") or "فشل تنزيل النموذج"))
    await context.update(95, "تم تنزيل النموذج ويجري التحقق منه")
    tts.refresh_engines()
    return {"engine": normalized, "model": selected_model, "download": result, "health": plugin.health()}


async def read_document_job(
    context: JobContext,
    *,
    document_path: Path,
    engine: str,
    language: str,
    voice: str,
    speed: float,
    normalize_numbers: bool,
    gemini_key: str | None,
    gemini_model: str | None,
    elevenlabs_key: str | None,
    elevenlabs_model: str | None,
) -> dict[str, Any]:
    await context.update(4, "جارٍ استخراج نص المستند")
    text = await asyncio.to_thread(extract_document, document_path)
    if normalize_numbers:
        text = normalize_text_for_speech(text)
    chunks = split_text(text)
    generated: list[Path] = []
    for index, chunk in enumerate(chunks):
        context.raise_if_cancelled()
        progress = 8 + int((index / max(1, len(chunks))) * 78)
        await context.update(progress, f"جارٍ قراءة المقطع {index + 1} من {len(chunks)}")
        generated.append(
            await synthesize_text(
                text=chunk,
                engine=engine,
                language=language,
                voice=voice,
                speed=speed,
                output_hint="document_part",
                index=index,
                gemini_key=gemini_key,
                gemini_model=gemini_model,
                elevenlabs_key=elevenlabs_key,
                elevenlabs_model=elevenlabs_model,
            )
        )
    await context.update(90, "جارٍ دمج المقاطع الصوتية")
    output = _safe_output_name("mobile_document", context.job_id, 0)
    await asyncio.to_thread(concatenate_audio, generated, output)
    file_id = mobile_file_store.encode_file_id("output", output.name)
    return {
        "file_id": file_id,
        "name": output.name,
        "url": f"/api/mobile/files/{file_id}",
        "characters": len(text),
        "chunks": len(chunks),
    }


async def generate_song_job(
    context: JobContext,
    *,
    lyrics: str,
    title: str,
    style: str,
    engine: str,
    language: str,
    voice: str,
    candidate_count: int,
    tempo: float,
    pitch_semitones: float,
    reverb: float,
    instrumental_file_id: str | None,
    gemini_key: str | None,
    gemini_model: str | None,
    elevenlabs_key: str | None,
    elevenlabs_model: str | None,
) -> dict[str, Any]:
    instrumental: Path | None = None
    if instrumental_file_id:
        _, instrumental = mobile_file_store.resolve_file_id(instrumental_file_id)
    prompt = f"أدِّ النص بأسلوب {style} وبإيقاع واضح، مع الالتزام الحرفي بالكلمات التالية:\n{lyrics}"
    candidates: list[dict[str, Any]] = []
    for index in range(candidate_count):
        context.raise_if_cancelled()
        await context.update(
            5 + int(index / max(1, candidate_count) * 75), f"جارٍ إنشاء أداء {index + 1} من {candidate_count}"
        )
        raw = await synthesize_text(
            text=prompt,
            engine=engine,
            language=language,
            voice=voice,
            speed=1.0,
            output_hint="song_raw",
            index=index,
            gemini_key=gemini_key,
            gemini_model=gemini_model,
            elevenlabs_key=elevenlabs_key,
            elevenlabs_model=elevenlabs_model,
        )
        styled = _safe_output_name("mobile_song_vocal", f"{context.job_id}:{title}", index)
        await asyncio.to_thread(
            apply_vocal_style,
            raw,
            styled,
            tempo=tempo,
            pitch_semitones=pitch_semitones,
            reverb=reverb,
        )
        final = styled
        if instrumental is not None:
            final = _safe_output_name("mobile_song_mix", f"{context.job_id}:{title}", index)
            await asyncio.to_thread(mix_audio, styled, instrumental, final)
        analysis = await asyncio.to_thread(analyze_audio, final)
        file_id = mobile_file_store.encode_file_id("output", final.name)
        candidates.append(
            {
                "candidate_id": f"{context.job_id}-{index + 1}",
                "file_id": file_id,
                "name": final.name,
                "url": f"/api/mobile/files/{file_id}",
                "quality_score": analysis["quality_score"],
                "duration_seconds": analysis["duration_seconds"],
            }
        )
    best = max(candidates, key=lambda item: item["quality_score"])
    await context.update(94, "تم تقييم النتائج")
    return {"title": title, "style": style, "candidates": candidates, "best_candidate_id": best["candidate_id"]}
