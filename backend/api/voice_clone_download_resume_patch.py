"""Resumable XTTS model provisioning for Voice Clone Pro 6.2.0.

This additive patch preserves profiles, samples, consent records, generated audio and
all existing interfaces. It replaces only the local XTTS setup function so a large
model download can resume, reports transferred megabytes and elapsed time, detects a
stalled connection, and never leaves the UI permanently stuck in an old 88% state.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.api import voice_clone_repair_runtime as repair
from backend.api import voice_clone_routes as clone
from backend.api import voice_clone_xtts_runtime as xtts

MODEL_FOLDER = "tts_models--multilingual--multi-dataset--xtts_v2"
ENGINE_CACHE = clone.ENGINE_DIR / "tts_cache"
DOWNLOAD_WORKER = clone.ENGINE_DIR / "xtts_resumable_download.py"
DOWNLOAD_STDOUT = clone.ENGINE_DIR / "xtts_download_stdout.log"
DOWNLOAD_STDERR = clone.ENGINE_DIR / "xtts_download_stderr.log"
DOWNLOAD_PID = clone.ENGINE_DIR / "xtts_download.pid"
EXPECTED_BYTES = 1_900_000_000
STALL_SECONDS = 12 * 60
TOTAL_SECONDS = 90 * 60
_ORIGINAL_READ_STATUS = clone._read_status
_ORIGINAL_SERVER_SOURCE = xtts._server_source
_ORIGINAL_WORKER_SOURCE = clone._worker_source


def _directory_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    try:
        for item in path.rglob("*"):
            try:
                if item.is_file():
                    total += item.stat().st_size
            except OSError:
                continue
    except OSError:
        return total
    return total


def _candidate_model_dirs() -> list[Path]:
    candidates = [ENGINE_CACHE / MODEL_FOLDER]
    local = os.getenv("LOCALAPPDATA", "").strip()
    roaming = os.getenv("APPDATA", "").strip()
    if local:
        candidates.append(Path(local) / "tts" / MODEL_FOLDER)
    if roaming:
        candidates.append(Path(roaming) / "tts" / MODEL_FOLDER)
    candidates.extend(
        [
            Path.home() / "AppData" / "Local" / "tts" / MODEL_FOLDER,
            Path.home() / ".local" / "share" / "tts" / MODEL_FOLDER,
            Path.home() / ".cache" / "tts" / MODEL_FOLDER,
        ]
    )
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _model_dir() -> Path:
    candidates = _candidate_model_dirs()
    existing = [(candidate, _directory_bytes(candidate)) for candidate in candidates]
    best, size = max(existing, key=lambda item: item[1], default=(ENGINE_CACHE / MODEL_FOLDER, 0))
    if size <= 0:
        best = ENGINE_CACHE / MODEL_FOLDER
    best.mkdir(parents=True, exist_ok=True)
    return best


def _model_complete(path: Path) -> bool:
    model = path / "model.pth"
    config = path / "config.json"
    vocab = path / "vocab.json"
    return (
        model.exists()
        and model.is_file()
        and model.stat().st_size > 500_000_000
        and config.exists()
        and config.stat().st_size > 500
        and vocab.exists()
        and vocab.stat().st_size > 10_000
    )


def _elapsed_label(seconds: float) -> str:
    whole = max(0, int(seconds))
    minutes, rest = divmod(whole, 60)
    return f"{minutes}:{rest:02d}"


def _write_status(state: str, message: str, progress: int, error: str = "", **extra: Any) -> None:
    payload: dict[str, Any] = {
        "state": state,
        "message": message,
        "progress": max(0, min(100, int(progress))),
        "error": error,
        "updated_at": clone._now(),
        **extra,
    }
    clone.ENGINE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = clone.ENGINE_STATUS.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(clone.ENGINE_STATUS)


def _read_status_resumable() -> dict[str, Any]:
    status = dict(_ORIGINAL_READ_STATUS())
    if status.get("state") == "installing":
        thread = clone._SETUP_THREAD
        alive = bool(thread and thread.is_alive())
        if not alive:
            model_dir = _model_dir()
            size_mb = round(_directory_bytes(model_dir) / (1024 * 1024), 1)
            status.update(
                {
                    "state": "needs_model",
                    "message": "توقف التنزيل السابق عند إغلاق البرنامج، والملفات الجزئية محفوظة.",
                    "progress": 0,
                    "error": f"اضغط تجهيز المحرك ليكمل من الملفات الموجودة ({size_mb} MB محفوظة).",
                    "downloaded_mb": size_mb,
                    "resumable": True,
                }
            )
    return status


def _download_worker_source(model_dir: Path) -> str:
    return f'''from __future__ import annotations
import json
import os
from pathlib import Path

model_dir = Path({str(model_dir)!r})
model_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("COQUI_TOS_AGREED", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "30")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "300")
os.environ["TTS_HOME"] = str(model_dir.parent)

from huggingface_hub import snapshot_download

kwargs = {{
    "repo_id": "coqui/XTTS-v2",
    "local_dir": str(model_dir),
    "max_workers": 2,
}}
try:
    snapshot_download(local_dir_use_symlinks=False, resume_download=True, **kwargs)
except TypeError:
    snapshot_download(**kwargs)

required = [model_dir / "model.pth", model_dir / "config.json", model_dir / "vocab.json"]
missing = [str(path.name) for path in required if not path.exists()]
if missing:
    raise RuntimeError("XTTS download incomplete; missing: " + ", ".join(missing))

from TTS.api import TTS
model = TTS(
    model_path=str(model_dir / "model.pth"),
    config_path=str(model_dir / "config.json"),
    progress_bar=False,
)
print(json.dumps({{"ready": True, "model_dir": str(model_dir)}}, ensure_ascii=False))
del model
'''


def _tail(path: Path, limit: int = 3500) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-limit:]
    except Exception:
        return ""


def _terminate(process: subprocess.Popen[Any]) -> None:
    try:
        process.terminate()
        process.wait(timeout=8)
        return
    except Exception:
        pass
    try:
        process.kill()
    except Exception:
        pass


def _run_resumable_model_setup(python: str) -> tuple[Path, str]:
    model_dir = _model_dir()
    DOWNLOAD_WORKER.write_text(_download_worker_source(model_dir), encoding="utf-8")
    DOWNLOAD_STDOUT.unlink(missing_ok=True)
    DOWNLOAD_STDERR.unlink(missing_ok=True)
    env = {
        **os.environ,
        "COQUI_TOS_AGREED": "1",
        "PYTHONUTF8": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "HF_HUB_DISABLE_XET": "1",
        "HF_HUB_ETAG_TIMEOUT": "30",
        "HF_HUB_DOWNLOAD_TIMEOUT": "300",
        "TTS_HOME": str(model_dir.parent),
        "OMP_NUM_THREADS": str(max(2, min(8, os.cpu_count() or 4))),
        "MKL_NUM_THREADS": str(max(2, min(8, os.cpu_count() or 4))),
    }
    with DOWNLOAD_STDOUT.open("w", encoding="utf-8") as stdout, DOWNLOAD_STDERR.open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(
            [python, str(DOWNLOAD_WORKER)],
            cwd=str(clone.ENGINE_DIR),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    DOWNLOAD_PID.write_text(str(process.pid), encoding="ascii")
    started = time.monotonic()
    last_change = started
    last_size = _directory_bytes(model_dir)
    try:
        while process.poll() is None:
            now = time.monotonic()
            elapsed = now - started
            size = _directory_bytes(model_dir)
            if size > last_size + 256 * 1024:
                last_change = now
                last_size = size
            complete = _model_complete(model_dir)
            size_mb = round(size / (1024 * 1024), 1)
            if complete:
                progress = 98
                message = (
                    f"اكتمل تنزيل ملفات XTTS ({size_mb} MB). "
                    f"جاري تحميل النموذج وفحصه — الوقت {_elapsed_label(elapsed)}..."
                )
                phase = "loading"
            else:
                approximate = min(16, int((size / EXPECTED_BYTES) * 16)) if EXPECTED_BYTES else 0
                progress = 80 + approximate
                message = (
                    f"جاري تنزيل نموذج XTTS مع حفظ الاستكمال: {size_mb} MB — "
                    f"الوقت {_elapsed_label(elapsed)}. لا تغلق البرنامج."
                )
                phase = "downloading"
            _write_status(
                "installing",
                message,
                progress,
                downloaded_mb=size_mb,
                elapsed_seconds=int(elapsed),
                phase=phase,
                resumable=True,
                model_dir=str(model_dir),
            )
            if elapsed > TOTAL_SECONDS:
                _terminate(process)
                raise RuntimeError("انتهت مهلة تجهيز XTTS بعد 90 دقيقة. الملفات الجزئية محفوظة ويمكن استكمالها.")
            if not complete and now - last_change > STALL_SECONDS:
                _terminate(process)
                raise RuntimeError(
                    "لم تتغير ملفات التنزيل لمدة 12 دقيقة. تحقق من الإنترنت ثم اضغط تجهيز المحرك ليكمل من نفس المكان."
                )
            time.sleep(3.0)

        stdout_text = _tail(DOWNLOAD_STDOUT)
        stderr_text = _tail(DOWNLOAD_STDERR)
        if process.returncode != 0 or not _model_complete(model_dir):
            raise RuntimeError(stderr_text or stdout_text or "لم يكتمل تنزيل أو تحميل نموذج XTTS.")
        return model_dir, stdout_text
    finally:
        DOWNLOAD_PID.unlink(missing_ok=True)


def _write_marker(model_dir: Path, details: str) -> None:
    payload = {
        "ready": True,
        "prepared_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "details": details[-1400:],
        "coqui": repair.COQUI_VERSION,
        "torch": repair.TORCH_VERSION,
        "transformers": repair.TRANSFORMERS_VERSION,
        "model_dir": str(model_dir),
        "resumable_download": True,
    }
    repair.MODEL_MARKER.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _ensure_huggingface(python: str) -> None:
    check = clone._run([python, "-c", "import huggingface_hub;print(huggingface_hub.__version__)"], timeout=120)
    if check.returncode == 0:
        return
    _write_status("installing", "جاري تثبيت أداة الاستكمال الآمن لتنزيل XTTS...", 78)
    completed = clone._run(
        [
            python,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "--upgrade",
            "huggingface_hub>=0.28,<1",
        ],
        timeout=900,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "تعذر تثبيت أداة تنزيل XTTS")[-2200:])


def _patched_model_source(source: str, model_dir: Path) -> str:
    old = 'model = TTS("tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=False).to(device)'
    replacement = (
        f"model_dir = Path({str(model_dir)!r})\n"
        "    model = TTS(model_path=str(model_dir / 'model.pth'), "
        "config_path=str(model_dir / 'config.json'), progress_bar=False).to(device)"
    )
    return source.replace(old, replacement)


def _server_source_resumable() -> str:
    return _patched_model_source(_ORIGINAL_SERVER_SOURCE(), _model_dir())


def _worker_source_resumable() -> str:
    return _patched_model_source(_ORIGINAL_WORKER_SOURCE(), _model_dir())


def _resume_local_engine() -> None:
    """Prepare XTTS without deleting caches, profiles, samples or generated audio."""
    if not clone._SETUP_LOCK.acquire(blocking=False):
        return
    try:
        _write_status("installing", "جاري فحص Python وبيئة XTTS الحالية...", 4, resumable=True)
        base_python = clone._find_python311()
        if not base_python:
            raise RuntimeError("Python 3.11 غير موجود. ثبّت Python 3.11 ثم أعد تجهيز المحرك.")
        if not clone._engine_python().exists():
            _write_status("installing", "جاري إنشاء بيئة XTTS المستقلة من دون لمس ملفاتك...", 10)
            completed = clone._run(base_python + ["-m", "venv", str(clone.ENGINE_VENV)], timeout=600)
            if completed.returncode != 0:
                raise RuntimeError((completed.stderr or completed.stdout or "تعذر إنشاء بيئة XTTS")[-2200:])

        python = str(clone._engine_python())
        _write_status("installing", "جاري فحص مكونات XTTS الموجودة...", 14, resumable=True)
        dependency_result = repair._dependency_check(python)
        if dependency_result.returncode != 0:
            repair._install_dependencies(base_python, python)
        else:
            _write_status("installing", "المكونات المتوافقة موجودة؛ لن يعاد تثبيتها.", 76, resumable=True)
        _ensure_huggingface(python)

        clone.WORKER_FILE.write_text(_worker_source_resumable(), encoding="utf-8")
        repair.MODEL_MARKER.unlink(missing_ok=True)
        model_dir, details = _run_resumable_model_setup(python)
        _write_marker(model_dir, details)
        _write_status(
            "ready",
            "اكتمل تنزيل نموذج XTTS وفحصه. النموذج جاهز، وستُحفظ الملفات لاستخدامها في المرات القادمة.",
            100,
            downloaded_mb=round(_directory_bytes(model_dir) / (1024 * 1024), 1),
            resumable=True,
            model_dir=str(model_dir),
        )
    except Exception as exc:
        repair.MODEL_MARKER.unlink(missing_ok=True)
        clone.logger.exception("Resumable XTTS setup failed")
        saved_mb = round(_directory_bytes(_model_dir()) / (1024 * 1024), 1)
        _write_status(
            "failed",
            "توقف تجهيز XTTS، لكن الملفات التي نزلت لم تُحذف.",
            0,
            f"{repair._friendly_error(str(exc))} اضغط تجهيز المحرك مرة أخرى للاستكمال. المحفوظ: {saved_mb} MB.",
            downloaded_mb=saved_mb,
            resumable=True,
        )
    finally:
        clone._SETUP_THREAD = None
        clone._SETUP_LOCK.release()


# Apply only runtime behavior. Existing profile/sample/project files remain untouched.
clone._read_status = _read_status_resumable
clone._worker_source = _worker_source_resumable
clone._setup_local_engine = _resume_local_engine
xtts._server_source = _server_source_resumable
