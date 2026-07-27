"""Runtime repair for the isolated XTTS-v2 engine used by Voice Clone Pro.

The original Voice Clone feature is preserved. This module only replaces the
background installer with a deterministic dependency set that is compatible with
Coqui TTS 0.27.5 on Python 3.11 and can repair an already-created environment.
"""
from __future__ import annotations

import os

from backend.api import voice_clone_routes as clone

TRANSFORMERS_VERSION = "4.57.6"
COQUI_VERSION = "0.27.5"
TORCH_VERSION = "2.5.1"


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
        return "انقطع تنزيل مكونات XTTS أو انتهت المهلة. افحص الإنترنت ثم اضغط تجهيز المحرك مرة أخرى."
    return value[-1800:] or "تعذر تجهيز XTTS لسبب غير معروف."


def _import_check(python: str):
    code = (
        "import torch,transformers;"
        "from TTS.api import TTS;"
        f"assert transformers.__version__=='{TRANSFORMERS_VERSION}', transformers.__version__;"
        "print('torch='+torch.__version__+' transformers='+transformers.__version__)"
    )
    return clone._run(
        [python, "-c", code],
        timeout=420,
        env={**os.environ, "COQUI_TOS_AGREED": "1"},
    )


def _repair_local_engine() -> None:
    """Install or repair XTTS without deleting profiles, samples, or user data."""
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

        clone._write_status("installing", "جاري تثبيت Coqui XTTS-v2...", 58)
        completed = _pip(python, f"coqui-tts=={COQUI_VERSION}", timeout=3600)
        if completed.returncode != 0:
            raise RuntimeError(_tail(completed, "تعذر تثبيت Coqui TTS"))

        # Coqui 0.27.5 can otherwise receive Transformers 5.x, which breaks XTTS
        # imports. Pin and force-repair it after Coqui resolves its dependencies.
        clone._write_status(
            "installing",
            f"جاري إصلاح توافق Transformers {TRANSFORMERS_VERSION} مع XTTS...",
            76,
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
        clone._write_status("installing", "جاري فحص XTTS بعد إصلاح جميع المكونات...", 92)
        completed = _import_check(python)
        if completed.returncode != 0:
            raise RuntimeError(_tail(completed, "فشل فحص XTTS بعد الإصلاح"))

        clone._write_status(
            "ready",
            (
                "المحرك المحلي XTTS-v2 جاهز. تم تثبيت الإصدارات المتوافقة. "
                "أول إنتاج فقط قد يحمّل نموذج XTTS الكبير."
            ),
            100,
        )
    except Exception as exc:
        clone.logger.exception("Local cloning engine repair failed")
        clone._write_status("failed", "فشل تجهيز المحرك المحلي.", 0, _friendly_error(str(exc)))
    finally:
        clone._SETUP_THREAD = None
        clone._SETUP_LOCK.release()


# Monkey-patch only the installer function. Existing routes, profiles, generation,
# consent records, and saved projects stay unchanged.
clone._setup_local_engine = _repair_local_engine
