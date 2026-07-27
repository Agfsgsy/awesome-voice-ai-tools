"""Strict voice, bilingual writer, and provider-settings regression tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.core import provider_settings
from backend.core.tts_registry import tts_registry
from backend.core.voice_catalog import voice_by_id, voices_for
from main import app

client = TestClient(app)


def test_provider_catalog_is_honest_and_never_returns_raw_secrets() -> None:
    response = client.get("/api/ultimate/providers")
    assert response.status_code == 200
    payload = response.json()
    categories = {item["category"] for item in payload["providers"]}
    assert {"free", "open_source", "trial", "paid"}.issubset(categories)
    serialized = response.text.lower()
    assert '"api_key":' not in serialized
    assert "edge" in {item["id"] for item in payload["providers"]}
    assert "openai" in {item["id"] for item in payload["providers"]}


def test_gemini_voice_gender_assignments_match_official_metadata() -> None:
    for voice in ("Kore", "Gacrux", "Sulafat", "Achernar"):
        assert voice_by_id("gemini", voice)["gender"] == "female"
    for voice in ("Charon", "Algieba", "Iapetus", "Puck"):
        assert voice_by_id("gemini", voice)["gender"] == "male"


def test_strict_voice_filters_never_cross_language_or_gender() -> None:
    arabic_women = voices_for("edge", language="ar", gender="female")
    english_men = voices_for("edge", language="en", gender="male")
    assert arabic_women and english_men
    assert all(item["language"] == "ar" and item["gender"] == "female" for item in arabic_women)
    assert all(item["language"] == "en" and item["gender"] == "male" for item in english_men)
    assert not voices_for("piper", language="ar", gender="female")
    assert not voices_for("openai", language="ar", gender="male")
    assert voices_for("openai", language="ar", gender="neutral")


def test_synthesis_rejects_voice_gender_mismatch_before_generation() -> None:
    response = client.post(
        "/api/ultimate/synthesize",
        json={
            "text": "هذا اختبار واضح للصوت.",
            "provider": "edge",
            "language": "ar",
            "gender": "male",
            "voice_id": "ar-SA-ZariyahNeural",
        },
    )
    assert response.status_code == 422
    assert "جنس" in response.json()["detail"]


def test_synthesis_rejects_high_confidence_language_mismatch() -> None:
    response = client.post(
        "/api/ultimate/synthesize",
        json={
            "text": "This sentence is clearly written in English.",
            "provider": "edge",
            "language": "ar",
            "gender": "male",
            "voice_id": "ar-SA-HamedNeural",
        },
    )
    assert response.status_code == 422
    assert "لغة النص" in response.json()["detail"]


def test_piper_dialogue_rejects_female_role_without_silent_switch(monkeypatch) -> None:
    class ReadyPlugin:
        def check(self) -> bool:
            return True

    original = tts_registry.get_plugin
    monkeypatch.setattr(
        tts_registry,
        "get_plugin",
        lambda name: ReadyPlugin() if name == "piper" else original(name),
    )
    response = client.post(
        "/api/ultimate/dialogue",
        json={
            "script": "المذيع_رجل: أهلًا بكم.\nالضيفة_امرأة: شكرًا للاستضافة.",
            "provider": "piper",
            "language": "ar",
        },
    )
    assert response.status_code == 422
    assert "لن يستبدله" in response.json()["detail"]


def test_local_creative_writer_supports_arabic_and_english_interviews() -> None:
    for language, role in (("ar", "المذيع_رجل:"), ("en", "HOST_MALE:")):
        response = client.post(
            "/api/ultimate/creative",
            json={
                "mode": "interview",
                "subject": "التعليم" if language == "ar" else "education",
                "language": language,
                "writer_provider": "local",
                "speakers": 3,
            },
        )
        assert response.status_code == 200
        assert response.json()["writer_used"] == "local"
        assert role in response.json()["text"]


def test_provider_settings_are_atomic_and_masked(tmp_path, monkeypatch) -> None:
    settings_file = tmp_path / "providers.json"
    monkeypatch.setattr(provider_settings, "SETTINGS_FILE", settings_file)
    provider_settings.save_provider_config(
        "unit_provider",
        {"api_key": "secret-test-provider-key-123", "region": "eastus"},
    )
    assert settings_file.exists()
    masked = provider_settings.masked_provider_config("unit_provider")
    assert masked["api_key_set"] is True
    assert masked["region"] == "eastus"
    assert "api_key" not in masked
    assert "secret-test-provider-key-123" not in str(masked)
