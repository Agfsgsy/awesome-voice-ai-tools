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

## التشغيل والتثبيت
### المتطلبات الأساسية
- Python 3.9 أو أحدث.
- `ffmpeg` (مطلوب لمعالجة الصوت).

### خطوات التثبيت (Linux / macOS)
```bash
# تثبيت ffmpeg (Ubuntu/Debian كمثال)
sudo apt update && sudo apt install ffmpeg -y

# تثبيت متطلبات المشروع
pip install -r requirements.txt
pip install -r requirements-ai.txt # (اختياري - لمحركات الذكاء الاصطناعي المتقدمة)

# تشغيل الخادم
python main.py
```

### خطوات التثبيت (Windows)
يمكنك استخدام سكربت التثبيت التلقائي الموجود:
```bat
install_ai.bat
```
ثم قم بتشغيل:
```bat
python main.py
```

افتح المتصفح: http://localhost:8000

## Run on Google Colab
يمكنك تشغيل المشروع بسهولة على Google Colab باستخدام النص البرمجي المخصص:
1. قم بإنشاء حساب في ngrok للحصول على Authtoken الخاص بك.
2. عيّن المتغير البيئي `NGROK_AUTHTOKEN` برمزك الخاص.
3. قم بتشغيل الأمر التالي:
```bash
export NGROK_AUTHTOKEN="your_ngrok_authtoken_here"
python colab_launcher.py
```
سيقوم النص بتثبيت الاعتماديات وتجهيز الخادم وإعطائك رابط ngrok العام لفتح الواجهة وواجهات API.

## API
- `/docs` - وثائق API التفاعلية
- `/api/tts` - توليد صوت
- `/api/audio/clone` - استنساخ صوت
- `/api/downloads` - قائمة الملفات
