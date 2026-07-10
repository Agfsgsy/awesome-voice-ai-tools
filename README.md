---
title: Voice AI Studio Arabic
emoji: 🎙️
colorFrom: teal
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Voice AI Studio Arabic

منصة صوتيات عربية لتوليد واستنساخ الصوت مفتوحة المصدر

## المميزات
- توليد صوت عربي/إنجليزي من النص (TTS)
- استنساخ صوت بإذن صاحب الصوت
- مؤثرات صوتية
- محتوى إسلامي
- واجهة عربية RTL 100%

## التشغيل
```bash
pip install -r requirements.txt
python main.py
```

افتح المتصفح: http://localhost:8000

## API
- `/docs` - وثائق API التفاعلية
- `/api/tts` - توليد صوت
- `/api/audio/clone` - استنساخ صوت
- `/api/downloads` - قائمة الملفات
