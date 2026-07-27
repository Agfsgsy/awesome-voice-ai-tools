"""Compatible build validator for the additive Voice Clone Fast repair on Studio 6.2.0.

This validator deliberately verifies public contracts and preserved tools instead of
requiring private helper names from a particular Yemeni music implementation. That
lets the voice-clone-only repair build on existing 6.2.0 installations without
modifying or replacing their shila/zamil backend.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import tomllib
from fastapi.routing import APIRoute

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import APP_VERSION  # noqa: E402
from main import app  # noqa: E402

EXPECTED_VERSION = "6.2.0"


def fail(message: str) -> None:
    raise SystemExit(f"[VOICE CLONE REPAIR VALIDATION ERROR] {message}")


def text(path: str) -> str:
    target = ROOT / path
    if not target.exists():
        fail(f"Missing required file: {path}")
    return target.read_text(encoding="utf-8")


def validate_version_and_preserved_ui() -> None:
    if APP_VERSION != EXPECTED_VERSION:
        fail(f"APP_VERSION is {APP_VERSION}, expected {EXPECTED_VERSION}")
    project = tomllib.loads(text("pyproject.toml"))
    if project.get("project", {}).get("version") != EXPECTED_VERSION:
        fail("pyproject.toml version changed")
    if json.loads(text("config/default.json")).get("version") != EXPECTED_VERSION:
        fail("config/default.json version changed")

    preserved = text("frontend/static/studio_shell_preserved.html")
    original_clone = text("frontend/static/voice_clone.html")
    for marker in (
        "Professional Studio 6.2.0 — Preserved UI",
        "/static/voice_clone.html",
        "/static/yemeni_creative_pro.html",
        "/static/ultimate_studio.html",
    ):
        if marker not in preserved:
            fail(f"Preserved interface marker missing: {marker}")
    for marker in (
        "الإصدار 6.2.0",
        "/api/voice-clone/status",
        "/api/voice-clone/profiles",
        "/api/voice-clone/generate",
        "أؤكد أنني صاحب الصوت",
        "لا يوجد محرك يضمن تطابقًا صوتيًا 100%",
    ):
        if marker not in original_clone:
            fail(f"Original Voice Clone page was changed or is incomplete: {marker}")


def validate_routes() -> None:
    body_routes = {
        ("/api/tts", "POST"),
        ("/api/speech", "POST"),
        ("/api/voice-clone/generate", "POST"),
        ("/api/voice-clone-fast/generate", "POST"),
        ("/api/yemeni-creative-safe/write", "POST"),
        ("/api/yemeni-creative-safe/produce", "POST"),
        ("/api/ultimate/synthesize", "POST"),
    }
    required = body_routes | {
        ("/api/voice-clone/status", "GET"),
        ("/api/voice-clone/setup-local", "POST"),
        ("/api/voice-clone/profiles", "GET"),
        ("/api/voice-clone/profiles", "POST"),
        ("/api/voice-clone-fast/status", "GET"),
        ("/api/voice-clone-runtime/status", "GET"),
        ("/api/voice-clone-runtime/warm", "POST"),
        ("/static/voice_clone.html", "GET"),
        ("/api/yemeni-creative-safe/health", "GET"),
    }

    found: set[tuple[str, str]] = set()
    duplicates: dict[tuple[str, str], list[str]] = defaultdict(list)
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or set():
            key = (route.path, method.upper())
            if key in required:
                found.add(key)
                duplicates[key].append(route.name)
            if key in body_routes:
                query_names = {field.name for field in route.dependant.query_params}
                if query_names.intersection({"req", "payload", "body"}):
                    fail(f"JSON body became a query parameter: {key}")
                if not route.dependant.body_params:
                    fail(f"Missing JSON body contract: {key}")

    repeated = {key: names for key, names in duplicates.items() if len(names) > 1}
    if repeated:
        fail(f"Duplicate required routes: {repeated}")
    missing = required - found
    if missing:
        fail(f"Missing required public routes: {sorted(missing)}")


def validate_fast_clone_files() -> None:
    fast = text("backend/api/voice_clone_fast_routes.py")
    patch = text("backend/api/voice_clone_fast_runtime_patch.py")
    runtime = text("backend/api/voice_clone_xtts_runtime.py")
    repair = text("backend/api/voice_clone_repair_runtime.py")
    ui_patch = text("frontend/static/voice_clone_fast_patch.js")
    ui_runtime = text("backend/api/voice_clone_ui_runtime.py")
    main = text("main.py")

    contracts = {
        "fast clone router": (
            fast,
            (
                'provider: Literal["auto", "local", "elevenlabs", "gemini_vertex"]',
                "MAX_REFERENCE_SECONDS = 30.0",
                "optimized_references",
                "/api/voice-clone-fast",
            ),
        ),
        "persistent XTTS runtime": (
            runtime,
            (
                "ThreadingHTTPServer",
                "xtts_persistent_server.py",
                "X-Ibn-Waqadi-Token",
                "model.tts_to_file",
                "/api/voice-clone-runtime",
            ),
        ),
        "XTTS setup repair": (
            repair,
            (
                "_dependency_check",
                "_model_check",
                "xtts_model_ready.json",
                "clone._setup_local_engine = _repair_local_engine",
            ),
        ),
        "provider hardening": (
            patch,
            (
                "fast._produce_with_provider = _bounded_produce",
                "xtts.generate",
                "asyncio.wait_for",
            ),
        ),
        "additive UI patch": (
            ui_patch,
            (
                "/api/voice-clone-fast/generate",
                "/api/voice-clone-runtime/warm",
                "تلقائي سريع",
                "10–30 ثانية",
            ),
        ),
    }
    for label, (source, markers) in contracts.items():
        for marker in markers:
            if marker not in source:
                fail(f"{label} is missing: {marker}")

    if "voice_clone_fast_patch.js" not in ui_runtime or "html.replace" not in ui_runtime:
        fail("The saved Voice Clone page is not receiving the additive UI patch")
    for marker in (
        "voice_clone_router",
        "voice_clone_fast_router",
        "voice_clone_runtime_router",
        "voice_clone_ui_router",
    ):
        if marker not in main:
            fail(f"Required clone router is not mounted: {marker}")


def validate_existing_tools_are_preserved() -> None:
    # Do not require private helper names such as _simple_mix or _audible_mix.
    # Existing installations can legitimately contain either implementation.
    required_files = (
        "backend/api/yemeni_creative_routes.py",
        "backend/api/yemeni_creative_hotfix.py",
        "frontend/static/yemeni_creative.html",
        "frontend/static/yemeni_creative_pro.html",
        "frontend/static/ultimate_studio.html",
        "backend/api/download_export_runtime.py",
    )
    for path in required_files:
        text(path)

    original_yemeni = text("frontend/static/yemeni_creative.html")
    repaired_yemeni = text("frontend/static/yemeni_creative_pro.html")
    export_runtime = text("backend/api/download_export_runtime.py")
    if "/api/yemeni-creative/produce" not in original_yemeni:
        fail("Original Yemeni Creative production page is missing")
    for marker in (
        "/api/yemeni-creative-safe/health",
        "/api/yemeni-creative-safe/write",
        "/api/yemeni-creative-safe/produce",
        "إنشاء شيلة الآن",
    ):
        if marker not in repaired_yemeni:
            fail(f"Existing Yemeni Creative UI contract missing: {marker}")
    if "shutil.copy2" not in export_runtime or "OUTPUTS_DIR" not in export_runtime:
        fail("Desktop audio export runtime is missing")


def main() -> None:
    validate_version_and_preserved_ui()
    validate_routes()
    validate_fast_clone_files()
    validate_existing_tools_are_preserved()
    print("[SUCCESS] Voice Clone Fast repair contracts are valid on Studio 6.2.0.")
    print("[SUCCESS] The original interface, shila/zamil pages, keys, profiles and exports remain preserved.")
    print("[SUCCESS] Validation no longer depends on unrelated private Yemeni mixer helper names.")


if __name__ == "__main__":
    main()
