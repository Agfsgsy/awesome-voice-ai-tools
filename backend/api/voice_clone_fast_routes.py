"""Fast and resilient consent-based voice cloning for Voice Clone Pro.

This additive router keeps the existing profiles, samples, consent records, UI, and
legacy endpoints untouched. It adds:
- automatic provider selection (ElevenLabs -> Gemini Vertex allowlisted replication -> XTTS),
- optimized 10-30 second reference clips so long source files do not stall XTTS,
- bounded provider timeouts and clear attempt reporting,
- optional true Gemini-TTS voice replication through Vertex AI when the account is allowlisted.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import uuid
import wave
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api import voice_clone_routes as clone
from backend.core.config import OUTPUTS_DIR
from backend.core.logger import get_logger
from backend.core.provider_settings import provider_config
from backend.plugins.builtin.audio_effects import _ffmpeg_executable

router = APIRouter(prefix="/api/voice-clone-fast", tags=["Voice Clone Fast"])
logger = get_logger("voice_clone_fast")

MODEL_MARKER = clone.ENGINE_DIR / "xtts_model_ready.json"
LOCAL_TIMEOUT_SECONDS = 1200
MAX_REFERENCE_SECONDS = 30.0


class FastGenerateRequest(BaseModel):
    profile_id: str = Field(min_length=8, max_length=80)
    text: str = Field(min_length=2, max_length=clone.MAX_TEXT)
    provider: Literal["auto", "local", "elevenlabs", "gemini_vertex"] = "auto"
    language: str = Field(default="ar", pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
    speed: float = Field(default=1.0, ge=0.75, le=1.20)
    style: Literal["natural", "warm", "emotional", "broadcast", "story"] = "natural"


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


def _valid_audio(path: Path | None, minimum: int = 1024) -> bool:
    return bool(path and path.exists() and path.is_file() and path.stat().st_size >= minimum)


def _reference_paths(profile_id: str, manifest: dict[str, Any]) -> list[Path]:
    """Create cached short references; never alter or delete original/processed samples."""
    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        raise RuntimeError("FFmpeg غير متاح لتجهيز عينة الاستنساخ السريعة.")

    profile = clone._profile_path(profile_id)
    processed = profile / "processed"
    references = profile / "optimized_references"
    references.mkdir(parents=True, exist_ok=True)
    records = list(manifest.get("samples") or [])
    if not records:
        raise RuntimeError("ملف الصوت لا يحتوي عينات معالجة.")

    remaining = MAX_REFERENCE_SECONDS
    result: list[Path] = []
    count = len(records)
    for index, item in enumerate(records, start=1):
        if remaining < 3.0:
            break
        source = processed / str(item.get("processed_file") or "")
        if not _valid_audio(source):
            continue
        duration = max(0.0, float(item.get("duration") or 0.0))
        if duration < 3.0:
            continue
        target_length = min(25.0 if count == 1 else 12.0, remaining, duration)
        if target_length < 3.0:
            continue
        start = 0.0
        if duration > target_length + 4.0:
            start = min(5.0, max(1.0, duration * 0.08))
        target = references / f"reference_{index}_{int(round(target_length))}s.wav"
        if not _valid_audio(target):
            completed = clone._run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-ss",
                    f"{start:.3f}",
                    "-i",
                    str(source),
                    "-t",
                    f"{target_length:.3f}",
                    "-vn",
                    "-ar",
                    "24000",
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    str(target),
                ],
                timeout=300,
            )
            if completed.returncode != 0 or not _valid_audio(target):
                target.unlink(missing_ok=True)
                raise RuntimeError((completed.stderr or completed.stdout or "تعذر إنشاء العينة المختصرة")[-1600:])
        result.append(target)
        remaining -= target_length

    if not result:
        raise RuntimeError("تعذر إنشاء عينة مرجعية قصيرة وصالحة.")
    return result


def _parse_worker(completed, raw_output: Path) -> str:
    if completed.returncode != 0 or not _valid_audio(raw_output):
        detail = (completed.stdout or completed.stderr or "فشل XTTS")[-3200:]
        try:
            parsed = json.loads((completed.stdout or "").strip().splitlines()[-1])
            detail = str(parsed.get("error") or detail)
        except Exception:
            pass
        raise RuntimeError(detail)
    try:
        parsed = json.loads((completed.stdout or "").strip().splitlines()[-1])
        return str(parsed.get("device") or "cpu")
    except Exception:
        return "cpu"


def _local_generate_fast(
    profile_id: str,
    manifest: dict[str, Any],
    references: list[Path],
    text: str,
    language: str,
    raw_output: Path,
) -> str:
    python = clone._engine_python()
    if not python.exists() or not clone.WORKER_FILE.exists():
        raise RuntimeError("المحرك المحلي غير مجهز. اضغط تجهيز XTTS مرة واحدة.")
    job = {
        "text": text,
        "language": language,
        "samples": [str(path) for path in references],
        "output": str(raw_output),
    }
    job_path = clone.ENGINE_DIR / f"fast_job_{uuid.uuid4().hex[:12]}.json"
    job_path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    cpu_threads = str(max(2, min(8, os.cpu_count() or 4)))
    env = {
        **os.environ,
        "COQUI_TOS_AGREED": "1",
        "PYTHONUTF8": "1",
        "OMP_NUM_THREADS": cpu_threads,
        "MKL_NUM_THREADS": cpu_threads,
        "TOKENIZERS_PARALLELISM": "false",
    }
    try:
        completed = clone._run(
            [str(python), str(clone.WORKER_FILE), str(job_path)],
            timeout=LOCAL_TIMEOUT_SECONDS,
            env=env,
        )
    except Exception as exc:
        raw_output.unlink(missing_ok=True)
        if "timed out" in str(exc).lower() or "timeout" in str(exc).lower():
            raise RuntimeError("انتهت مهلة XTTS بعد 20 دقيقة. استخدم الوضع التلقائي أو ElevenLabs، أو أعد تجهيز النموذج المحلي.") from exc
        raise
    finally:
        job_path.unlink(missing_ok=True)
    return _parse_worker(completed, raw_output)


async def _ensure_eleven_voice_fast(
    profile_id: str,
    manifest: dict[str, Any],
    references: list[Path],
    api_key: str,
) -> str:
    existing = str(manifest.get("elevenlabs_voice_id") or "").strip()
    if existing:
        return existing
    handles = [path.open("rb") for path in references]
    try:
        files = [("files", (path.name, handle, "audio/wav")) for path, handle in zip(references, handles)]
        data = {
            "name": f"IbnWaqadi-{manifest.get('name', profile_id)}-{profile_id[:5]}",
            "description": "Consent-based synthetic voice profile created in Ibn Al-Waqadi Studio.",
            "remove_background_noise": "false",
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=30.0)) as client:
            response = await client.post(
                "https://api.elevenlabs.io/v1/voices/add",
                headers={"xi-api-key": api_key},
                data=data,
                files=files,
            )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=response.status_code,
                detail="تعذر إنشاء نسخة ElevenLabs: " + clone._eleven_error(response),
            )
        voice_id = str(response.json().get("voice_id") or "").strip()
        if not voice_id:
            raise HTTPException(status_code=502, detail="لم تُرجع ElevenLabs معرف الصوت المستنسخ.")
        manifest["elevenlabs_voice_id"] = voice_id
        manifest["elevenlabs_created_at"] = clone._now()
        clone._save_manifest(profile_id, manifest)
        return voice_id
    finally:
        for handle in handles:
            handle.close()


async def _eleven_generate_fast(
    profile_id: str,
    manifest: dict[str, Any],
    references: list[Path],
    text: str,
    raw_output: Path,
) -> str:
    settings = clone._human_settings()
    api_key = settings["api_key"]
    if not api_key:
        raise HTTPException(status_code=400, detail="مفتاح ElevenLabs غير موجود في Human Pro.")
    await _ensure_eleven_voice_fast(profile_id, manifest, references, api_key)
    return await clone._eleven_generate(profile_id, manifest, text, raw_output)


def _gemini_config() -> dict[str, str]:
    values = provider_config("google_cloud")
    return {
        "project_id": str(values.get("project_id") or os.getenv("GOOGLE_CLOUD_PROJECT", "")).strip(),
        "service_account_json": str(values.get("service_account_json") or "").strip(),
        "model_id": str(values.get("model_id") or "gemini-2.5-flash-tts-eap-11-2025").strip(),
    }


def _gemini_capability() -> tuple[bool, str]:
    config = _gemini_config()
    if not config["project_id"]:
        return False, "أضف Google Cloud Project ID وبيانات حساب الخدمة أولًا."
    if not config["service_account_json"] and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip():
        return False, "يلزم حساب خدمة Google Cloud أو Application Default Credentials."
    try:
        import google.auth  # noqa: F401
        from google.auth.transport.requests import Request  # noqa: F401
    except Exception:
        return False, "مكتبة google-auth غير مثبتة في هذه النسخة."
    return True, "جاهز تقنيًا؛ يلزم أن يكون مشروع Google مقبولًا في قائمة Voice Replication."


def _google_access_token() -> tuple[str, str]:
    import google.auth
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    config = _gemini_config()
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    raw = config["service_account_json"]
    project_id = config["project_id"]
    if raw:
        candidate = Path(raw).expanduser()
        if candidate.exists() and candidate.is_file():
            credentials = service_account.Credentials.from_service_account_file(str(candidate), scopes=scopes)
        else:
            credentials = service_account.Credentials.from_service_account_info(json.loads(raw), scopes=scopes)
    else:
        credentials, detected_project = google.auth.default(scopes=scopes)
        project_id = project_id or str(detected_project or "")
    credentials.refresh(Request())
    if not credentials.token or not project_id:
        raise RuntimeError("تعذر الحصول على رمز Google Cloud أو Project ID.")
    return str(credentials.token), project_id


def _write_pcm_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(pcm)


async def _gemini_generate(
    references: list[Path],
    text: str,
    raw_output: Path,
) -> str:
    ready, reason = _gemini_capability()
    if not ready:
        raise HTTPException(status_code=400, detail="Gemini Voice Replication غير جاهز: " + reason)
    token, project_id = await asyncio.to_thread(_google_access_token)
    config = _gemini_config()
    encoded = base64.b64encode(references[0].read_bytes()).decode("ascii")
    payload = {
        "contents": {
            "role": "user",
            "parts": [{"text": "Say the following exactly: " + text}],
        },
        "generation_config": {
            "response_modalities": ["AUDIO"],
            "speech_config": {
                "voice_config": {
                    "replicated_voice_config": {
                        "voice_sample_audio": encoded,
                    }
                }
            },
        },
    }
    endpoint = (
        f"https://aiplatform.googleapis.com/v1/projects/{project_id}/locations/global/"
        f"publishers/google/models/{config['model_id']}:generateContent"
    )
    async with httpx.AsyncClient(timeout=httpx.Timeout(360.0, connect=30.0)) as client:
        response = await client.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {token}",
                "x-goog-user-project": project_id,
                "Content-Type": "application/json",
            },
            json=payload,
        )
    if response.status_code >= 400:
        detail = response.text[:1400]
        try:
            detail = str((response.json().get("error") or {}).get("message") or detail)
        except Exception:
            pass
        if response.status_code in {401, 403, 404}:
            detail = "المشروع غير مصرح له بميزة Gemini Voice Replication أو بيانات Google Cloud غير صحيحة. " + detail
        raise HTTPException(status_code=response.status_code, detail=detail)
    try:
        part = response.json()["candidates"][0]["content"]["parts"][0]
        inline = part.get("inlineData") or part.get("inline_data") or {}
        pcm = base64.b64decode(inline.get("data") or "")
    except Exception as exc:
        raise HTTPException(status_code=502, detail="لم ترجع Gemini بيانات صوت مستنسخ صالحة.") from exc
    if len(pcm) < 1024:
        raise HTTPException(status_code=502, detail="بيانات Gemini الصوتية فارغة أو قصيرة.")
    await asyncio.to_thread(_write_pcm_wav, raw_output, pcm)
    return config["model_id"]


def _provider_order(requested: str) -> list[str]:
    if requested != "auto":
        return [requested]
    result: list[str] = []
    if clone._human_settings()["api_key"]:
        result.append("elevenlabs")
    gemini_ready, _reason = _gemini_capability()
    if gemini_ready:
        result.append("gemini_vertex")
    result.append("local")
    return result


async def _produce_with_provider(
    provider: str,
    request: FastGenerateRequest,
    manifest: dict[str, Any],
    references: list[Path],
    raw: Path,
) -> str:
    if provider == "elevenlabs":
        return await _eleven_generate_fast(
            request.profile_id,
            manifest,
            references,
            request.text.strip(),
            raw,
        )
    if provider == "gemini_vertex":
        return await _gemini_generate(references, request.text.strip(), raw)
    if provider == "local":
        return await asyncio.to_thread(
            _local_generate_fast,
            request.profile_id,
            manifest,
            references,
            request.text.strip(),
            request.language,
            raw,
        )
    raise HTTPException(status_code=400, detail="محرك الاستنساخ غير معروف.")


@router.get("/status")
async def fast_status():
    base = await clone.clone_status()
    gemini_ready, gemini_reason = _gemini_capability()
    if base.get("elevenlabs_key_set"):
        recommended = "elevenlabs"
    elif gemini_ready:
        recommended = "gemini_vertex"
    else:
        recommended = "local"
    return {
        **base,
        "success": True,
        "recommended_provider": recommended,
        "automatic_order": ["elevenlabs", "gemini_vertex", "local"],
        "gemini_vertex_ready": gemini_ready,
        "gemini_vertex_reason": gemini_reason,
        "xtts_model_warmed": MODEL_MARKER.exists(),
        "reference_optimization": "10-30 seconds",
        "message": "الوضع التلقائي يستخدم أسرع محرك استنساخ حقيقي متاح ولا يستخدم صوت Gemini الجاهز بدل العينة.",
    }


@router.post("/generate")
async def generate_fast(request: FastGenerateRequest):
    manifest = clone._load_manifest(request.profile_id)
    references = await asyncio.to_thread(_reference_paths, request.profile_id, manifest)
    providers = _provider_order(request.provider)
    attempts: list[dict[str, str]] = []
    last_error = ""

    for provider in providers:
        token = uuid.uuid4().hex[:12]
        suffix = ".wav" if provider in {"local", "gemini_vertex"} else ".mp3"
        raw = OUTPUTS_DIR / f"clone_fast_raw_{provider}_{request.profile_id}_{token}{suffix}"
        master = OUTPUTS_DIR / f"voice_clone_fast_{provider}_{request.profile_id}_{token}.mp3"
        try:
            detail = await _produce_with_provider(provider, request, manifest, references, raw)
            if not _valid_audio(raw):
                raise RuntimeError("المحرك لم ينشئ ملفًا صوتيًا صالحًا.")
            await asyncio.to_thread(clone._master_clone, raw, master, request.speed, request.style)
            if not _valid_audio(master):
                raise RuntimeError("لم يكتمل الماستر النهائي.")
            metadata = {
                "synthetic_voice": True,
                "consent_confirmed": True,
                "profile_id": request.profile_id,
                "profile_name": manifest.get("name"),
                "owner_name": manifest.get("owner_name"),
                "requested_provider": request.provider,
                "provider": provider,
                "provider_detail": detail,
                "language": request.language,
                "style": request.style,
                "speed": request.speed,
                "optimized_reference_seconds": MAX_REFERENCE_SECONDS,
                "quality": "MP3 320kbps / 48kHz stereo",
                "created_at": clone._now(),
                "attempts": attempts,
            }
            project = await asyncio.to_thread(clone._save_project, manifest, master, metadata)
            return {
                "success": True,
                "url": f"/api/downloads/{master.name}",
                "file": str(master),
                "desktop_project": str(project),
                "requested_provider": request.provider,
                "provider": provider,
                "provider_detail": detail,
                "attempts": attempts,
                "profile": clone._public_profile(manifest),
                "quality": metadata["quality"],
                "reference_count": len(references),
                "message": f"تم إنشاء الصوت بالمحرك {provider} وحفظ مشروعه على سطح المكتب.",
            }
        except Exception as exc:
            last_error = _plain(exc.detail if isinstance(exc, HTTPException) else exc)
            attempts.append({"provider": provider, "error": last_error[-1200:]})
            logger.warning("Voice clone provider %s failed: %s", provider, last_error)
            master.unlink(missing_ok=True)
            if request.provider != "auto":
                if isinstance(exc, HTTPException):
                    raise
                raise HTTPException(status_code=500, detail=f"فشل الاستنساخ عبر {provider}: {last_error}") from exc
        finally:
            raw.unlink(missing_ok=True)

    raise HTTPException(
        status_code=502,
        detail={
            "message": "فشلت جميع محركات الاستنساخ الحقيقية المتاحة.",
            "attempts": attempts,
            "last_error": last_error,
        },
    )
