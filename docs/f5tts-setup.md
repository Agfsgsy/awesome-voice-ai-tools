# F5-TTS Setup Guide

## التثبيت
```bash
pip install torch torchaudio
pip install f5-tts
```

## الاستخدام مع الواجهة
1. شغّل `python app.py`
2. اختر "F5-TTS" من القائمة
3. أضف عينة صوتية مرجعية (20-60 ثانية)
4. اكتب النص واضغط توليد

## ملاحظات
- يعمل بدون GPU لكن GPU يسرّع التوليد
- أفضل لغات: الإنجليزية والعربية
- رخصة: MIT (تجاري ✅)

## المستودع الأصلي
https://github.com/SWivid/F5-TTS
