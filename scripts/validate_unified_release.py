"""Build-time validation for Voice Clone Pro 6.2.0 and the additive Yemeni repair."""
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
        ("/api/yemeni-creative-safe/write", "POST"),
        ("/api/yemeni-creative-safe/produce", "POST"),
        ("/api/voice-clone/generate", "POST"),
    }
    required_routes = required_bodies | {
        ("/api/voice-clone/status", "GET"),
        ("/api/voice-clone/setup-local", "POST"),
        ("/api/voice-clone/profiles", "POST"),
        ("/api/voice-clone/profiles", "GET"),
        ("/api/studio-pro/clone", "POST"),
        ("/api/yemeni-creative-safe/health", "GET"),
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

    for marker in (
        "consent_confirmed",
        "speaker_wav",
        "coqui-tts==0.27.5",
        "https://api.elevenlabs.io/v1/voices/add",
        "voice_clone_",
        "320k",
        "48000",
        "synthetic_voice",
        "استنساخ الصوت",
    ):
        if marker not in backend:
            fail(f"Voice Clone backend is missing: {marker}")

    for marker in (
        "/api/voice-clone/status",
        "/api/voice-clone/setup-local",
        "/api/voice-clone/profiles",
        "/api/voice-clone/generate",
        "أؤكد أنني صاحب الصوت",
        "لا يوجد محرك يضمن تطابقًا صوتيًا 100%",
    ):
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


def _validate_yemeni_features() -> None:
    original_backend = _text("backend/api/yemeni_creative_routes.py")
    original_frontend = _text("frontend/static/yemeni_creative.html")
    repaired_backend = _text("backend/api/yemeni_creative_hotfix.py")
    repaired_frontend = _text("frontend/static/yemeni_creative_pro.html")
    shell = _text("frontend/static/studio_shell.html")
    main = _text("main.py")

    for marker in ("zamil", "shila", "success_cinematic", "320k", "الأعمال اليمنية"):
        if marker not in original_backend:
            fail(f"Existing Yemeni Creative feature is missing: {marker}")
    if "/api/yemeni-creative/produce" not in original_frontend:
        fail("The original Yemeni Creative frontend was removed")

    for marker in (
        "/api/yemeni-creative-safe/health",
        "/api/yemeni-creative-safe/write",
        "/api/yemeni-creative-safe/produce",
        "quickShila",
        "quickZamil",
        "إنشاء شيلة الآن",
        "إنتاج الشيلة أو العمل الآن",
    ):
        if marker not in repaired_frontend:
            fail(f"The repaired Yemeni frontend is missing: {marker}")

    for marker in ("asyncio.wait_for", "_write_local", "_simple_mix", "12, token", "safe_hotfix"):
        if marker not in repaired_backend:
            fail(f"The repaired Yemeni backend is missing: {marker}")

    if "/static/yemeni_creative_pro.html" not in shell:
        fail("The 6.2 interface does not open the repaired Yemeni page")
    if "yemeni_creative_router" not in main or "yemeni_creative_safe_router" not in main:
        fail("The original and repaired Yemeni routers are not both mounted")

    runtime = _text("backend/api/download_export_runtime.py")
    if "shutil.copy2" not in runtime or "OUTPUTS_DIR" not in runtime:
        fail("Reliable Desktop audio export runtime is missing")


def main() -> None:
    _validate_versions()
    _validate_engine_policy()
    _validate_api_contracts()
    _validate_voice_clone()
    _validate_yemeni_features()
    print("[SUCCESS] Voice Clone Pro 6.2.0 interface and tools are preserved.")
    print("[SUCCESS] The additive Yemeni shila/zamil repair is connected without deleting the original feature.")


if __name__ == "__main__":
    main()
