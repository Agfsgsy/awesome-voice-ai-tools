"""Consent-based professional voice cloning for Ibn Al-Waqadi Studio.

The feature supports two explicit providers:
- Local XTTS-v2 in an isolated Python environment under LocalAppData.
- ElevenLabs Instant Voice Cloning when the user's Human Pro account permits it.

Cloning is never advertised as acoustically identical. Every profile requires an
explicit consent record, keeps a sample hash, and every generated project includes
metadata marking the result as synthetic speech.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import threading
import time
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.core.config import CONFIG_DIR, DATA_DIR, OUTPUTS_DIR
from backend.core.logger import get_logger
from backend.plugins.builtin.audio_effects import _ffmpeg_executable

router = APIRouter(prefix="/api/voice-clone", tags=["Voice Clone Pro"])
logger = get_logger("voice_clone_pro")

CLONE_ROOT = DATA_DIR / "voice_clones"
PROFILES_DIR = CLONE_ROOT / "profiles"
ENGINE_DIR = CLONE_ROOT / "local_engine"
ENGINE_VENV = ENGINE_DIR / "venv"
ENGINE_STATUS = ENGINE_DIR / "setup_status.json"
WORKER_FILE = ENGINE_DIR / "xtts_worker.py"
HUMAN_SETTINGS = CONFIG_DIR / "human_pro.json"
SUPPORTED_SAMPLE_FORMATS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".opus"}
MAX_SAMPLE_BYTES = 80 * 1024 * 1024
MAX_PROFILE_BYTES = 220 * 1024 * 1024
MAX_TEXT = 12000

for directory in (CLONE_ROOT, PROFILES_DIR, ENGINE_DIR, OUTPUTS_DIR):
    directory.mkdir(parents=True, exist_ok=True)

_SETUP_LOCK = threading.Lock()
_SETUP_THREAD: threading.Thread | None = None


class GenerateCloneRequest(BaseModel):
    profile_id: str = Field(min_length=8, max_length=80)
    text: str = Field(min_length=2, max_length=MAX_TEXT)
    provider: Literal["local", "elevenlabs"] = "local"
    language: str = Field(default="ar", pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
    speed: float = Field(default=1.0, ge=0.75, le=1.20)
    style: Literal["natural", "warm", "emotional", "broadcast", "story"] = "natural"


class DeleteProfileRequest(BaseModel):
    confirm: bool = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_name(value: str, fallback: str = "voice") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", (value or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .-")
    return (cleaned[:80] or fallback)


def _profile_path(profile_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{16}", profile_id or ""):
        raise HTTPException(status_code=400, detail="معرّف ملف الصوت غير صالح.")
    path = (PROFILES_DIR / profile_id).resolve()
    if PROFILES_DIR.resolve() not in path.parents:
        raise HTTPException(status_code=400, detail="مسار ملف الصوت غير صالح.")
    return path


def _manifest_path(profile_id: str) -> Path:
    return _profile_path(profile_id) / "profile.json"


def _load_manifest(profile_id: str) -> dict[str, Any]:
    path = _manifest_path(profile_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="ملف الصوت المستنسخ غير موجود.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail="تعذر قراءة بيانات ملف الصوت.") from exc
    if not data.get("consent_confirmed"):
        raise HTTPException(status_code=403, detail="لا يوجد سجل موافقة صالح لهذا الملف الصوتي.")
    return data


def _save_manifest(profile_id: str, data: dict[str, Any]) -> None:
    path = _manifest_path(profile_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _desktop_root() -> Path:
    candidates: list[Path] = []
    for variable in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        root = os.getenv(variable, "").strip()
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


def _engine_python() -> Path:
    return ENGINE_VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _write_status(state: str, message: str, progress: int, error: str = "") -> None:
    payload = {
        "state": state,
        "message": message,
        "progress": max(0, min(100, int(progress))),
        "error": error,
        "updated_at": _now(),
    }
    ENGINE_DIR.mkdir(parents=True, exist_ok=True)
    ENGINE_STATUS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_status() -> dict[str, Any]:
    if not ENGINE_STATUS.exists():
        return {"state": "not_installed", "message": "المحرك المحلي غير مجهز.", "progress": 0, "error": ""}
    try:
        return json.loads(ENGINE_STATUS.read_text(encoding="utf-8"))
    except Exception:
        return {"state": "unknown", "message": "تعذر قراءة حالة المحرك.", "progress": 0, "error": ""}


def _worker_source() -> str:
    return r'''from __future__ import annotations
import json
import os
import sys
import traceback
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"success": False, "error": "job file is required"}))
        return 2
    job_path = Path(sys.argv[1])
    job = json.loads(job_path.read_text(encoding="utf-8"))
    os.environ.setdefault("COQUI_TOS_AGREED", "1")
    try:
        import torch
        from TTS.api import TTS
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = TTS("tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=False).to(device)
        model.tts_to_file(
            text=job["text"],
            speaker_wav=job["samples"],
            language=job.get("language", "ar").split("-")[0],
            file_path=job["output"],
            split_sentences=True,
        )
        output = Path(job["output"])
        if not output.exists() or output.stat().st_size < 1024:
            raise RuntimeError("XTTS did not create a usable output file")
        print(json.dumps({"success": True, "device": device, "output": str(output)}))
        return 0
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc), "trace": traceback.format_exc()[-3000:]}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _run(command: list[str], *, timeout: int = 3600, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def _find_python311() -> list[str] | None:
    candidates: list[list[str]] = []
    if os.name == "nt":
        candidates.extend([["py", "-3.11"], ["python", "-3.11"]])
    candidates.extend([["python3.11"], ["python3"], ["python"]])
    for candidate in candidates:
        try:
            completed = _run(candidate + ["-c", "import sys;print(sys.version_info[:2])"], timeout=20)
            if completed.returncode == 0 and "(3, 11)" in completed.stdout:
                return candidate
        except Exception:
            continue
    return None


def _setup_local_engine() -> None:
    global _SETUP_THREAD
    if not _SETUP_LOCK.acquire(blocking=False):
        return
    try:
        _write_status("installing", "جاري البحث عن Python 3.11...", 4)
        base_python = _find_python311()
        if not base_python:
            raise RuntimeError("Python 3.11 غير موجود. ثبّت Python 3.11 ثم أعد تجهيز المحرك.")

        if not _engine_python().exists():
            _write_status("installing", "جاري إنشاء بيئة الاستنساخ المستقلة...", 10)
            completed = _run(base_python + ["-m", "venv", str(ENGINE_VENV)], timeout=600)
            if completed.returncode != 0:
                raise RuntimeError((completed.stderr or completed.stdout or "تعذر إنشاء البيئة")[-1800:])

        python = str(_engine_python())
        _write_status("installing", "جاري تحديث أدوات التثبيت...", 18)
        completed = _run([python, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], timeout=900)
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "تعذر تحديث pip")[-1800:])

        _write_status("installing", "جاري تثبيت PyTorch للمحرك المحلي...", 32)
        completed = _run(
            [
                python,
                "-m",
                "pip",
                "install",
                "torch==2.5.1",
                "torchaudio==2.5.1",
                "--index-url",
                "https://download.pytorch.org/whl/cpu",
            ],
            timeout=3600,
        )
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "تعذر تثبيت PyTorch")[-2200:])

        _write_status("installing", "جاري تثبيت Coqui XTTS-v2...", 62)
        completed = _run([python, "-m", "pip", "install", "coqui-tts==0.27.5"], timeout=3600)
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "تعذر تثبيت Coqui TTS")[-2400:])

        WORKER_FILE.write_text(_worker_source(), encoding="utf-8")
        _write_status("installing", "جاري فحص المحرك بعد التثبيت...", 90)
        completed = _run(
            [python, "-c", "import torch;from TTS.api import TTS;print(torch.__version__)"],
            timeout=300,
            env={**os.environ, "COQUI_TOS_AGREED": "1"},
        )
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "فشل فحص XTTS")[-2200:])
        _write_status("ready", "المحرك المحلي XTTS-v2 جاهز. أول إنتاج سيحمّل النموذج وقد يستغرق وقتًا.", 100)
    except Exception as exc:
        logger.exception("Local cloning engine setup failed")
        _write_status("failed", "فشل تجهيز المحرك المحلي.", 0, str(exc))
    finally:
        _SETUP_THREAD = None
        _SETUP_LOCK.release()


def _wav_metrics(path: Path) -> dict[str, float]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.getnframes()
        raw = handle.readframes(frames)
    if sample_width != 2 or channels != 1 or rate <= 0:
        raise ValueError("صيغة WAV المعالجة غير متوقعة.")
    count = len(raw) // 2
    if count == 0:
        raise ValueError("العينة لا تحتوي بيانات صوتية.")
    values = struct.unpack(f"<{count}h", raw)
    squares = 0.0
    peak = 0
    clipped = 0
    silent = 0
    for value in values:
        absolute = abs(value)
        squares += float(value) * float(value)
        peak = max(peak, absolute)
        if absolute >= 32400:
            clipped += 1
        if absolute < 260:
            silent += 1
    rms = math.sqrt(squares / count) / 32768.0
    return {
        "duration": frames / rate,
        "rms": rms,
        "peak": peak / 32768.0,
        "clipping_ratio": clipped / count,
        "silence_ratio": silent / count,
    }


def _preprocess_sample(source: Path, target: Path) -> dict[str, float]:
    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        raise RuntimeError("FFmpeg غير متاح لتنقية عينة الصوت.")
    filter_chain = (
        "highpass=f=60,lowpass=f=12000,"
        "silenceremove=start_periods=1:start_duration=0.12:start_threshold=-48dB:"
        "stop_periods=-1:stop_duration=0.30:stop_threshold=-48dB,"
        "loudnorm=I=-20:TP=-2:LRA=10"
    )
    completed = _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-af",
            filter_chain,
            "-ar",
            "24000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(target),
        ],
        timeout=600,
    )
    if completed.returncode != 0 or not target.exists() or target.stat().st_size < 1024:
        raise RuntimeError((completed.stderr or completed.stdout or "تعذر تجهيز العينة")[-1600:])
    return _wav_metrics(target)


def _quality(total_duration: float, metrics: list[dict[str, float]]) -> tuple[int, str, list[str]]:
    score = 40
    notes: list[str] = []
    if total_duration >= 60:
        score += 32
    elif total_duration >= 30:
        score += 25
    elif total_duration >= 15:
        score += 16
    else:
        notes.append("يفضل تسجيل 15–90 ثانية لثبات أفضل.")
    average_rms = sum(item["rms"] for item in metrics) / len(metrics)
    max_clip = max(item["clipping_ratio"] for item in metrics)
    max_silence = max(item["silence_ratio"] for item in metrics)
    if 0.035 <= average_rms <= 0.28:
        score += 18
    else:
        notes.append("مستوى التسجيل منخفض أو مرتفع؛ اقترب من الميكروفون دون صراخ.")
    if max_clip < 0.001:
        score += 7
    else:
        notes.append("توجد قمم صوتية مشوهة في العينة.")
    if max_silence < 0.45:
        score += 3
    else:
        notes.append("العينة تحتوي صمتًا طويلًا.")
    score = max(0, min(100, score))
    label = "ممتازة" if score >= 88 else "جيدة جدًا" if score >= 76 else "جيدة" if score >= 62 else "تحتاج تحسين"
    return score, label, notes


async def _save_upload(upload: UploadFile, target: Path, remaining: int) -> tuple[int, str]:
    hasher = hashlib.sha256()
    total = 0
    with target.open("wb") as handle:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_SAMPLE_BYTES or total > remaining:
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="حجم عينات الصوت أكبر من الحد المسموح.")
            hasher.update(chunk)
            handle.write(chunk)
    if total < 1024:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="عينة الصوت فارغة أو تالفة.")
    return total, hasher.hexdigest()


async def create_profile_from_uploads(
    samples: list[UploadFile],
    *,
    name: str,
    owner_name: str,
    consent: bool,
    consent_statement: str,
) -> dict[str, Any]:
    if not consent:
        raise HTTPException(status_code=400, detail="يجب تأكيد أن الصوت لك أو لديك إذن صريح موثق من صاحبه.")
    if len(consent_statement.strip()) < 8:
        raise HTTPException(status_code=400, detail="اكتب تأكيدًا مختصرًا للموافقة، مثل: أنا صاحب الصوت وأوافق على الاستنساخ.")
    if not samples or len(samples) > 5:
        raise HTTPException(status_code=400, detail="اختر من عينة واحدة إلى خمس عينات صوتية.")

    profile_id = uuid.uuid4().hex[:16]
    directory = _profile_path(profile_id)
    originals = directory / "originals"
    processed = directory / "processed"
    originals.mkdir(parents=True, exist_ok=False)
    processed.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    records: list[dict[str, Any]] = []
    metrics: list[dict[str, float]] = []
    try:
        for index, upload in enumerate(samples, start=1):
            original_name = Path(upload.filename or f"sample_{index}.wav").name
            suffix = Path(original_name).suffix.lower()
            if suffix not in SUPPORTED_SAMPLE_FORMATS:
                raise HTTPException(status_code=400, detail=f"صيغة العينة غير مدعومة: {suffix or 'بدون امتداد'}")
            original = originals / f"sample_{index}{suffix}"
            size, digest = await _save_upload(upload, original, MAX_PROFILE_BYTES - total_bytes)
            total_bytes += size
            normalized = processed / f"sample_{index}.wav"
            sample_metrics = await asyncio.to_thread(_preprocess_sample, original, normalized)
            if sample_metrics["duration"] < 3.0:
                raise HTTPException(status_code=400, detail=f"العينة رقم {index} أقصر من 3 ثوانٍ بعد إزالة الصمت.")
            metrics.append(sample_metrics)
            records.append(
                {
                    "original_name": original_name,
                    "sha256": digest,
                    "processed_file": normalized.name,
                    "duration": round(sample_metrics["duration"], 2),
                    "rms": round(sample_metrics["rms"], 5),
                    "clipping_ratio": round(sample_metrics["clipping_ratio"], 6),
                    "silence_ratio": round(sample_metrics["silence_ratio"], 5),
                }
            )
        total_duration = sum(item["duration"] for item in metrics)
        if total_duration < 10.0:
            raise HTTPException(status_code=400, detail="إجمالي الكلام الواضح أقل من 10 ثوانٍ. استخدم عينة أطول.")
        if total_duration > 300.0:
            raise HTTPException(status_code=400, detail="إجمالي العينات أطول من خمس دقائق؛ اختر أفضل المقاطع فقط.")
        score, label, notes = _quality(total_duration, metrics)
        manifest = {
            "id": profile_id,
            "name": _safe_name(name, "صوتي"),
            "owner_name": _safe_name(owner_name, "صاحب الصوت"),
            "created_at": _now(),
            "consent_confirmed": True,
            "consent_statement": consent_statement.strip()[:500],
            "consent_record_sha256": hashlib.sha256(
                f"{owner_name}|{consent_statement}|{profile_id}|{_now()}".encode("utf-8")
            ).hexdigest(),
            "synthetic_use_only": True,
            "samples": records,
            "total_duration": round(total_duration, 2),
            "quality_score": score,
            "quality_label": label,
            "quality_notes": notes,
            "elevenlabs_voice_id": "",
        }
        _save_manifest(profile_id, manifest)
        return manifest
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise


def _public_profile(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "owner_name": data.get("owner_name"),
        "created_at": data.get("created_at"),
        "sample_count": len(data.get("samples") or []),
        "total_duration": data.get("total_duration", 0),
        "quality_score": data.get("quality_score", 0),
        "quality_label": data.get("quality_label", ""),
        "quality_notes": data.get("quality_notes", []),
        "elevenlabs_ready": bool(data.get("elevenlabs_voice_id")),
        "consent_confirmed": bool(data.get("consent_confirmed")),
    }


def _human_settings() -> dict[str, str]:
    data: dict[str, Any] = {}
    if HUMAN_SETTINGS.exists():
        try:
            data = json.loads(HUMAN_SETTINGS.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    return {
        "api_key": str(data.get("api_key") or os.getenv("ELEVENLABS_API_KEY", "")).strip(),
        "model_id": str(data.get("model_id") or os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")).strip(),
    }


def _eleven_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            detail = payload.get("detail") or payload.get("error") or payload
            if isinstance(detail, dict):
                return str(detail.get("message") or detail.get("status") or detail)
            return str(detail)
    except Exception:
        pass
    return response.text[:1000] or f"HTTP {response.status_code}"


async def _ensure_eleven_voice(profile_id: str, manifest: dict[str, Any], api_key: str) -> str:
    existing = str(manifest.get("elevenlabs_voice_id", "")).strip()
    if existing:
        return existing
    processed_dir = _profile_path(profile_id) / "processed"
    sample_paths = [processed_dir / str(item["processed_file"]) for item in manifest.get("samples", [])]
    handles = [path.open("rb") for path in sample_paths]
    try:
        files = [("files", (path.name, handle, "audio/wav")) for path, handle in zip(sample_paths, handles)]
        data = {
            "name": f"IbnWaqadi-{manifest.get('name', profile_id)}-{profile_id[:5]}",
            "description": "Consent-based voice clone created locally in Ibn Al-Waqadi Studio.",
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
            raise HTTPException(status_code=response.status_code, detail="تعذر إنشاء نسخة ElevenLabs: " + _eleven_error(response))
        voice_id = str(response.json().get("voice_id", "")).strip()
        if not voice_id:
            raise HTTPException(status_code=502, detail="أنشأت ElevenLabs الطلب لكنها لم ترجع Voice ID.")
        manifest["elevenlabs_voice_id"] = voice_id
        manifest["elevenlabs_created_at"] = _now()
        _save_manifest(profile_id, manifest)
        return voice_id
    finally:
        for handle in handles:
            handle.close()


def _local_generate(profile_id: str, manifest: dict[str, Any], text: str, language: str, raw_output: Path) -> str:
    python = _engine_python()
    if not python.exists() or not WORKER_FILE.exists():
        raise RuntimeError("المحرك المحلي غير مجهز. اضغط تجهيز XTTS مرة واحدة.")
    processed_dir = _profile_path(profile_id) / "processed"
    samples = [str(processed_dir / str(item["processed_file"])) for item in manifest.get("samples", [])]
    job = {
        "text": text,
        "language": language,
        "samples": samples,
        "output": str(raw_output),
    }
    job_path = ENGINE_DIR / f"job_{uuid.uuid4().hex[:12]}.json"
    job_path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    env = {**os.environ, "COQUI_TOS_AGREED": "1", "PYTHONUTF8": "1"}
    try:
        completed = _run([str(python), str(WORKER_FILE), str(job_path)], timeout=3600, env=env)
    finally:
        job_path.unlink(missing_ok=True)
    if completed.returncode != 0 or not raw_output.exists():
        detail = (completed.stdout or completed.stderr or "فشل XTTS")[-3200:]
        try:
            parsed = json.loads(completed.stdout.strip().splitlines()[-1])
            detail = str(parsed.get("error") or detail)
        except Exception:
            pass
        raise RuntimeError(detail)
    device = "cpu"
    try:
        parsed = json.loads(completed.stdout.strip().splitlines()[-1])
        device = str(parsed.get("device") or "cpu")
    except Exception:
        pass
    return device


async def _eleven_generate(profile_id: str, manifest: dict[str, Any], text: str, raw_output: Path) -> str:
    settings = _human_settings()
    api_key = settings["api_key"]
    if not api_key:
        raise HTTPException(status_code=400, detail="أضف مفتاح ElevenLabs في إعداد Human Pro أولًا.")
    voice_id = await _ensure_eleven_voice(profile_id, manifest, api_key)
    payload = {
        "text": text,
        "model_id": settings["model_id"] or "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.48,
            "similarity_boost": 0.88,
            "style": 0.22,
            "use_speaker_boost": True,
        },
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0)) as client:
        response = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": api_key, "Accept": "audio/mpeg"},
            json=payload,
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail="تعذر توليد الصوت عبر ElevenLabs: " + _eleven_error(response))
    raw_output.write_bytes(response.content)
    if raw_output.stat().st_size < 1024:
        raise HTTPException(status_code=502, detail="لم تُرجع ElevenLabs ملفًا صوتيًا صالحًا.")
    return voice_id


def _master_clone(source: Path, target: Path, speed: float, style: str) -> None:
    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        shutil.copy2(source, target)
        return
    style_filters = {
        "natural": "equalizer=f=180:t=q:w=1.2:g=1",
        "warm": "equalizer=f=170:t=q:w=1.2:g=2,equalizer=f=4200:t=q:w=1.0:g=-1",
        "emotional": "equalizer=f=220:t=q:w=1.0:g=1.5,aecho=0.8:0.12:35:0.08",
        "broadcast": "equalizer=f=120:t=q:w=1.0:g=2,equalizer=f=3500:t=q:w=1.1:g=1.5",
        "story": "equalizer=f=190:t=q:w=1.0:g=1.2,equalizer=f=5200:t=q:w=1.0:g=-0.8",
    }
    filters = (
        f"highpass=f=60,lowpass=f=15000,{style_filters.get(style, style_filters['natural'])},"
        f"atempo={speed:.3f},acompressor=threshold=-20dB:ratio=2.4:attack=10:release=180,"
        "loudnorm=I=-16:TP=-1.2:LRA=9,alimiter=limit=0.97"
    )
    completed = _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-af",
            filters,
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "320k",
            str(target),
        ],
        timeout=1200,
    )
    if completed.returncode != 0 or not target.exists() or target.stat().st_size < 1024:
        raise RuntimeError((completed.stderr or completed.stdout or "فشل الماستر النهائي")[-1800:])


def _save_project(manifest: dict[str, Any], master: Path, metadata: dict[str, Any]) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    project = (
        _desktop_root()
        / "استوديو ابن الواقدي"
        / "استنساخ الصوت"
        / _safe_name(str(manifest.get("name", "صوتي")))
        / stamp
    )
    project.mkdir(parents=True, exist_ok=True)
    target = project / f"{_safe_name(str(manifest.get('name', 'صوتي')))} - صوت مستنسخ.mp3"
    shutil.copy2(master, target)
    (project / "معلومات الاستنساخ.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (project / "تنبيه.txt").write_text(
        "هذا الملف صوت اصطناعي منشأ باستنساخ صوت مصرح به. لا يجوز استخدامه للانتحال أو التضليل.\n",
        encoding="utf-8-sig",
    )
    return project


async def generate_from_profile(request: GenerateCloneRequest) -> dict[str, Any]:
    manifest = _load_manifest(request.profile_id)
    token = uuid.uuid4().hex[:12]
    suffix = ".wav" if request.provider == "local" else ".mp3"
    raw = OUTPUTS_DIR / f"clone_raw_{request.provider}_{request.profile_id}_{token}{suffix}"
    master = OUTPUTS_DIR / f"voice_clone_{request.provider}_{request.profile_id}_{token}.mp3"
    provider_detail = ""
    try:
        if request.provider == "local":
            provider_detail = await asyncio.to_thread(
                _local_generate,
                request.profile_id,
                manifest,
                request.text.strip(),
                request.language,
                raw,
            )
        else:
            provider_detail = await _eleven_generate(
                request.profile_id,
                manifest,
                request.text.strip(),
                raw,
            )
        await asyncio.to_thread(_master_clone, raw, master, request.speed, request.style)
        metadata = {
            "synthetic_voice": True,
            "consent_confirmed": True,
            "profile_id": request.profile_id,
            "profile_name": manifest.get("name"),
            "owner_name": manifest.get("owner_name"),
            "provider": request.provider,
            "provider_detail": provider_detail,
            "language": request.language,
            "style": request.style,
            "speed": request.speed,
            "quality": "MP3 320kbps / 48kHz stereo",
            "created_at": _now(),
        }
        project = await asyncio.to_thread(_save_project, manifest, master, metadata)
        return {
            "success": True,
            "url": f"/api/downloads/{master.name}",
            "file": str(master),
            "desktop_project": str(project),
            "provider": request.provider,
            "profile": _public_profile(manifest),
            "quality": metadata["quality"],
            "message": "تم إنشاء الصوت المستنسخ المصرح به وحفظ مشروعه على سطح المكتب.",
        }
    except HTTPException:
        master.unlink(missing_ok=True)
        raise
    except Exception as exc:
        master.unlink(missing_ok=True)
        logger.exception("Voice clone generation failed")
        raise HTTPException(status_code=500, detail=f"فشل استنساخ الصوت: {exc}") from exc
    finally:
        raw.unlink(missing_ok=True)


@router.get("/status")
async def clone_status():
    settings = _human_settings()
    setup = _read_status()
    ready = _engine_python().exists() and WORKER_FILE.exists() and setup.get("state") == "ready"
    profiles = []
    for manifest_path in sorted(PROFILES_DIR.glob("*/profile.json"), reverse=True):
        try:
            profiles.append(_public_profile(json.loads(manifest_path.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return {
        "success": True,
        "local_engine_ready": ready,
        "local_setup": setup,
        "elevenlabs_key_set": bool(settings["api_key"]),
        "profiles": profiles,
        "profile_count": len(profiles),
        "sample_guidance": "أفضل نتيجة من 30–120 ثانية كلام واضح بلا موسيقى أو صدى.",
        "exact_match_guaranteed": False,
    }


@router.post("/setup-local")
async def setup_local(accept_model_license: bool = Form(...)):
    global _SETUP_THREAD
    if not accept_model_license:
        raise HTTPException(status_code=400, detail="يجب قبول ترخيص نموذج XTTS قبل تنزيله واستخدامه.")
    if _engine_python().exists() and WORKER_FILE.exists() and _read_status().get("state") == "ready":
        return {"success": True, "started": False, "message": "المحرك المحلي جاهز بالفعل."}
    if _SETUP_THREAD and _SETUP_THREAD.is_alive():
        return {"success": True, "started": False, "message": "تجهيز المحرك يعمل الآن."}
    _SETUP_THREAD = threading.Thread(target=_setup_local_engine, name="voice-clone-setup", daemon=True)
    _SETUP_THREAD.start()
    return {"success": True, "started": True, "message": "بدأ تجهيز XTTS في الخلفية. اترك البرنامج مفتوحًا."}


@router.post("/profiles")
async def create_profile(
    samples: list[UploadFile] = File(...),
    name: str = Form(...),
    owner_name: str = Form(...),
    consent: bool = Form(...),
    consent_statement: str = Form(...),
):
    manifest = await create_profile_from_uploads(
        samples,
        name=name,
        owner_name=owner_name,
        consent=consent,
        consent_statement=consent_statement,
    )
    return {
        "success": True,
        "profile": _public_profile(manifest),
        "message": "تم إنشاء ملف الصوت وفحص العينات وحفظ سجل الموافقة محليًا.",
    }


@router.get("/profiles")
async def list_profiles():
    result: list[dict[str, Any]] = []
    for manifest_path in sorted(PROFILES_DIR.glob("*/profile.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            result.append(_public_profile(json.loads(manifest_path.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return {"success": True, "profiles": result}


@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str, request: DeleteProfileRequest):
    if not request.confirm:
        raise HTTPException(status_code=400, detail="يلزم تأكيد حذف ملف الصوت.")
    directory = _profile_path(profile_id)
    if not directory.exists():
        raise HTTPException(status_code=404, detail="ملف الصوت غير موجود.")
    shutil.rmtree(directory)
    return {"success": True, "message": "تم حذف ملف الاستنساخ المحلي وعيناته."}


@router.post("/generate")
async def generate_clone(request: GenerateCloneRequest):
    return await generate_from_profile(request)


@router.post("/open-project")
async def open_project(path: str = Form(...)):
    project = Path(path).resolve()
    allowed = (_desktop_root() / "استوديو ابن الواقدي" / "استنساخ الصوت").resolve()
    try:
        project.relative_to(allowed)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="لا يمكن فتح مسار خارج مجلد استنساخ الصوت.") from exc
    if not project.exists() or not project.is_dir():
        raise HTTPException(status_code=404, detail="مجلد المشروع غير موجود.")
    try:
        if os.name == "nt":
            os.startfile(str(project))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(project)])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"تعذر فتح المجلد: {exc}") from exc
    return {"success": True, "path": str(project)}
