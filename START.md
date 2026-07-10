# 🚀 تشغيل Voice AI Studio

## الخطوة 1: تثبيت متطلبات الخادم
```bash
pip install fastapi uvicorn[standard] python-multipart
pip install pedalboard librosa noisereduce soundfile numpy
```

## الخطوة 2: تثبيت محرك الصوت المطلوب
```bash
# الأفضل للاستنساخ
pip install TTS

# الأعلى جودة
pip install torch torchaudio
pip install f5-tts

# خفيف وسريع
pip install kokoro
```

## الخطوة 3: تشغيل الخادم
```bash
python server.py
```

## الخطوة 4: فتح الموقع
افتح المتصفح على:
```
http://localhost:8000
```

---

## تشغيل بـ Docker
```bash
docker-compose up --build
```
ثم افتح: http://localhost:8000

---

## الميزات
- 🔊 توليد الصوت من النص (6 محركات)
- 🎤 استنساخ الصوت من عينة
- 🎛️ مؤثرات صوتية (ريفرب، إيكو، ضغط، طبقة)
- 🕌 محتوى ديني (قرآن، مشايخ، أذان)
- 🧹 إزالة الضجيج التلقائية
- 📱 واجهة عربية متجاوبة
