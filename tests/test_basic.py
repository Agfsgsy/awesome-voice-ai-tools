"""اختبارات أساسية للمشروع"""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_config_import():
    from backend.core.config import APP_NAME, APP_VERSION, APP_PORT
    assert APP_NAME == "Voice AI Studio Arabic"
    assert APP_VERSION == "2.0.0"
    assert APP_PORT == 8000


def test_logger_import():
    from backend.core.logger import get_logger
    logger = get_logger("test")
    assert logger is not None


def test_audio_utils_import():
    from backend.core.audio_utils import generate_sine_wave
    data = generate_sine_wave(frequency=440, duration=0.1)
    assert len(data) > 0
    assert isinstance(data, bytes)


def test_plugin_manager_import():
    from backend.core.plugin_manager import PluginManager
    from pathlib import Path
    pm = PluginManager(Path("."))
    assert pm is not None


def test_tts_engine_import():
    from backend.core.tts_engine import TTSEngine
    engine = TTSEngine()
    engines = engine.list_engines()
    assert len(engines) > 0
    assert any(e["name"] == "kokoro" for e in engines)


def test_health_checks():
    from backend.core.health import run_all_checks
    checks = run_all_checks(8001)
    assert len(checks) > 0
    assert all("name" in c for c in checks)
    assert all("ok" in c for c in checks)


@pytest.mark.asyncio
async def test_tts_fallback():
    from backend.core.tts_engine import tts
    result = await tts.synthesize(text="test", engine="fallback")
    assert result["success"] is True
    assert result["engine"] == "fallback"


def test_fastapi_app():
    from main import app
    assert app is not None
    assert app.title == "Voice AI Studio Arabic"
