# XTTS-v2 (Coqui) Setup Guide

## التثبيت
```bash
pip install torch torchaudio
pip install TTS
```

## الاستخدام البرمجي
```python
from TTS.api import TTS
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
tts.tts_to_file(
    text="مرحبا بالعالم",
    speaker_wav="sample.wav",
    language="ar",
    file_path="output.wav"
)
```

## ملاحظات
- يدعم اللغة العربية ✅
- الاستنساخ من 6 ثوانٍ فقط
- رخصة CPML (غير تجاري ⚠️)

## المستودع الأصلي
https://github.com/coqui-ai/TTS
