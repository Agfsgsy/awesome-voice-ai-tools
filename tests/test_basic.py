"""Comprehensive Test Suite - Voice AI Studio v3"""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestConfig:
    def test_config_import(self):
        from backend.core.config import APP_NAME, APP_VERSION, APP_PORT
        assert APP_NAME == "Voice AI Studio Arabic"
        assert APP_VERSION == "3.0.0"
        assert APP_PORT == 8000

    def test_settings_singleton(self):
        from backend.core.config import settings
        assert settings.APP_NAME == "Voice AI Studio Arabic"


class TestSecurity:
    def test_sanitize_filename(self):
        from backend.core.security import sanitize_filename
        assert sanitize_filename("test.wav") == "test.wav"
        assert sanitize_filename("../../../etc/passwd") == "_.._.._.._etc_passwd"

    def test_validate_audio_file(self):
        from backend.core.security import validate_audio_file
        assert validate_audio_file("test.wav") == True
        assert validate_audio_file("test.exe") == False


class TestAudioUtils:
    def test_generate_sine_wave(self):
        from backend.core.audio_utils import generate_sine_wave
        data = generate_sine_wave(frequency=440, duration=0.1)
        assert len(data) > 0
        assert isinstance(data, bytes)

    def test_generate_silence(self):
        from backend.core.audio_utils import generate_silence
        data = generate_silence(duration=0.1)
        assert len(data) > 0


class TestHealth:
    def test_health_checks(self):
        from backend.core.health import health_checker
        result = health_checker.run_checks()
        assert "status" in result
        assert "checks" in result
        assert result["summary"]["total"] > 0


class TestLanguageManager:
    def test_detect_arabic(self):
        from backend.core.language_manager import language_manager
        result = language_manager.detect_language("مرحبا بالعالم")
        assert result["code"] == "ar"

    def test_detect_english(self):
        from backend.core.language_manager import language_manager
        result = language_manager.detect_language("Hello world")
        assert result["code"] == "en"

    def test_list_languages(self):
        from backend.core.language_manager import language_manager
        langs = language_manager.list_languages()
        assert len(langs) > 0


class TestCacheManager:
    @pytest.mark.asyncio
    async def test_cache_set_get(self):
        from backend.core.cache_manager import cache_manager
        await cache_manager.set("test_key", "test_value", ttl_seconds=60)
        result = await cache_manager.get("test_key")
        assert result == "test_value"


class TestTTSEngine:
    def test_engine_creation(self):
        from backend.core.tts_engine import TTSEngine
        engine = TTSEngine()
        assert engine is not None

    @pytest.mark.asyncio
    async def test_fallback_synthesis(self):
        from backend.core.tts_engine import tts
        result = await tts.synthesize(text="test", engine="fallback")
        assert result["success"] == True


class TestFastAPI:
    def test_app_creation(self):
        from main import app
        assert app is not None
        assert app.title == "Voice AI Studio Arabic"
