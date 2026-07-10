# دليل التثبيت - Voice AI Studio Arabic

## المتطلبات
- Python 3.9 أو أحدث (يُفضل 3.11 أو 3.12)
- pip
- Git
- 500MB مساحة فارغة على الأقل

## التثبيت السريع (Linux / macOS)

```bash
git clone https://github.com/Agfsgsy/awesome-voice-ai-tools.git
cd awesome-voice-ai-tools
chmod +x scripts/*.sh
./scripts/install.sh
```

## التثبيت السريع (Termux / Android)

```bash
pkg update && pkg install python git
git clone https://github.com/Agfsgsy/awesome-voice-ai-tools.git
cd awesome-voice-ai-tools
chmod +x scripts/*.sh
./scripts/install.sh
```

## التشغيل

```bash
./scripts/run.sh
```

ثم افتح المتصفح: http://localhost:8000

## التشغيل اليدوي

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Docker

```bash
docker compose up --build
```

## متغيرات البيئة

انسخ `.env.example` إلى `.env` واملأ القيم:

```bash
cp .env.example .env
```

| المتغير | الوصف | الافتراضي |
|---------|-------|-----------|
| APP_HOST | عنوان المضيف | 0.0.0.0 |
| APP_PORT | المنفذ | 8000 |
| APP_DEBUG | وضع التصحيح | false |
| GEMINI_API_KEY | مفتاح Gemini API (اختياري) | فارغ |
| GEMINI_TTS_MODEL | نموذج Gemini TTS | gemini-3.1-flash-tts-preview |
