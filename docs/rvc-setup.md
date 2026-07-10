# RVC Setup Guide

## التثبيت
```bash
git clone https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI
cd Retrieval-based-Voice-Conversion-WebUI
pip install -r requirements.txt
```

## التشغيل
```bash
python infer-web.py
```
ثم افتح المتصفح على: http://localhost:7865

## الاستخدام عبر Python
```python
from infer.lib.infer_pack.models import SynthesizerTrnMs768NSFsid
# راجع README الرسمي للتفاصيل
```

## المميزات
- تحويل صوت احترافي
- مناسب للغناء والتمثيل
- واجهة WebUI كاملة

## المستودع الأصلي
https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI
