"""Build-time validation for the unified free-first desktop release."""
from __future__ import annotations

import json
import re
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

EXPECTED_VERSION = "5.1.0"


def fail(message: str) -> None:
    raise SystemExit(f"[UNIFIED VALIDATION ERROR] {message}")


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _validate_versions() -> None:
    if APP_VERSION != EXPECTED_VERSION:
        fail(f"APP_VERSION is {APP_VERSION}, expected {EXPECTED_VERSION}")

    project = tomllib.loads(_text("pyproject.toml"))
    if project.get("project", {}).get("version") != EXPECTED_VERSION:
        fail("pyproject.toml does not use the unified version")

    default_config = json.loads(_text("config/default.json"))
    if default_config.get("version") != EXPECTED_VERSION:
        fail("config/default.json does not use the unified version")

    version_contracts = {
        "setup.py": f'version="{EXPECTED_VERSION}"',
        "installer/VoiceAIStudio.iss": f'#define MyAppVersion "{EXPECTED_VERSION}"',
        "frontend/static/studio_shell.html": f"VERSION='{EXPECTED_VERSION}'",
    }
    for path, marker in version_contracts.items():
        if marker not in _text(path):
            fail(f"{path} does not use version {EXPECTED_VERSION}")


def _validate_free_first_policy() -> None:
    if not FREE_ENGINES or FREE_ENGINES[0] != "edge":
        fail("Edge must be the primary free neural engine")
    if ENGINE_PRIORITY[: len(FREE_ENGINES)] != FREE_ENGINES:
        fail("Free engines must come before cloud engines")
    if any(engine not in ENGINE_PRIORITY for engine in CLOUD_ENGINES):
        fail("Cloud engines are missing from the explicit engine list")

    interview_source = _text("backend/api/interview_pro_routes.py")
    if 'engine: str = Field(default="edge"' not in interview_source:
        fail("Interview Pro is not free-first")

    interview_ui = _text("frontend/static/interview_pro.html")
    if '<option value="edge"' not in interview_ui:
        fail("Interview Pro has no free neural engine option")
    if "الصوت المجاني الميكانيكي" in _text("frontend/static/interview_ultra.html"):
        fail("Dialogue Ultra still describes the free neural voice as mechanical")

    producer = _text("frontend/static/producer.html")
    if '<option value="edge" selected>' not in producer or "voiceCatalogs" not in producer:
        fail("Producer does not expose engine-specific free voice choices")
    if '<option value="piper">' not in producer:
        fail("Producer does not expose the offline Piper engine")


def _validate_api_contracts() -> None:
    required_bodies = {
        ("/api/tts", "POST"),
        ("/api/speech", "POST"),
        ("/api/interview-pro/scenario", "POST"),
        ("/api/interview-pro/render", "POST"),
        ("/api/studio/v1/interviews/scenario", "POST"),
        ("/api/studio/v1/interviews/render", "POST"),
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
            if key in required_bodies:
                found.add(key)
                if not route.dependant.body_params:
                    fail(f"Missing JSON request body on {key[1]} {key[0]}")

    duplicate_routes = {key: names for key, names in duplicates.items() if len(names) > 1}
    if duplicate_routes:
        fail(f"Duplicate routes detected: {duplicate_routes}")

    missing = required_bodies - found
    if missing:
        fail(f"Missing required routes: {sorted(missing)}")

    schema = app.openapi()
    for path, method in required_bodies:
        operation = schema.get("paths", {}).get(path, {}).get(method.lower(), {})
        if "requestBody" not in operation:
            fail(f"OpenAPI has no requestBody for {method} {path}")
        parameters = operation.get("parameters", [])
        if any(
            item.get("in") == "query" and item.get("name") in {"req", "payload", "body"}
            for item in parameters
        ):
            fail(f"OpenAPI exposes an invalid query payload for {method} {path}")


def _validate_frontend_contracts() -> None:
    shell = _text("frontend/static/studio_shell.html")
    if "studio:navigate" not in shell or "addEventListener('message'" not in shell:
        fail("The dashboard navigation bridge is missing")

    old_badges = re.compile(
        r"(Producer 2\.8|Studio 2\.7|الإصدار 3\.4|Strict Cloud 3\.8|Smart Probe 4\.2)"
    )
    for path in (
        "frontend/static/dashboard.html",
        "frontend/static/producer.html",
        "frontend/static/pro.html",
        "frontend/static/interview_ultra.html",
        "frontend/static/gemini_keys.html",
    ):
        if old_badges.search(_text(path)):
            fail(f"{path} still contains a fragmented legacy version")


def main() -> None:
    _validate_versions()
    _validate_free_first_policy()
    _validate_api_contracts()
    _validate_frontend_contracts()
    print("[SUCCESS] Unified Studio 5.1 contracts validated.")
    print("[SUCCESS] Versions, JSON bodies, navigation, and free-first audio are consistent.")


if __name__ == "__main__":
    main()
