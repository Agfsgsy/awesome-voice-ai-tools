# Fish Speech Setup Guide

## التثبيت
```bash
git clone https://github.com/fishaudio/fish-speech
cd fish-speech
pip install -e .
```

## تحميل النماذج
```bash
huggingface-cli download fishaudio/fish-speech-1.5 --local-dir checkpoints/fish-speech-1.5
```

## التشغيل
```bash
python -m tools.api_server --listen 0.0.0.0:8080 \
    --llama-checkpoint-path checkpoints/fish-speech-1.5
```

## المميزات
- جودة عالية جداً
- دعم 80+ لغة
- رخصة Apache 2.0 (تجاري ✅)

## المستودع الأصلي
https://github.com/fishaudio/fish-speech
