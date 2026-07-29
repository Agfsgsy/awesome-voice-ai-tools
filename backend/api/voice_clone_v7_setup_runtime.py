"""Upgrade the preserved XTTS setup routine for Voice Clone Pro 7.

The original implementation is kept on disk. At import time this additive
runtime replaces only the setup callable: it chooses NVIDIA CUDA when usable,
falls back to CPU, installs Coqui TTS in the isolated venv, pre-downloads XTTS,
and reports exact progress through the existing status file.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
from pathlib import Path

from backend.api import voice_clone_routes as vc
from backend.core.logger import get_logger

logger = get_logger("voice_clone_v7_setup")


def _has_nvidia() -> bool:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return False
    try:
        completed = subprocess.run(
            [executable, "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return completed.returncode == 0 and bool(completed.stdout.strip())
    except Exception:
        return False


def _install_torch(python: str) -> None:
    if _has_nvidia():
        vc._write_status("installing", "تم اكتشاف NVIDIA؛ جاري تثبيت PyTorch CUDA...", 28)
        command = [
            python,
            "-m",
            "pip",
            "install",
            "torch==2.5.1",
            "torchaudio==2.5.1",
            "--index-url",
            "https://download.pytorch.org/whl/cu124",
        ]
        completed = vc._run(command, timeout=5400)
        if completed.returncode == 0:
            return
        logger.warning("CUDA PyTorch installation failed; falling back to CPU: %s", (completed.stderr or completed.stdout)[-1000:])

    vc._write_status("installing", "جاري تثبيت PyTorch المتوافق مع المعالج...", 30)
    completed = vc._run(
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
        timeout=5400,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "تعذر تثبيت PyTorch")[-3000:])


def _setup_local_engine_v7() -> None:
    if not vc._SETUP_LOCK.acquire(blocking=False):
        return
    try:
        vc._write_status("installing", "Voice Clone Pro 7: فحص Python 3.11...", 3)
        base_python = vc._find_python311()
        if not base_python:
            raise RuntimeError("Python 3.11 غير موجود. شغّل UPDATE_AND_INSTALL_VOICE_CLONE_PRO_7.bat")

        if not vc._engine_python().exists():
            vc._write_status("installing", "إنشاء بيئة XTTS المستقلة...", 9)
            completed = vc._run(base_python + ["-m", "venv", str(vc.ENGINE_VENV)], timeout=900)
            if completed.returncode != 0:
                raise RuntimeError((completed.stderr or completed.stdout or "تعذر إنشاء البيئة")[-2500:])

        python = str(vc._engine_python())
        vc._write_status("installing", "تحديث pip وwheel وsetuptools...", 15)
        completed = vc._run(
            [python, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
            timeout=1500,
        )
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "تعذر تحديث pip")[-2500:])

        _install_torch(python)

        vc._write_status("installing", "تثبيت Coqui XTTS-v2...", 56)
        completed = vc._run(
            [python, "-m", "pip", "install", "coqui-tts==0.27.5", "soundfile", "librosa"],
            timeout=7200,
        )
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "تعذر تثبيت Coqui TTS")[-4000:])

        vc.WORKER_FILE.parent.mkdir(parents=True, exist_ok=True)
        vc.WORKER_FILE.write_text(vc._worker_source(), encoding="utf-8")

        vc._write_status("installing", "تنزيل نموذج XTTS-v2 وفحصه؛ لا تغلق البرنامج...", 78)
        preload = (
            "import os;os.environ['COQUI_TOS_AGREED']='1';"
            "import torch;from TTS.api import TTS;"
            "m=TTS('tts_models/multilingual/multi-dataset/xtts_v2',progress_bar=False);"
            "print('device', 'cuda' if torch.cuda.is_available() else 'cpu');"
            "print('model-ready')"
        )
        completed = vc._run(
            [python, "-c", preload],
            timeout=4 * 3600,
            env={**os.environ, "COQUI_TOS_AGREED": "1", "PYTHONUTF8": "1"},
        )
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "فشل تنزيل أو فحص نموذج XTTS")[-5000:])

        device = "GPU NVIDIA" if "device cuda" in completed.stdout else "CPU"
        vc._write_status(
            "ready",
            f"XTTS-v2 جاهز بالكامل على {device}. تم تثبيت المكتبات وتنزيل النموذج وفحصه.",
            100,
        )
    except Exception as exc:
        logger.exception("Voice Clone Pro 7 XTTS setup failed")
        vc._write_status("failed", "فشل تجهيز XTTS-v2.", 0, str(exc))
    finally:
        vc._SETUP_THREAD = None
        vc._SETUP_LOCK.release()


# Patch only the setup implementation. Existing profiles, consent records,
# generation, deletion, and output routes remain unchanged.
vc._setup_local_engine = _setup_local_engine_v7
