"""Build-time validation for the unified stable desktop release."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.routing import APIRoute  # noqa: E402
from backend.core.config import APP_VERSION, ENGINE_PRIORITY, MANUAL_ONLY_ENGINES  # noqa: E402
from main import app  # noqa: E402


def fail(message: str) -> None:
    raise SystemExit(f"[UNIFIED VALIDATION ERROR] {message}")


def main() -> None:
    if APP_VERSION != "5.0.0":
        fail(f"APP_VERSION is {APP_VERSION}, expected 5.0.0")
    if any(engine in ENGINE_PRIORITY for engine in MANUAL_ONLY_ENGINES):
        fail("A manual-only/free engine is present in automatic ENGINE_PRIORITY")

    required = {
        ("/api/interview-pro/scenario", "POST"),
        ("/api/interview-pro/render", "POST"),
        ("/api/studio/v1/interviews/scenario", "POST"),
        ("/api/studio/v1/interviews/render", "POST"),
    }
    found: set[tuple[str, str]] = set()

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or set():
            key = (route.path, method.upper())
            if key not in required:
                continue
            if key in found:
                fail(f"Duplicate unified route: {key[1]} {key[0]}")
            found.add(key)
            query_names = {field.name for field in route.dependant.query_params}
            if query_names.intersection({"req", "payload", "body"}):
                fail(f"Request body became a query parameter on {key[1]} {key[0]}")
            if not route.dependant.body_params:
                fail(f"Missing JSON request body on {key[1]} {key[0]}")

    missing = required - found
    if missing:
        fail(f"Missing required unified routes: {sorted(missing)}")

    schema = app.openapi()
    for path, method in required:
        operation = schema.get("paths", {}).get(path, {}).get(method.lower(), {})
        if "requestBody" not in operation:
            fail(f"OpenAPI has no requestBody for {method} {path}")
        parameters = operation.get("parameters", [])
        if any(item.get("in") == "query" and item.get("name") in {"req", "payload", "body"} for item in parameters):
            fail(f"OpenAPI exposes an invalid query payload for {method} {path}")

    route_source = (ROOT / "backend" / "api" / "interview_pro_routes.py").read_text(encoding="utf-8")
    forbidden = [
        'candidates.append("edge")',
        "candidates.append('edge')",
        'candidates.extend(["gemini", "edge"])',
        "candidates.extend(['gemini', 'edge'])",
    ]
    if any(token in route_source for token in forbidden):
        fail("Interview production contains an automatic free-engine fallback")

    print("[SUCCESS] Unified Studio 5.0 contracts validated.")
    print("[SUCCESS] JSON body contracts and Cloud-Only policy are valid.")


if __name__ == "__main__":
    main()
