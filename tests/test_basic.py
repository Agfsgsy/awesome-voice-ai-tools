"""اختبارات أساسية للمشروع ومحرك الصوت."""
import pytest


def test_config_import():
    from backend.core.config import APP_NAME, APP_VERSION, APP_PORT

    assert APP_NAME == "Voice AI Studio Arabic"
    assert APP_VERSION == "2.0.0"
    assert APP_PORT == 8000


def test_logger_import():
    from backend.core.logger import get_logger

    assert get_logger("test") is not None


def test_audio_utils_import():
    from backend.core.audio_utils import generate_sine_wave

    data = generate_sine_wave(frequency=440, duration=0.1)
    assert isinstance(data, bytes)
    assert data


def test_plugin_manager_import():
    from pathlib import Path
    from backend.core.plugin_manager import PluginManager

    assert PluginManager(Path(".")) is not None


def test_tts_engine_import():
    from backend.core.tts_engine import TTSEngine

    engine = TTSEngine()
    engines = engine.list_engines()
    assert engines
    assert any(item["name"] == "kokoro" for item in engines)
    assert all(item["name"] != "fallback" for item in engines)


@pytest.mark.asyncio
async def test_tts_rejects_invalid_engine():
    from backend.core.tts_engine import TTSEngine

    result = await TTSEngine().synthesize(text="اختبار", engine="invalid_engine_name")
    assert result["success"] is False
    assert result["file"] is None
    assert result["url"] is None


@pytest.mark.asyncio
async def test_tts_rejects_empty_text():
    from backend.core.tts_engine import TTSEngine

    result = await TTSEngine().synthesize(text="   ", engine="auto")
    assert result["success"] is False
    assert "required" in result["message"].lower()


@pytest.mark.asyncio
async def test_tts_rejects_unsafe_speed():
    from backend.core.tts_engine import TTSEngine

    result = await TTSEngine().synthesize(text="اختبار", engine="auto", speed=4.0)
    assert result["success"] is False
    assert "speed" in result["message"].lower()


def test_health_checks():
    from backend.core.health import run_all_checks

    checks = run_all_checks(8001)
    assert checks
    assert all("name" in check for check in checks)
    assert all("ok" in check for check in checks)


def test_fastapi_app():
    from main import app

    assert app is not None
    assert app.title == "Voice AI Studio Arabic"
