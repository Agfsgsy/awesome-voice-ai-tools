import pytest
import httpx
from httpx import AsyncClient
from main import app
from backend.core.tts_registry import tts_registry

@pytest.mark.asyncio
async def test_api_settings_default_engine():
    async with AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert "default_engine" in data
        assert "engine_available" in data

        available = tts_registry.get_available_engines()
        if len(available) == 0:
            assert data["engine_available"] is False
            assert data["default_engine"] == "fallback"
        else:
            assert data["engine_available"] is True
            assert data["default_engine"] != "fallback"

            # Since auto_select_engine returns None if no models are downloaded,
            # it should default to the first available engine
            auto = tts_registry.auto_select_engine()
            if auto:
                assert data["default_engine"] == auto
            else:
                assert data["default_engine"] == available[0]["name"]

@pytest.mark.asyncio
async def test_api_tts_auto_select_engine():
    async with AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/tts", json={
            "text": "اختبار المحرك",
            "engine": "auto",
            "language": "ar"
        })
        assert response.status_code == 200
        data = response.json()

        available = tts_registry.get_available_engines()
        if len(available) == 0:
            assert data["success"] is False
            assert "No TTS engine available" in data["message"]
        else:
            assert "success" in data

@pytest.mark.asyncio
async def test_kokoro_fallback():
    kokoro_plugin = tts_registry.get_plugin("kokoro")
    if kokoro_plugin and not kokoro_plugin.check():
        result = await kokoro_plugin.generate(text="Test", language="en")
        assert "success" in result
        assert result["success"] is True
        assert "fallback" in result["message"].lower()

@pytest.mark.asyncio
async def test_api_status():
    async with AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert "engine_available" in data
        available = tts_registry.get_available_engines()
        assert data["engine_available"] == (len(available) > 0)
