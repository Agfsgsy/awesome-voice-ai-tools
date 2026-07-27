"""اختبارات محرك Whisper STT"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.mark.asyncio
async def test_whisper_stt_transcription():
    from backend.plugins.whisper_plugin import WhisperPlugin
    from backend.plugins.piper_plugin import PiperPlugin

    whisper_plugin = WhisperPlugin()
    piper_plugin = PiperPlugin()

    if not whisper_plugin.check():
        pytest.skip("Whisper not installed")

    if not piper_plugin.check():
        pytest.skip("Piper not installed (needed to generate test audio)")

    # تأكد من تحميل نموذج
    models = whisper_plugin.list_models()
    if not any(m["downloaded"] for m in models):
        res = whisper_plugin.download_models("tiny")
        assert res["success"] is True

    # توليد ملف صوتي أولاً
    text = "مرحبا"
    gen_result = await piper_plugin.generate(text, language="ar")
    assert gen_result["success"] is True

    audio_path = gen_result["file"]

    # اختبار التحويل (STT) - اختبار حقيقي
    transcribe_result = await whisper_plugin.transcribe(audio_path, language="ar")

    assert transcribe_result["success"] is True, f"Transcription failed: {transcribe_result.get('message')}"

    # التحقق من أن النص ليس فارغاً (يجب أن يلتقط كلمة قريبة من 'مرحبا')
    transcribed_text = transcribe_result["text"]
    assert len(transcribed_text) > 0, "Transcribed text is empty"
