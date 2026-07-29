#!/usr/bin/env python3
"""Verify the additive Voice Clone Pro 7 release without downloading models."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.api.voice_clone_routes import WORKER_FILE, _engine_python, _read_status  # noqa: E402
from backend.core.config import APP_RELEASE, APP_VERSION  # noqa: E402
from main import app  # noqa: E402


def main() -> int:
    paths = {getattr(route, "path", "") for route in app.routes}
    required = {
        "/api/voice-ai/engines",
        "/api/voice-ai/setup/xtts",
        "/api/voice-ai/audio/clone/ensemble",
        "/api/voice-clone/status",
        "/api/voice-clone/setup-local",
        "/api/voice-clone/generate",
    }
    missing = sorted(required - paths)
    setup = _read_status()
    report = {
        "version": APP_VERSION,
        "release": APP_RELEASE,
        "version_ok": APP_VERSION == "7.0.0",
        "required_routes_ok": not missing,
        "missing_routes": missing,
        "xtts_python": str(_engine_python()),
        "xtts_python_exists": _engine_python().exists(),
        "xtts_worker_exists": WORKER_FILE.exists(),
        "xtts_status": setup,
        "xtts_ready": (
            _engine_python().exists()
            and WORKER_FILE.exists()
            and setup.get("state") == "ready"
        ),
        "exact_match_guaranteed": False,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["version_ok"] or not report["required_routes_ok"]:
        return 1
    if not report["xtts_ready"]:
        print("\nXTTS لم يكتمل بعد. شغّل أمر التحديث مرة أخرى أو اضغط تجهيز XTTS من الواجهة.")
        return 2
    print("\nVoice Clone Pro 7 routes and XTTS are ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
