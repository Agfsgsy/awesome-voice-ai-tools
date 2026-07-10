# دليل Termux - Voice AI Studio Arabic

## تثبيت Termux

1. ثبّت [Termux](https://f-droid.org/packages/com.termux/) من F-Droid (لا تستخدم متجر Play).
2. افتح Termux ونفّذ:

```bash
pkg update && pkg upgrade
pkg install python git rust
```

## تثبيت المشروع

```bash
git clone https://github.com/Agfsgsy/awesome-voice-ai-tools.git
cd awesome-voice-ai-tools
chmod +x scripts/*.sh
./scripts/install.sh
```

## التشغيل

```bash
./scripts/run.sh
```

افتح في المتصفح: http://localhost:8000

## قيود Termux

| الميزة | الحالة | الملاحظة |
|--------|--------|----------|
| FastAPI | يعمل | كامل |
| Gradio | يعمل | كامل |
| واجهة الويب | تعمل | كاملة RTL |
| Kokoro TTS | يعمل (إذا تم تثبيته يدوياً) | قد يحتاج MATHLIB=m |
| Piper TTS | يعمل (إذا تم تثبيته) | خفيف ومناسب |
| XTTS-v2 | قد لا يعمل | يحتاج torch وذاكرة كبيرة |
| F5-TTS | لا يعمل | يحتاج GPU أو ذاكرة كبيرة |
| Bark | قد لا يعمل | ثقيل على Android |
| Gemini TTS | يعمل | يحتاج API key |
| المحرك الاحتياطي | يعمل دائماً | يولد نغمة تجريبية |

## استكشاف الأخطاء

```bash
# فحص شامل
./scripts/doctor.sh

# فحص الصحة
./scripts/healthcheck.sh

# إصلاح
./scripts/repair.sh
```

## ملاحظات

- استخدم `requirements-termux.txt` للتثبيت على Termux.
- بعض المكتبات (torch, torchaudio) قد تحتاج تثبيت يدوي أو قد لا تعمل.
- المحرك الاحتياطي يولد نغمة بسيطة عند عدم توفر أي محرك TTS.
