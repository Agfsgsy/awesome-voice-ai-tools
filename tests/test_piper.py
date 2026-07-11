"""اختبارات محرك Piper TTS"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.mark.asyncio
async def test_piper_tts_generation():
    from backend.plugins.piper_plugin import PiperPlugin
    from backend.core.audio_eval import evaluate_audio_quality

    plugin = PiperPlugin()

    # تأكد من التثبيت
    if not plugin.check():
        pytest.skip("Piper not installed")

    # تحقق من وجود نموذج أو قم بتحميل واحد خفيف
    models = plugin.list_models()
    downloaded = [m for m in models if m["downloaded"]]

    if not downloaded:
         res = plugin.download_models("ar_JO-kareem-low")
         assert res["success"] is True

    # توليد الصوت (اختبار حقيقي)
    text = "مرحبا بكم في اختبار الجودة."
    result = await plugin.generate(text, language="ar")

    assert result["success"] is True, f"Generation failed: {result.get('message')}"

    file_path = result["file"]
    assert os.path.exists(file_path), "Audio file was not created"

    # التقييم التلقائي
    eval_res = evaluate_audio_quality(file_path)
    assert eval_res["valid"] is True, "Generated audio is invalid"
    assert eval_res["silent"] is False, "Generated audio is silent"
    assert eval_res["duration_seconds"] > 0, "Audio duration is 0"
