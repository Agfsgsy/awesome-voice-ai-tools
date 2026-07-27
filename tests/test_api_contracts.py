"""Regression tests for the packaged application's public JSON contracts."""

from __future__ import annotations

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from backend.api import studio_pro_routes
from backend.core.tts_registry import tts_registry
from main import app

BODY_ROUTES = {
    ("/api/tts", "POST"),
    ("/api/speech", "POST"),
    ("/api/interview-pro/scenario", "POST"),
    ("/api/interview-pro/render", "POST"),
    ("/api/studio/v1/interviews/scenario", "POST"),
    ("/api/studio/v1/interviews/render", "POST"),
    ("/api/ultimate/synthesize", "POST"),
    ("/api/ultimate/creative", "POST"),
    ("/api/ultimate/dialogue", "POST"),
}


def test_public_post_routes_accept_json_bodies() -> None:
    found: set[tuple[str, str]] = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or set():
            key = (route.path, method)
            if key not in BODY_ROUTES:
                continue
            found.add(key)
            assert route.dependant.body_params
            assert not {"req", "payload", "body"}.intersection(field.name for field in route.dependant.query_params)
    assert found == BODY_ROUTES


def test_openapi_marks_tts_requests_as_json_bodies() -> None:
    paths = app.openapi()["paths"]
    for path in ("/api/tts", "/api/speech"):
        operation = paths[path]["post"]
        assert "requestBody" in operation
        assert "application/json" in operation["requestBody"]["content"]
        assert not any(
            parameter["in"] == "query" and parameter["name"] == "req" for parameter in operation.get("parameters", [])
        )


def test_free_auto_engine_is_used_without_api_key(monkeypatch) -> None:
    class FreeEngine:
        async def generate(self, **_kwargs):
            return {
                "success": True,
                "engine": "edge",
                "file": "voice.mp3",
                "url": "/api/downloads/voice.mp3",
                "message": "ok",
            }

    original_get_plugin = tts_registry.get_plugin
    monkeypatch.setattr(
        tts_registry,
        "get_plugin",
        lambda name: FreeEngine() if name == "edge" else original_get_plugin(name),
    )

    response = TestClient(app).post(
        "/api/tts",
        json={"text": "اختبار صوت عربي", "engine": "auto", "language": "ar"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["engine_requested"] == "auto"
    assert payload["engine_used"] == "edge"
    assert payload["fallback"] is False


def test_invalid_tts_body_never_reports_query_req() -> None:
    response = TestClient(app).post("/api/tts", json={})
    assert response.status_code == 422
    errors = response.json()["detail"]
    assert all(error["loc"][:2] != ["query", "req"] for error in errors)


def test_root_opens_the_unified_studio() -> None:
    response = TestClient(app, follow_redirects=False).get("/")
    assert response.status_code == 307
    assert response.headers["location"] == "/static/ultimate_studio.html"


def test_free_first_health_contract() -> None:
    payload = TestClient(app).get("/api/studio/health").json()
    assert payload["success"] is True
    assert payload["default_engine"] == "edge"
    assert payload["automatic_free_fallback"] is True
    assert payload["explicit_cloud_choice_is_strict"] is True


def test_locked_desktop_export_never_loses_completed_audio(tmp_path, monkeypatch) -> None:
    source = tmp_path / "completed.wav"
    source.write_bytes(b"RIFF-completed-audio")
    export_dir = tmp_path / "exports"
    export_dir.mkdir()

    monkeypatch.setattr(studio_pro_routes, "_desktop_exports", lambda: export_dir)
    monkeypatch.setattr(
        studio_pro_routes.shutil,
        "copy2",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("locked")),
    )

    assert studio_pro_routes._copy_to_desktop(source) is None
    assert source.read_bytes() == b"RIFF-completed-audio"
