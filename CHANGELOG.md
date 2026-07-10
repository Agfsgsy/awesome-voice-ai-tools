# سجل التغييرات - Voice AI Studio Arabic

## [2.0.0] - 2026-07-10

### المضاف
- بنية احترافية كاملة (backend/ frontend/ plugins/)
- نظام إضافات Plugin System مع اكتشاف تلقائي
- API كاملة مع 18+ endpoint
- واجهة ويب عربية RTL مع 7 صفحات
- دعم Termux (Android)
- 4 ملفات متطلبات منفصلة (core, termux, linux, dev)
- 11 سكربت تشغيل وصيانة
- أداة فحص ذاتي (Doctor)
- Docker و docker-compose
- دعم Hugging Face Spaces
- محرك TTS موحد مع 8 محركات
- محرك احتياطي يعمل دائماً
- دعم Google Gemini TTS API
- نظام تسجيل أحداث متكامل
- معالجة استثناءات شاملة
- Async/Await للأداء

### المحسّن
- إعادة هيكلة كاملة للكود
- إصلاح جميع المسارات (Paths)
- إزالة الكود المكرر
- تنظيم Imports
- دعم Dark Mode في الواجهة

### القيود
- محركات TTS الثقيلة (XTTS, F5, Bark) تحتاج تثبيتاً يدوياً
- بعض المكتبات لا تعمل على Termux (torch, torchaudio)
- المحرك الاحتياطي يولد نغمة بسيطة فقط
