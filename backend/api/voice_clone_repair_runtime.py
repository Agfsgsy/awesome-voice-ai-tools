"""Runtime repair and warm-up for the isolated XTTS-v2 voice-clone engine.

The original profiles, samples, consent records, routes, and projects are preserved.
The engine is considered ready only after the actual XTTS model has been downloaded
and loaded successfully, so the first Generate click no longer hides a large model
download behind an endless spinner.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from backend.api import voice_clone_routes as clone

TRANSFORMERS_VERSION = "4.57.6"
COQUI_VERSION = "0.27.5"
TORCH_VERSION = "2.5.1"
MODEL_MARKER = clone.ENGINE_DIR / "xtts_model_ready.json"
_ORIGINAL_READ_STATUS = clone._read_status


def _tail(completed, fallback: str, limit: int = 2600) -> str:
    value = (completed.stderr or completed.stdout or fallback).strip()
    return value[-limit:]


def _pip(python: str, *packages: str, timeout: int = 3600, force: bool = False):
    command = [
        python,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--upgrade",
    ]
    if force:
        command.append("--force-reinstall")
    command.extend(packages)
    return clone._run(command, timeout=timeout)


def _friendly_error(value: str) -> str:
    low = value.lower()
    if "isin_mps_friendly" in low or "transformers" in low:
        return (
            "تعارض إصدار Transformers داخل بيئة XTTS. سيصلحه زر تجهيز المحرك "
            f"بتثبيت Transformers {TRANSFORMERS_VERSION} المتوافق."
        )
    if "no module named" in low:
        return "مكوّن ناقص داخل بيئة XTTS. اضغط تجهيز المحرك مرة أخرى لإكمال المكونات."
    if "space" in low or "no space" in low:
        return "المساحة غير كافية. وفر ما لا يقل عن 8 جيجابايت ثم أعد تجهيز المحرك."
    if "timed out" in low or "timeout" in low:
        return "انقطع تنزيل نموذج XTTS أو انتهت المهلة. افحص الإنترنت ثم اضغط تجهيز المحرك مرة أخرى."
    if "model" in low and "download" in low:
        return "لم يكتمل تنزيل نموذج XTTS الكبير. أبقِ البرنامج مفتوحًا وأعد تجهيز المحرك."
    return value[-1800:] or "تعذر تجهيز XTTS لسبب غير معروف."


def _model_check(python: str):
    """Download and load the real model, not only import the Python package."""
    code = (
        "import json,os,torch,transformers;"
        "os.environ.setdefault('COQUI_TOS_AGREED','1');"
        "os.environ.setdefault('TOKENIZERS_PARALLELISM','false');"
        "from TTS.api import TTS;"
        f"assert transformers.__version__=='{TRANSFORMERS_VERSION}', transformers.__version__;"
        "model=TTS('tts_models/multilingual/multi-dataset/xtts_v2',progress_bar=False);"
        "print(json.dumps({'ready':True,'torch':torch.__version__,'transformers':transformers.__version__}))"
    )
    threads = str(max(2, min(8, os.cpu_count() or 4)))
    return clone._run(
        [python, "-c", code],
        timeout=5400,
        env={
            **os.environ,
            "COQUI_TOS_AGREED": "1",
            "PYTHONUTF8": "1",
            "OMP_NUM_THREADS": threads,
            "MKL_NUM_THREADS": threads,
            "TOKENIZERS_PARALLELISM": "false",
        },
    )


def _write_model_marker(completed) -> None:
    payload = {
        "ready": True,
        "prepared_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "details": (completed.stdout or "").strip()[-1200:],
        "coqui": COQUI_VERSION,
        "torch": TORCH_VERSION,
        "transformers": TRANSFORMERS_VERSION,
    }
    MODEL_MARKER.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_status_with_model() -> dict:
    status = dict(_ORIGINAL_READ_STATUS())
    if status.get("state") == "ready" and not MODEL_MARKER.exists():
        status.update(
            {
                "state": "needs_model",
                "message": "المكونات مثبتة، لكن نموذج XTTS الكبير لم يُجهز بعد.",
                "progress": 92,
                "error": "اضغط تجهيز المحرك مرة واحدة ليتم تنزيل النموذج وفحصه قبل الإنتاج.",
            }
        )
    return status


def _repair_local_engine() -> None:
    """Install, repair, download, and warm XTTS without deleting user data."""
    if not clone._SETUP_LOCK.acquire(blocking=False):
        return
    try:
        clone._write_status("installing", "جاري فحص Python 3.11 وبيئة XTTS الحالية...", 4)
        base_python = clone._find_python311()
        if not base_python:
            raise RuntimeError("Python 3.11 غير موجود. ثبّت Python 3.11 ثم أعد تجهيز المحرك.")

        if not clone._engine_python().exists():
            clone._write_status("installing", "جاري إنشاء بيئة XTTS المستقلة من دون لمس ملفاتك...", 10)
            completed = clone._run(base_python + ["-m", "venv", str(clone.ENGINE_VENV)], timeout=600)
            if completed.returncode != 0:
                raise RuntimeError(_tail(completed, "تعذر إنشاء بيئة XTTS"))

        python = str(clone._engine_python())
        clone._write_status("installing", "جاري تحديث أدوات التثبيت داخل بيئة XTTS...", 18)
        completed = _pip(python, "pip", "setuptools", "wheel", timeout=900)
        if completed.returncode != 0:
            raise RuntimeError(_tail(completed, "تعذر تحديث pip"))

        clone._write_status("installing", "جاري تثبيت PyTorch المتوافق للمحرك المحلي...", 32)
        completed = clone._run(
            [
                python,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-input",
                "--upgrade",
                f"torch=={TORCH_VERSION}",
                f"torchaudio=={TORCH_VERSION}",
                "--index-url",
                "https://download.pytorch.org/whl/cpu",
            ],
            timeout=3600,
        )
        if completed.returncode != 0:
            raise RuntimeError(_tail(completed, "تعذر تثبيت PyTorch"))

        clone._write_status("installing", "جاري تثبيت Coqui XTTS-v2...", 55)
        completed = _pip(python, f"coqui-tts=={COQUI_VERSION}", timeout=3600)
        if completed.returncode != 0:
            raise RuntimeError(_tail(completed, "تعذر تثبيت Coqui TTS"))

        clone._write_status(
            "installing",
            f"جاري تثبيت Transformers {TRANSFORMERS_VERSION} المتوافق...",
            72,
        )
        completed = _pip(
            python,
            f"transformers=={TRANSFORMERS_VERSION}",
            timeout=1800,
            force=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(_tail(completed, "تعذر تثبيت Transformers المتوافق"))

        clone.WORKER_FILE.write_text(clone._worker_source(), encoding="utf-8")
        MODEL_MARKER.unlink(missing_ok=True)
        clone._write_status(
            "installing",
            "جاري تنزيل نموذج XTTS الكبير وتحميله وفحصه الآن؛ اترك البرنامج مفتوحًا...",
            88,
        )
        completed = _model_check(python)
        if completed.returncode != 0:
            raise RuntimeError(_tail(completed, "فشل تنزيل أو تحميل نموذج XTTS"))
        _write_model_marker(completed)

        clone._write_status(
            "ready",
            "المحرك المحلي XTTS-v2 والنموذج الكامل جاهزان. لن ينتظر زر الإنتاج تنزيل النموذج من الصفر.",
            100,
        )
    except Exception as exc:
        MODEL_MARKER.unlink(missing_ok=True)
        clone.logger.exception("Local cloning engine repair or warm-up failed")
        clone._write_status("failed", "فشل تجهيز المحرك المحلي.", 0, _friendly_error(str(exc)))
    finally:
        clone._SETUP_THREAD = None
        clone._SETUP_LOCK.release()


# Patch only setup/readiness. Profiles, samples, consent records, and old endpoints remain.
clone._read_status = _read_status_with_model
clone._setup_local_engine = _repair_local_engine
