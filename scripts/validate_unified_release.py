"""Build-time validation for the Yemeni Creative desktop release."""
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

EXPECTED_VERSION = "6.1.0"


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
    if json.loads(_text("config/default.json")).get("version") != EXPECTED_VERSION:
        fail("config/default.json does not use the unified version")
    contracts = {
        "setup.py": f'version="{EXPECTED_VERSION}"',
        "installer/VoiceAIStudio.iss": f'#define MyAppVersion "{EXPECTED_VERSION}"',
        "frontend/static/studio_shell.html": f"VERSION='{EXPECTED_VERSION}'",
        "frontend/static/yemeni_creative.html": "الإصدار 6.1.0",
        ".github/workflows/build-windows-installer.yml": "IbnWaqadiStudio-6.1-Windows-Setup",
    }
    for path, marker in contracts.items():
        if marker not in _text(path):
            fail(f"{path} does not use release {EXPECTED_VERSION}")
    if "IbnWaqadiStudio-6.1-Windows-Portable" not in _text(".github/workflows/build-windows-installer.yml"):
        fail("Windows portable artifact does not use version 6.1")


def _validate_engine_policy() -> None:
    if not FREE_ENGINES or FREE_ENGINES[0] != "edge":
        fail("Edge must remain the primary free neural engine")
    if ENGINE_PRIORITY[: len(FREE_ENGINES)] != FREE_ENGINES:
        fail("Free engines must come before explicit cloud engines")
    if any(engine not in ENGINE_PRIORITY for engine in CLOUD_ENGINES):
        fail("A cloud engine is missing from the explicit engine list")
    source = _text("backend/api/yemeni_creative_routes.py")
    if "_synthesize_strict" not in source:
        fail("Yemeni Creative must use strict provider selection")
    if "provider = request.provider" not in source:
        fail("Yemeni Creative does not preserve the selected provider")


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


def _validate_yemeni_creative() -> None:
    backend = _text("backend/api/yemeni_creative_routes.py")
    frontend = _text("frontend/static/yemeni_creative.html")
    shell = _text("frontend/static/studio_shell.html")
    desktop = _text("desktop_app.py")
    for marker in (
        "zamil",
        "shila",
        "success_cinematic",
        "dedication_warm",
        "libmp3lame",
        "320k",
        "48000",
        "الأعمال اليمنية",
        "original_text_and_music",
    ):
        if marker not in backend:
            fail(f"Yemeni backend is missing: {marker}")
    for marker in (
        "/api/yemeni-creative/catalog",
        "/api/yemeni-creative/write",
        "/api/yemeni-creative/produce",
        "تحميل الماستر النهائي",
        "فتح حزمة المشروع",
    ):
        if marker not in frontend:
            fail(f"Yemeni frontend is missing: {marker}")
    if "/static/yemeni_creative.html" not in shell:
        fail("The unified shell does not expose Yemeni Creative")
    if "/static/studio_shell.html" not in desktop:
        fail("The Windows launcher does not open the unified 6.1 shell")
    if "لا يقتبس" not in backend or "لا تطلب تقليد" not in frontend:
        fail("Original-only copyright safeguards are missing")


def _validate_download_runtime() -> None:
    runtime = _text("backend/api/download_export_runtime.py")
    if "shutil.copy2" not in runtime or "OUTPUTS_DIR" not in runtime:
        fail("Reliable audio download/export runtime is missing")


def main() -> None:
    _validate_versions()
    _validate_engine_policy()
    _validate_api_contracts()
    _validate_yemeni_creative()
    _validate_download_runtime()
    print("[SUCCESS] Yemeni Creative 6.1.0 contracts validated.")
    print("[SUCCESS] Original writing, strict voices, 320 kbps mastering and Desktop project packs are consistent.")


if __name__ == "__main__":
    main()
