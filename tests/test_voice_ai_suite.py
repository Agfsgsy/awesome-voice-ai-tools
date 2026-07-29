import pytest

from backend.voice_ai.models import CloneOptions
from backend.voice_ai.numbers import normalize_number_token, normalize_numbers_in_text
from backend.voice_ai.service import VoiceAISuite


def test_engine_aliases():
    assert CloneOptions(text="مرحبا", engine="coqui", consent_confirmed=True).engine == "xtts"
    assert CloneOptions(text="مرحبا", engine="xtts-v2", consent_confirmed=True).engine == "xtts"
    assert CloneOptions(text="مرحبا", engine="gpt-sovits", consent_confirmed=True).engine == "gpt_sovits"


def test_consent_default_is_false():
    request = CloneOptions(text="اختبار")
    assert request.consent_confirmed is False


def test_number_normalization_percentage():
    assert "بالمائة" in normalize_numbers_in_text("النسبة 15%")


def test_number_normalization_phone_digits():
    output = normalize_number_token("777123456", mode="phone")
    assert "سبعة" in output and "واحد" in output


def test_weighted_score_redistributes_missing_metrics():
    score = VoiceAISuite._weighted_score(None, None, 0.8, 1.0)
    assert score == pytest.approx((0.8 * 0.15 + 1.0 * 0.10) / 0.25, abs=1e-4)


def test_character_similarity_arabic_variants():
    assert VoiceAISuite._character_similarity("أحمد", "احمد") == 1.0
    assert VoiceAISuite._character_similarity("مرحبا", "مختلف") < 0.5
