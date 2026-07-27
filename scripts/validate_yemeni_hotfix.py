"""Regression validation for the additive Yemeni Creative repair."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.routing import APIRoute

from backend.api.yemeni_creative_hotfix import SafeWriteRequest, _write_local
from backend.core.config import APP_VERSION
from main import app


def fail(message: str) -> None:
    raise SystemExit(f"[YEMENI HOTFIX ERROR] {message}")


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    if APP_VERSION != "6.2.0":
        fail(f"The repair must preserve Voice Clone Pro 6.2.0, found {APP_VERSION}")

    routes = {(route.path, method) for route in app.routes if isinstance(route, APIRoute) for method in (route.methods or set())}
    required = {
        ("/api/voice-clone/generate", "POST"),
        ("/api/yemeni-creative/write", "POST"),
        ("/api/yemeni-creative/produce", "POST"),
        ("/api/yemeni-creative-safe/health", "GET"),
        ("/api/yemeni-creative-safe/write", "POST"),
        ("/api/yemeni-creative-safe/produce", "POST"),
    }
    missing = required - routes
    if missing:
        fail(f"Missing routes: {sorted(missing)}")

    shell = text("frontend/static/studio_shell.html")
    for marker in (
        "/static/voice_clone.html",
        "/static/yemeni_creative_pro.html",
        "Professional Studio 6.2.0",
        "المقابلات البشرية Pro",
        "الحوار الطبيعي Ultra",
        "الاستوديو الكامل",
    ):
        if marker not in shell:
            fail(f"The restored 6.2 interface is missing: {marker}")

    page = text("frontend/static/yemeni_creative_pro.html")
    for marker in (
        "quickShila",
        "quickZamil",
        "writeLocal",
        "writeGemini",
        "produce",
        "/api/yemeni-creative-safe/write",
        "/api/yemeni-creative-safe/produce",
        "إنشاء شيلة الآن",
        "إنتاج الشيلة أو العمل الآن",
    ):
        if marker not in page:
            fail(f"The repaired Yemeni page is missing: {marker}")

    for content_type in ("shila", "zamil", "success", "dedication", "poem"):
        title, body = _write_local(
            SafeWriteRequest(
                content_type=content_type,
                recipient="علي",
                occasion="نجاح",
                subject="قصة كفاح وتقدم خطوة خطوة",
                keywords="العزيمة، اليمن، النجاح",
                writer_provider="local",
            )
        )
        if len(title.strip()) < 2 or len(body.splitlines()) < 6:
            fail(f"Local creation failed for {content_type}")

    desktop = text("desktop_app.py")
    if "/static/studio_shell.html" not in desktop:
        fail("The desktop launcher no longer opens the restored interface")

    print("[SUCCESS] Voice Clone Pro 6.2.0 interface is preserved.")
    print("[SUCCESS] Shila, zamil, success, dedication and poem creation buttons are wired.")
    print("[SUCCESS] Local writing works without Gemini and the original routes remain available.")


if __name__ == "__main__":
    main()
