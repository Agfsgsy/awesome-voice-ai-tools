import asyncio
from pathlib import Path

from backend.core.tts_engine import TTSEngine


def test_rejects_empty_text():
    engine = TTSEngine()
    result = asyncio.run(engine.synthesize("   ", engine="auto"))
    assert result["success"] is False
    assert result["file"] is None


def test_rejects_invalid_speed():
    engine = TTSEngine()
    result = asyncio.run(engine.synthesize("مرحبا", engine="auto", speed=3.0))
    assert result["success"] is False
    assert "Speed" in result["message"]


def test_rejects_oversized_text():
    engine = TTSEngine()
    result = asyncio.run(engine.synthesize("ا" * (engine.MAX_TEXT_LENGTH + 1), engine="auto"))
    assert result["success"] is False
    assert "too long" in result["message"]


def test_no_fake_fallback_success_when_no_engine(monkeypatch):
    engine = TTSEngine()
    monkeypatch.setattr(engine, "_best_builtin_engine", lambda: None)

    from backend.core.tts_registry import tts_registry
    monkeypatch.setattr(tts_registry, "auto_select_engine", lambda: None)

    result = asyncio.run(engine.synthesize("اختبار", engine="auto"))
    assert result["success"] is False
    assert result["url"] is None


def test_filename_changes_with_voice_and_speed():
    first = TTSEngine._filename("tts", "hello", "voice-a", 1.0)
    second = TTSEngine._filename("tts", "hello", "voice-b", 1.0)
    third = TTSEngine._filename("tts", "hello", "voice-a", 1.2)
    assert first != second
    assert first != third
    assert Path(first).suffix == ".wav"
