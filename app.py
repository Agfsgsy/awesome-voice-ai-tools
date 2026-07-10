#!/usr/bin/env python3
"""
Voice AI Unified Launcher
واجهة موحدة لتشغيل أدوات توليد الصوت واستنساخه
"""

import gradio as gr
import os
import sys
import importlib

ENGINES = [
    "F5-TTS",
    "XTTS-v2 (Coqui)",
    "OpenVoice",
    "Fish Speech",
    "RVC",
    "Bark",
    "Kokoro",
    "MeloTTS",
]

def generate_voice(engine: str, text: str, reference_audio):
    """
    تحويل النص إلى صوت باستخدام المحرك المختار.
    يتطلب تثبيت المحرك المناسب أولاً.
    """
    if not text.strip():
        return None, "⚠️ الرجاء إدخال نص."

    if engine == "F5-TTS":
        try:
            from f5_tts.api import F5TTS
            tts = F5TTS()
            wav, sr, _ = tts.infer(
                ref_file=reference_audio,
                ref_text="",
                gen_text=text,
            )
            output_path = "output_f5.wav"
            import soundfile as sf
            sf.write(output_path, wav, sr)
            return output_path, "✅ تم التوليد بنجاح باستخدام F5-TTS"
        except ImportError:
            return None, "❌ F5-TTS غير مثبت. شغّل: pip install f5-tts"

    elif engine == "XTTS-v2 (Coqui)":
        try:
            from TTS.api import TTS
            tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
            output_path = "output_xtts.wav"
            tts.tts_to_file(
                text=text,
                speaker_wav=reference_audio,
                language="ar",
                file_path=output_path,
            )
            return output_path, "✅ تم التوليد بنجاح باستخدام XTTS-v2"
        except ImportError:
            return None, "❌ Coqui TTS غير مثبت. شغّل: pip install TTS"

    elif engine == "OpenVoice":
        return None, "⚙️ OpenVoice: راجع docs/openvoice-setup.md للإعداد اليدوي."

    elif engine == "Fish Speech":
        return None, "⚙️ Fish Speech: راجع docs/fish-speech-setup.md للإعداد."

    elif engine == "RVC":
        return None, "⚙️ RVC: راجع docs/rvc-setup.md — يحتاج واجهة WebUI منفصلة."

    elif engine == "Bark":
        try:
            from bark import SAMPLE_RATE, generate_audio, preload_models
            import soundfile as sf
            preload_models()
            audio_array = generate_audio(text)
            output_path = "output_bark.wav"
            sf.write(output_path, audio_array, SAMPLE_RATE)
            return output_path, "✅ تم التوليد بنجاح باستخدام Bark"
        except ImportError:
            return None, "❌ Bark غير مثبت. شغّل: pip install git+https://github.com/suno-ai/bark"

    elif engine == "Kokoro":
        try:
            from kokoro import KPipeline
            import soundfile as sf
            pipeline = KPipeline(lang_code="a")
            generator = pipeline(text, voice="af_heart")
            output_path = "output_kokoro.wav"
            for i, (gs, ps, audio) in enumerate(generator):
                sf.write(output_path, audio, 24000)
                break
            return output_path, "✅ تم التوليد بنجاح باستخدام Kokoro"
        except ImportError:
            return None, "❌ Kokoro غير مثبت. شغّل: pip install kokoro"

    elif engine == "MeloTTS":
        try:
            from melo.api import TTS
            tts = TTS(language="EN")
            output_path = "output_melo.wav"
            speaker_ids = tts.hps.data.spk2id
            tts.tts_to_file(text, speaker_ids["EN-Default"], output_path)
            return output_path, "✅ تم التوليد بنجاح باستخدام MeloTTS"
        except ImportError:
            return None, "❌ MeloTTS غير مثبت. شغّل: pip install git+https://github.com/myshell-ai/MeloTTS"

    return None, "⚠️ المحرك غير معروف."


with gr.Blocks(title="🎙️ Voice AI Unified Launcher", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🎙️ Voice AI Unified Launcher\nواجهة موحدة لتشغيل أدوات توليد الصوت واستنساخه")

    with gr.Row():
        engine_select = gr.Dropdown(
            choices=ENGINES,
            value="F5-TTS",
            label="🔧 اختر المحرك",
        )

    with gr.Row():
        with gr.Column():
            text_input = gr.Textbox(
                label="📝 النص المراد تحويله",
                placeholder="اكتب النص هنا...",
                lines=4,
            )
            reference_audio = gr.Audio(
                label="🎤 عينة الصوت المرجعية (للاستنساخ)",
                type="filepath",
            )
            generate_btn = gr.Button("🚀 توليد الصوت", variant="primary")

        with gr.Column():
            output_audio = gr.Audio(label="🔊 الصوت الناتج")
            status_text = gr.Textbox(label="📊 الحالة", interactive=False)

    generate_btn.click(
        fn=generate_voice,
        inputs=[engine_select, text_input, reference_audio],
        outputs=[output_audio, status_text],
    )

    gr.Markdown("""
    ## 📖 ملاحظات
    - تأكد من تثبيت المحرك المطلوب أولاً (راجع `requirements/`)
    - لأفضل جودة استنساخ: استخدم عينة صوت 20-60 ثانية نظيفة
    - للمحتوى العربي: جرّب XTTS-v2 أو F5-TTS أولاً
    """)

if __name__ == "__main__":
    demo.launch(share=True, server_port=7860)
