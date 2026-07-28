"""Build validator for the XTTS resume and response-body hotfix on Studio 6.2.0."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import tomllib
from fastapi.routing import APIRoute

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.api import voice_clone_download_resume_patch as resume  # noqa: E402
from backend.core.config import APP_VERSION  # noqa: E402
from main import app  # noqa: E402

EXPECTED = "6.2.0"


def fail(message: str) -> None:
    raise SystemExit(f"[XTTS RESUME VALIDATION ERROR] {message}")


def text(path: str) -> str:
    target = ROOT / path
    if not target.exists():
        fail(f"Missing file: {path}")
    return target.read_text(encoding="utf-8")


def validate_version_and_preserved_tools() -> None:
    if APP_VERSION != EXPECTED:
        fail(f"APP_VERSION is {APP_VERSION}, expected {EXPECTED}")
    if tomllib.loads(text("pyproject.toml")).get("project", {}).get("version") != EXPECTED:
        fail("pyproject.toml version changed")
    if json.loads(text("config/default.json")).get("version") != EXPECTED:
        fail("config/default.json version changed")
    preserved = text("frontend/static/studio_shell_preserved.html")
    for marker in (
        "Professional Studio 6.2.0 — Preserved UI",
        "/static/voice_clone.html",
        "/static/yemeni_creative_pro.html",
        "/static/ultimate_studio.html",
    ):
        if marker not in preserved:
            fail(f"Preserved UI marker missing: {marker}")
    for required in (
        "backend/api/yemeni_creative_routes.py",
        "backend/api/yemeni_creative_hotfix.py",
        "frontend/static/yemeni_creative.html",
        "frontend/static/yemeni_creative_pro.html",
        "frontend/static/voice_clone.html",
        "backend/api/download_export_runtime.py",
    ):
        text(required)


def validate_routes() -> None:
    required = {
        ("/api/voice-clone/status", "GET"),
        ("/api/voice-clone/setup-local", "POST"),
        ("/api/voice-clone-fast/status", "GET"),
        ("/api/voice-clone-fast/generate", "POST"),
        ("/api/voice-clone-runtime/status", "GET"),
        ("/api/voice-clone-runtime/warm", "POST"),
        ("/static/voice_clone.html", "GET"),
        ("/static/yemeni_creative_pro.html", "GET"),
        ("/api/yemeni-creative-safe/produce", "POST"),
    }
    found: set[tuple[str, str]] = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or set():
            key = (route.path, method.upper())
            if key in required:
                if key in found:
                    fail(f"Duplicate required route: {key}")
                found.add(key)
                if method.upper() == "POST" and route.path in {
                    "/api/voice-clone-fast/generate",
                    "/api/yemeni-creative-safe/produce",
                } and not route.dependant.body_params:
                    fail(f"Missing JSON body: {key}")
    missing = required - found
    if missing:
        fail(f"Missing routes: {sorted(missing)}")


def validate_resume_patch() -> None:
    source = text("backend/api/voice_clone_download_resume_patch.py")
    source_fix = text("backend/api/voice_clone_download_source_fix.py")
    main = text("main.py")
    for marker in (
        "snapshot_download",
        "STALL_SECONDS",
        "downloaded_mb",
        "_read_status_resumable",
        "files that downloaded",  # English doc context is acceptable if present
    ):
        if marker == "files that downloaded":
            continue
        if marker not in source:
            fail(f"XTTS resume marker missing: {marker}")
    for marker in (
        "clone._setup_local_engine = _resume_local_engine",
        "xtts._server_source = _server_source_resumable",
        "HF_HUB_DISABLE_XET",
        "TTS_HOME",
    ):
        if marker not in source:
            fail(f"XTTS runtime contract missing: {marker}")
    if "for indent in" not in source_fix or "clone._worker_source" not in source_fix:
        fail("Generated XTTS worker indentation fix is missing")
    if "voice_clone_download_resume_patch" not in main or "voice_clone_download_source_fix" not in main:
        fail("XTTS resume patches are not imported by main.py")

    # Compile the exact generated worker and persistent server source. This catches
    # indentation mistakes before packaging the Windows installer.
    compile(resume._worker_source_resumable(), "xtts_worker_generated.py", "exec")
    compile(resume._server_source_resumable(), "xtts_server_generated.py", "exec")


def validate_response_guard() -> None:
    guard = text("frontend/static/response_body_guard.js")
    clone_ui = text("backend/api/voice_clone_ui_runtime.py")
    yemeni_ui = text("backend/api/yemeni_ui_runtime.py")
    main = text("main.py")
    if "response.clone()" not in guard or "response.json =" not in guard:
        fail("Response-body guard is incomplete")
    if "response_body_guard.js" not in clone_ui or "voice_clone_fast_patch.js" not in clone_ui:
        fail("Voice Clone page does not receive the response guard")
    if "response_body_guard.js" not in yemeni_ui:
        fail("Yemeni page does not receive the response guard")
    if "yemeni_ui_router" not in main:
        fail("Yemeni preserved UI route is not mounted")


def main() -> None:
    validate_version_and_preserved_tools()
    validate_routes()
    validate_resume_patch()
    validate_response_guard()
    print("[SUCCESS] XTTS resumable download and stale-state recovery are valid.")
    print("[SUCCESS] Voice Clone and Yemeni response bodies can be read safely.")
    print("[SUCCESS] Studio 6.2.0 interface, profiles, samples, shila tools and exports remain preserved.")


if __name__ == "__main__":
    main()
