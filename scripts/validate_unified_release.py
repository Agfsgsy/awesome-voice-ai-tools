"""Build-time validation for Voice Clone Pro 6.2.0."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.routing import APIRoute

from backend.core.config import APP_VERSION, CLOUD_ENGINES, ENGINE_PRIORITY, FREE_ENGINES
from main import app

EXPECTED_VERSION = "6.2.0"


def fail(message: str) -> None:
    raise SystemExit(f"[VOICE CLONE VALIDATION ERROR] {message}")


def _text(path: str) -> str:
    file = ROOT / path
    if not file.exists():
        fail(f"Missing required file: {path}")
    return file.read_text(encoding="utf-8")


def _validate_versions() -> None:
    if APP_VERSION != EXPECTED_VERSION:
        fail(f"APP_VERSION is {APP_VERSION}, expected {EXPECTED_VERSION}")
    project = tomllib.loads(_text("pyproject.toml"))
    if project.get("project", {}).get("version") != EXPECTED_VERSION:
        fail("pyproject.toml does not use the release version")
    if json.loads(_text("config/default.json")).get("version") != EXPECTED_VERSION:
        fail("config/default.json does not use the release version")
    contracts = {
        "setup.py": f'version="{EXPECTED_VERSION}"',
        "installer/VoiceAIStudio.iss": f'#define MyAppVersion "{EXPECTED_VERSION}"',
        "frontend/static/studio_shell.html": f"VERSION='{EXPECTED_VERSION}'",
        "frontend/static/voice_clone.html": "الإصدار 6.2.0",
        "backend/core/config.py": 'APP_RELEASE = "Voice Clone Pro"',
    }
    for path, marker in contracts.items():
        if marker not in _text(path):
            fail(f"Version marker is missing from {path}: {marker}")


def _validate_engine_policy() -> None:
    if not FREE_ENGINES or FREE_ENGINES[0] != "edge":
        fail("Edge must remain the primary general free TTS engine")
    if ENGINE_PRIORITY[: len(FREE_ENGINES)] != FREE_ENGINES:
        fail("Free general engines must remain first in the normal TTS priority")
    if any(engine not in ENGINE_PRIORITY for engine in CLOUD_ENGINES):
        fail("A configured cloud engine is missing from ENGINE_PRIORITY")


def _validate_api_contracts() -> None:
    required_bodies = {
        ("/api/tts", "POST"),
        ("/api/speech", "POST"),
        ("/api/interview-pro/scenario", "POST"),
        ("/api/interview-pro/render", "POST"),
        ("/api/studio/v1/interviews/scenario", "POST"),
        ("/api/studio/v1/interviews/render", "POST"),
        ("/api/ultimate/synthesize", "POST"),
        ("/api/ultimate/creative", "POST"),
        ("/api/ultimate/dialogue", "POST"),
        ("/api/yemeni-creative/write", "POST"),
        ("/api/yemeni-creative/produce", "POST"),
        ("/api/voice-clone/generate", "POST"),
    }
    required_routes = required_bodies | {
        ("/api/voice-clone/status", "GET"),
        ("/api/voice-clone/setup-local", "POST"),
        ("/api/voice-clone/profiles", "POST"),
        ("/api/voice-clone/profiles", "GET"),
        ("/api/studio-pro/clone", "POST"),
    }
    found: set[tuple[str, str]] = set()
    duplicates: dict[tuple[str, str], list[str]] = defaultdict(list)
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or set():
            key = (route.path, method.upper())
            duplicates[key].append(route.name)
            query_names = {field.name for field in route.dependant.query_params}
            if query_names.intersection({"req", "payload", "body"}):
                fail(f"JSON payload became a query parameter on {key[1]} {key[0]}")
            if key in required_routes:
                found.add(key)
            if key in required_bodies and not route.dependant.body_params:
                fail(f"Missing JSON request body on {key[1]} {key[0]}")
    duplicate_routes = {key: names for key, names in duplicates.items() if len(names) > 1}
    if duplicate_routes:
        fail(f"Duplicate routes detected: {duplicate_routes}")
    missing = required_routes - found
    if missing:
        fail(f"Missing required routes: {sorted(missing)}")
    schema = app.openapi()
    for path, method in required_bodies:
        operation = schema.get("paths", {}).get(path, {}).get(method.lower(), {})
        if "requestBody" not in operation:
            fail(f"OpenAPI has no requestBody for {method} {path}")


def _validate_voice_clone() -> None:
    backend = _text("backend/api/voice_clone_routes.py")
    frontend = _text("frontend/static/voice_clone.html")
    shell = _text("frontend/static/studio_shell.html")
    legacy = _text("backend/api/studio_pro_routes.py")
    coqui = _text("backend/plugins/coqui_plugin.py")
    main = _text("main.py")

    backend_markers = (
        "consent_confirmed",
        "speaker_wav",
        "coqui-tts==0.27.5",
        "https://api.elevenlabs.io/v1/voices/add",
        "voice_clone_",
        "320k",
        "48000",
        "synthetic_voice",
        "استنساخ الصوت",
    )
    for marker in backend_markers:
        if marker not in backend:
            fail(f"Voice Clone backend is missing: {marker}")

    frontend_markers = (
        "/api/voice-clone/status",
        "/api/voice-clone/setup-local",
        "/api/voice-clone/profiles",
        "/api/voice-clone/generate",
        "أؤكد أنني صاحب الصوت",
        "لا يوجد محرك يضمن تطابقًا صوتيًا 100%",
    )
    for marker in frontend_markers:
        if marker not in frontend:
            fail(f"Voice Clone frontend is missing: {marker}")

    if "/static/voice_clone.html" not in shell:
        fail("The main interface does not expose Voice Clone Pro")
    if "voice_clone_router" not in main:
        fail("Voice Clone Pro router is not mounted")
    if "create_profile_from_uploads" not in legacy or "generate_from_profile" not in legacy:
        fail("The legacy clone box does not delegate to Voice Clone Pro")
    if "speaker_wav=str(reference)" not in coqui:
        fail("Coqui plugin still ignores the reference audio")
    if "async def clone(" not in coqui:
        fail("Coqui plugin does not expose a real clone method")


def _validate_existing_features() -> None:
    yemeni_backend = _text("backend/api/yemeni_creative_routes.py")
    yemeni_frontend = _text("frontend/static/yemeni_creative.html")
    shell = _text("frontend/static/studio_shell.html")
    for marker in ("zamil", "shila", "success_cinematic", "320k", "الأعمال اليمنية"):
        if marker not in yemeni_backend:
            fail(f"Existing Yemeni Creative feature is missing: {marker}")
    if "/api/yemeni-creative/produce" not in yemeni_frontend:
        fail("Existing Yemeni Creative frontend is incomplete")
    if "/static/yemeni_creative.html" not in shell:
        fail("Existing Yemeni Creative navigation was removed")
    runtime = _text("backend/api/download_export_runtime.py")
    if "shutil.copy2" not in runtime or "OUTPUTS_DIR" not in runtime:
        fail("Reliable Desktop audio export runtime is missing")


def main() -> None:
    _validate_versions()
    _validate_engine_policy()
    _validate_api_contracts()
    _validate_voice_clone()
    _validate_existing_features()
    print("[SUCCESS] Voice Clone Pro 6.2.0 contracts validated.")
    print("[SUCCESS] Consent profiles, XTTS speaker_wav, ElevenLabs IVC, legacy cloning and Desktop exports are connected.")


if __name__ == "__main__":
    main()
