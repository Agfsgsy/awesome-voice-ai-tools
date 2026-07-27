"""Persistent local XTTS runtime for consent-based Voice Clone Pro.

The heavyweight model is loaded once in an isolated localhost worker and reused.
Existing profiles, long source recordings, consent records, and generated files are
never deleted or modified. The worker accepts only a random local token.
"""
from __future__ import annotations

import atexit
import json
import os
import secrets
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from backend.api import voice_clone_routes as clone
from backend.core.logger import get_logger

router = APIRouter(prefix="/api/voice-clone-runtime", tags=["Voice Clone XTTS Runtime"])
logger = get_logger("voice_clone_xtts_runtime")

SERVER_FILE = clone.ENGINE_DIR / "xtts_persistent_server.py"
RUNTIME_FILE = clone.ENGINE_DIR / "xtts_runtime.json"
MODEL_MARKER = clone.ENGINE_DIR / "xtts_model_ready.json"
STDOUT_LOG = clone.ENGINE_DIR / "xtts_server_stdout.log"
STDERR_LOG = clone.ENGINE_DIR / "xtts_server_stderr.log"

_START_LOCK = threading.Lock()
_STATE_LOCK = threading.Lock()
_WARM_THREAD: threading.Thread | None = None
_PROCESS: subprocess.Popen[Any] | None = None
_STATE: dict[str, Any] = {
    "state": "stopped",
    "message": "خدمة XTTS غير مشغلة.",
    "device": "",
    "started_at": "",
    "error": "",
}


def _server_source() -> str:
    return r'''from __future__ import annotations
import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def send(handler, status, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("port and token are required")
    port = int(sys.argv[1])
    token = sys.argv[2]
    os.environ.setdefault("COQUI_TOS_AGREED", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    import torch
    from TTS.api import TTS
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = TTS("tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=False).to(device)

    class Handler(BaseHTTPRequestHandler):
        server_version = "IbnWaqadiXTTS/1.0"
        def log_message(self, _format, *_args):
            return
        def authorized(self):
            return self.headers.get("X-Ibn-Waqadi-Token", "") == token
        def do_GET(self):
            if not self.authorized():
                return send(self, 403, {"success": False, "error": "forbidden"})
            if self.path != "/health":
                return send(self, 404, {"success": False, "error": "not found"})
            return send(self, 200, {"success": True, "ready": True, "device": device})
        def do_POST(self):
            if not self.authorized():
                return send(self, 403, {"success": False, "error": "forbidden"})
            if self.path != "/generate":
                return send(self, 404, {"success": False, "error": "not found"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 2_000_000:
                    raise ValueError("invalid request size")
                job = json.loads(self.rfile.read(length).decode("utf-8"))
                text = str(job.get("text") or "").strip()
                samples = [str(item) for item in (job.get("samples") or [])]
                output = Path(str(job.get("output") or ""))
                language = str(job.get("language") or "ar").split("-")[0]
                if not text or not samples or not output.name:
                    raise ValueError("text, samples and output are required")
                model.tts_to_file(
                    text=text,
                    speaker_wav=samples,
                    language=language,
                    file_path=str(output),
                    split_sentences=True,
                )
                if not output.exists() or output.stat().st_size < 1024:
                    raise RuntimeError("XTTS did not create a usable output")
                return send(self, 200, {"success": True, "device": device, "output": str(output)})
            except Exception as exc:
                return send(self, 500, {
                    "success": False,
                    "error": str(exc),
                    "trace": traceback.format_exc()[-2500:],
                })

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.serve_forever(poll_interval=0.4)


if __name__ == "__main__":
    main()
'''


def _set_state(**updates: Any) -> None:
    with _STATE_LOCK:
        _STATE.update(updates)


def _state() -> dict[str, Any]:
    with _STATE_LOCK:
        return dict(_STATE)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _request(port: int, token: str, path: str, payload: dict[str, Any] | None, timeout: float) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=body,
        method="GET" if payload is None else "POST",
        headers={
            "X-Ibn-Waqadi-Token": token,
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(raw)
        except Exception:
            detail = {"error": raw}
        raise RuntimeError(str(detail.get("error") or detail)) from exc


def _probe(port: int, token: str, timeout: float = 2.0) -> dict[str, Any] | None:
    try:
        result = _request(port, token, "/health", None, timeout)
        return result if result.get("ready") else None
    except Exception:
        return None


def _read_runtime() -> tuple[int, str] | None:
    if not RUNTIME_FILE.exists():
        return None
    try:
        data = json.loads(RUNTIME_FILE.read_text(encoding="utf-8"))
        port = int(data.get("port") or 0)
        token = str(data.get("token") or "")
        if port > 0 and token:
            return port, token
    except Exception:
        pass
    return None


def _write_runtime(port: int, token: str, pid: int) -> None:
    RUNTIME_FILE.write_text(
        json.dumps({"port": port, "token": token, "pid": pid, "created_at": clone._now()}, indent=2),
        encoding="utf-8",
    )
    try:
        RUNTIME_FILE.chmod(0o600)
    except OSError:
        pass


def _log_tail(path: Path, limit: int = 2600) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-limit:]
    except Exception:
        return ""


def _ensure_server(timeout: float = 900.0) -> tuple[int, str, str]:
    global _PROCESS
    existing = _read_runtime()
    if existing:
        health = _probe(existing[0], existing[1])
        if health:
            device = str(health.get("device") or "cpu")
            _set_state(state="ready", message="XTTS محمل في الذاكرة وجاهز.", device=device, error="")
            return existing[0], existing[1], device

    if not MODEL_MARKER.exists():
        raise RuntimeError("نموذج XTTS الكامل غير مجهز. اضغط تجهيز المحرك مرة واحدة أولًا.")
    python = clone._engine_python()
    if not python.exists():
        raise RuntimeError("بيئة XTTS المحلية غير موجودة.")

    with _START_LOCK:
        existing = _read_runtime()
        if existing:
            health = _probe(existing[0], existing[1])
            if health:
                device = str(health.get("device") or "cpu")
                _set_state(state="ready", message="XTTS محمل في الذاكرة وجاهز.", device=device, error="")
                return existing[0], existing[1], device

        SERVER_FILE.write_text(_server_source(), encoding="utf-8")
        port = _free_port()
        token = secrets.token_urlsafe(32)
        env = {
            **os.environ,
            "COQUI_TOS_AGREED": "1",
            "PYTHONUTF8": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "OMP_NUM_THREADS": str(max(2, min(8, os.cpu_count() or 4))),
            "MKL_NUM_THREADS": str(max(2, min(8, os.cpu_count() or 4))),
        }
        _set_state(
            state="warming",
            message="جاري تحميل نموذج XTTS في الذاكرة مرة واحدة...",
            device="",
            started_at=clone._now(),
            error="",
        )
        STDOUT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with STDOUT_LOG.open("a", encoding="utf-8") as stdout, STDERR_LOG.open("a", encoding="utf-8") as stderr:
            _PROCESS = subprocess.Popen(
                [str(python), str(SERVER_FILE), str(port), token],
                cwd=str(clone.ENGINE_DIR),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        _write_runtime(port, token, int(_PROCESS.pid))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if _PROCESS.poll() is not None:
                detail = _log_tail(STDERR_LOG) or _log_tail(STDOUT_LOG) or "توقفت خدمة XTTS أثناء التحميل."
                RUNTIME_FILE.unlink(missing_ok=True)
                _set_state(state="failed", message="فشل تحميل XTTS في الذاكرة.", error=detail)
                raise RuntimeError(detail)
            health = _probe(port, token, timeout=2.0)
            if health:
                device = str(health.get("device") or "cpu")
                _set_state(state="ready", message="XTTS محمل في الذاكرة وجاهز.", device=device, error="")
                return port, token, device
            time.sleep(1.0)
        try:
            _PROCESS.terminate()
        except Exception:
            pass
        RUNTIME_FILE.unlink(missing_ok=True)
        _set_state(state="failed", message="انتهت مهلة تحميل XTTS في الذاكرة.", error="")
        raise RuntimeError("انتهت مهلة تحميل نموذج XTTS في الذاكرة بعد 15 دقيقة.")


def _warm_job() -> None:
    global _WARM_THREAD
    try:
        _ensure_server()
    except Exception as exc:
        logger.warning("XTTS background warm-up failed: %s", exc)
        _set_state(state="failed", message="فشل تسخين XTTS.", error=str(exc))
    finally:
        _WARM_THREAD = None


def generate(
    profile_id: str,
    manifest: dict[str, Any],
    references: list[Path],
    text: str,
    language: str,
    raw_output: Path,
) -> str:
    del profile_id, manifest
    port, token, device = _ensure_server()
    result = _request(
        port,
        token,
        "/generate",
        {
            "text": text,
            "language": language,
            "samples": [str(path) for path in references],
            "output": str(raw_output),
        },
        timeout=1200.0,
    )
    if not result.get("success") or not raw_output.exists() or raw_output.stat().st_size < 1024:
        raise RuntimeError(str(result.get("error") or "لم ينشئ XTTS ملفًا صالحًا."))
    return str(result.get("device") or device)


@router.get("/status")
async def runtime_status():
    current = _read_runtime()
    if current:
        health = await __import__("asyncio").to_thread(_probe, current[0], current[1])
        if health:
            _set_state(state="ready", message="XTTS محمل في الذاكرة وجاهز.", device=health.get("device", "cpu"), error="")
    return {
        "success": True,
        **_state(),
        "model_prepared": MODEL_MARKER.exists(),
        "persistent_worker": True,
    }


@router.post("/warm")
async def warm_runtime():
    global _WARM_THREAD
    if not MODEL_MARKER.exists():
        raise HTTPException(status_code=409, detail="نموذج XTTS الكامل غير مجهز. اضغط تجهيز المحرك أولًا.")
    current = _read_runtime()
    if current and await __import__("asyncio").to_thread(_probe, current[0], current[1]):
        return {"success": True, "started": False, "message": "XTTS محمل في الذاكرة وجاهز."}
    if _WARM_THREAD and _WARM_THREAD.is_alive():
        return {"success": True, "started": False, "message": "تسخين XTTS يعمل الآن في الخلفية."}
    _WARM_THREAD = threading.Thread(target=_warm_job, name="xtts-persistent-warm", daemon=True)
    _WARM_THREAD.start()
    return {"success": True, "started": True, "message": "بدأ تحميل XTTS في الذاكرة بالخلفية."}


def _shutdown() -> None:
    global _PROCESS
    if _PROCESS and _PROCESS.poll() is None:
        try:
            _PROCESS.terminate()
            _PROCESS.wait(timeout=8)
        except Exception:
            try:
                _PROCESS.kill()
            except Exception:
                pass
    RUNTIME_FILE.unlink(missing_ok=True)


atexit.register(_shutdown)
