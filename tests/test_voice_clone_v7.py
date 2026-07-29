from __future__ import annotations

from backend.api.voice_engine_suite_routes import (
    _engine_unavailable_detail,
    _normalize_engine,
)
from backend.core.config import APP_RELEASE, APP_VERSION


def test_voice_clone_v7_release_metadata():
    assert APP_VERSION == "7.0.0"
    assert APP_RELEASE == "Voice Clone Multi-Engine Pro"


def test_clone_engine_aliases_resolve_to_xtts():
    for alias in ("xtts", "xtts-v2", "xtts_v2", "coqui", "coqui-tts", "coqui_xtts"):
        assert _normalize_engine(alias) == "xtts"


def test_engine_unavailable_is_actionable():
    detail = _engine_unavailable_detail([])
    assert detail["error_code"] == "ENGINE_NOT_AVAILABLE"
    assert detail["setup_endpoint"] == "/api/voice-ai/setup/xtts"
    assert detail["status_endpoint"] == "/api/voice-ai/engines"
    assert detail["windows_command"] == "UPDATE_AND_INSTALL_VOICE_CLONE_PRO_7.bat"


def test_v7_routes_are_registered():
    from main import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/api/voice-ai/engines" in paths
    assert "/api/voice-ai/setup/xtts" in paths
    assert "/api/voice-ai/setup/all" in paths
    assert "/api/voice-ai/audio/clone/ensemble" in paths
    assert "/api/voice-ai/song/generate" in paths
