---
title: Ibn Al-Waqadi Voice Studio
emoji: 🎙️
colorFrom: teal
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# استوديو ابن الواقدي 5.1 — Free First

استوديو عربي موحّد لإنتاج الصوت والمقابلات. يبدأ بمحركات مجانية لا تتطلب مفتاح API مدفوعًا، ويحافظ على Gemini وElevenLabs كخيارات سحابية صريحة فقط.

## ما الذي يقدمه الإصدار 5.1؟

- صوت عربي عصبي عبر **Microsoft Edge TTS** من دون مفتاح API.
- صوت عربي محلي عبر **Piper**؛ يُنزّل النموذج العربي تلقائيًا عند أول استخدام ثم يعمل دون اتصال.
- إنتاج صوت منفرد، حوار متعدد المتحدثين، ومقابلات قابلة للاستكمال.
- واجهة عربية RTL موحّدة بدل الصفحات ذات الإصدارات المتعارضة.
- عقد JSON ثابتة لمسارات الصوت، مع فحص إقلاع يمنع عودة خطأ `query.req`.
- لا ينتج البرنامج نغمة وهمية على أنها كلام عند فشل المحركات.
- Gemini وElevenLabs اختياريان ولا يُستخدمان تلقائيًا في الوضع المجاني.

## التثبيت الموصى به على Windows

المتطلبات:

- Windows 10 أو 11 بنظام 64 بت.
- Python من 3.9 إلى 3.13 عند التشغيل من المصدر.
- اتصال بالإنترنت لاستخدام Edge TTS أو لتنزيل نموذج Piper أول مرة.

من PowerShell داخل مجلد المشروع:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-desktop.txt
python main.py
```

ثم افتح `http://127.0.0.1:8000`. سينقلك المسار الرئيسي إلى الاستوديو الموحّد تلقائيًا.

يمكن كذلك تشغيل `INSTALL_WINDOWS_LITE.bat` لتجهيز البيئة الأساسية، أو `BUILD_WINDOWS_INSTALLER.bat` لبناء التطبيق المحمول وملف التثبيت.

## Linux وmacOS

ثبّت FFmpeg من مدير حزم النظام، ثم:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

## اختيار محرك الصوت

| الخيار | مفتاح API | الاتصال | الاستخدام |
|---|---:|---:|---|
| `auto` | لا | بحسب المحرك | Edge أولًا، ثم Piper المحلي عند تعذر الاتصال |
| `edge` | لا | مطلوب | الافتراضي الأسرع وصوت عربي عصبي |
| `piper` | لا | أول مرة فقط | محلي بعد تنزيل النموذج |
| `gemini` | نعم | مطلوب | اختياري ولا يُختار تلقائيًا |
| `elevenlabs` | نعم | مطلوب | اختياري ولا يُختار تلقائيًا |

## واجهة API

الوثائق التفاعلية متاحة في `http://127.0.0.1:8000/docs`.

مثال طلب صحيح:

```bash
curl -X POST http://127.0.0.1:8000/api/tts \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"مرحبًا بكم في استوديو ابن الواقدي\",\"engine\":\"auto\",\"language\":\"ar\"}"
```

الاستجابة توضح `engine_requested` و`engine_used` وما إذا استُخدم Piper كبديل مجاني.

## التحقق قبل النشر

```powershell
python -m pytest -q
python -m compileall -q main.py desktop_app.py backend scripts
python scripts\validate_unified_release.py
```

يتحقق مدقق الإصدار من تطابق رقم النسخة، وسياسة Free First، وأجسام JSON، وعدم تكرار المسارات، وروابط التنقل بين صفحات الاستوديو.

## الملفات والخصوصية

- في النسخة المجمعة تُحفظ النماذج والمخرجات والسجلات داخل `%LOCALAPPDATA%\VoiceAIStudioArabic`.
- لا ترسل مفاتيح Gemini أو ElevenLabs إلى المستودع.
- لا تستخدم الاستنساخ الصوتي إلا بموافقة صاحب الصوت، ووضّح للمستمعين عندما يكون المحتوى مولدًا.

## حل المشكلات

- إذا تعذر Edge، اختر Piper أو اترك `auto` ليحاول Piper تلقائيًا.
- عند أول تشغيل لـPiper انتظر اكتمال تنزيل النموذج العربي؛ بعد ذلك لا يحتاج المحرك إلى اتصال.
- إذا فشل دمج المقابلات، ثبّت FFmpeg وتأكد من ظهوره في مسار النظام.
- إذا منع Windows الكتابة على سطح المكتب، تبقى النتيجة محفوظة داخل التطبيق ويمكن تنزيلها من المشغّل؛ أغلق الملف المفتوح أو اسمح بالكتابة ثم أعد التصدير.
- نفّذ `python scripts\validate_unified_release.py` إذا ظهرت رسالة تحقق عند بدء التطبيق.
