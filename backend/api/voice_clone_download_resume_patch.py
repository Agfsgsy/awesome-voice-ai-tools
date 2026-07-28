"""Resumable XTTS model provisioning for Voice Clone Pro 6.2.0.

This additive patch preserves profiles, samples, consent records, generated audio and
all existing interfaces. It replaces only the local XTTS setup function so a large
model download can resume, reports transferred megabytes and elapsed time, detects a
stalled connection, and never leaves the UI permanently stuck in an old 88% state.
"""
from __future__ import annotations

import importlib
import json
import os
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

repair = importlib.import_module("backend.api.voice_clone_repair_runtime")
clone = importlib.import_module("backend.api.voice_clone_routes")
xtts = importlib.import_module("backend.api.voice_clone_xtts_runtime")

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
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def _model_dir() -> Path:
    return ENGINE_CACHE / MODEL_FOLDER


def _model_complete(model_dir: Path) -> bool:
    model = model_dir / "model.pth"
    config = model_dir / "config.json"
    vocab = model_dir / "vocab.json"
    try:
        return (
            model.exists()
            and model.stat().st_size >= 500_000_000
            and config.exists()
            and config.stat().st_size >= 500
            and vocab.exists()
            and vocab.stat().st_size >= 10_000
        )
    except OSError:
        return False


def _write_status(status: str, message: str, progress: int, error: str = "", **extra: Any) -> None:
    payload: dict[str, Any] = {
        "status": status,
        "message": message,
        "progress": max(0, min(100, int(progress))),
        "error": error,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    payload.update(extra)
    repair.STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    repair.STATUS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_marker(model_dir: Path, detail: str) -> None:
    repair.MODEL_MARKER.parent.mkdir(parents=True, exist_ok=True)
    repair.MODEL_MARKER.write_text(
        json.dumps(
            {
                "ready": True,
                "model_dir": str(model_dir),
                "detail": detail,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _read_pid() -> int:
    try:
        return int(DOWNLOAD_PID.read_text(encoding="utf-8").strip())
    except Exception:
        return 0


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            completed = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            return str(pid) in completed.stdout
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _stop_pid(pid: int) -> None:
    if pid <= 0:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=15, check=False)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception:
        pass


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

print(json.dumps({{"ready": True, "model_dir": str(model_dir)}}, ensure_ascii=False))
'''


def _start_download(python: str, model_dir: Path) -> int:
    DOWNLOAD_WORKER.parent.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_WORKER.write_text(_download_worker_source(model_dir), encoding="utf-8")
    stdout = open(DOWNLOAD_STDOUT, "w", encoding="utf-8")
    stderr = open(DOWNLOAD_STDERR, "w", encoding="utf-8")
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    process = subprocess.Popen(
        [python, str(DOWNLOAD_WORKER)],
        cwd=str(clone.ENGINE_DIR),
        stdout=stdout,
        stderr=stderr,
        creationflags=flags,
    )
    DOWNLOAD_PID.write_text(str(process.pid), encoding="utf-8")
    return process.pid


def _tail(path: Path, limit: int = 4000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-limit:].strip()
    except Exception:
        return ""


def _run_resumable_model_setup(python: str) -> tuple[Path, str]:
    model_dir = _model_dir()
    model_dir.mkdir(parents=True, exist_ok=True)
    if _model_complete(model_dir):
        return model_dir, f"XTTS model files already exist ({round(_directory_bytes(model_dir)/1048576,1)} MB)."

    previous_pid = _read_pid()
    if _process_alive(previous_pid):
        _stop_pid(previous_pid)

    start_bytes = _directory_bytes(model_dir)
    start_time = time.monotonic()
    last_bytes = start_bytes
    last_change = start_time
    pid = _start_download(python, model_dir)

    while True:
        now = time.monotonic()
        current_bytes = _directory_bytes(model_dir)
        if current_bytes > last_bytes:
            last_bytes = current_bytes
            last_change = now
        downloaded_mb = round(current_bytes / 1048576, 1)
        progress = min(97, max(5, int((current_bytes / EXPECTED_BYTES) * 97)))
        elapsed = int(now - start_time)
        _write_status(
            "installing",
            f"جاري تنزيل نموذج XTTS — تم تنزيل {downloaded_mb} MB — الوقت {elapsed//60:02d}:{elapsed%60:02d}",
            progress,
            downloaded_mb=downloaded_mb,
            elapsed_seconds=elapsed,
            phase="downloading",
            resumable=True,
            model_dir=str(model_dir),
        )
        if not _process_alive(pid):
            if _model_complete(model_dir):
                break
            error = _tail(DOWNLOAD_STDERR) or _tail(DOWNLOAD_STDOUT) or "XTTS download process ended early."
            raise RuntimeError(error)
        if now - last_change > STALL_SECONDS:
            _stop_pid(pid)
            raise RuntimeError("XTTS download stopped making progress. Press Setup again to resume from saved files.")
        if now - start_time > TOTAL_SECONDS:
            _stop_pid(pid)
            raise RuntimeError("XTTS setup reached the time limit. Press Setup again to resume from saved files.")
        time.sleep(4)

    detail = _tail(DOWNLOAD_STDOUT) or "XTTS model download completed."
    return model_dir, detail


def _read_status_resumable() -> dict[str, Any]:
    current = _ORIGINAL_READ_STATUS()
    model_dir = _model_dir()
    downloaded_mb = round(_directory_bytes(model_dir) / 1048576, 1)
    if repair.MODEL_MARKER.exists():
        current.update({"status": "ready", "progress": 100, "downloaded_mb": downloaded_mb, "resumable": True})
        return current
    if _model_complete(model_dir):
        current.update(
            {
                "status": "installing",
                "progress": 98,
                "downloaded_mb": downloaded_mb,
                "message": "اكتمل تنزيل ملفات XTTS. يجري فحص النموذج وإنهاء التجهيز...",
                "phase": "finalizing",
                "resumable": True,
            }
        )
        return current
    current.update({"downloaded_mb": downloaded_mb, "resumable": True})
    return current


def _worker_source_resumable() -> str:
    return _ORIGINAL_WORKER_SOURCE()


def _patched_model_source(source: str, model_dir: Path) -> str:
    return source


def _server_source_resumable() -> str:
    return _ORIGINAL_SERVER_SOURCE()


clone._read_status = _read_status_resumable
clone._setup_local_engine = _run_resumable_model_setup
clone.logger.info("XTTS resumable model setup patch is active.")
