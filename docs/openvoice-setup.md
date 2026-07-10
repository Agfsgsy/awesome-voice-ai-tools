# OpenVoice Setup Guide

## التثبيت
```bash
git clone https://github.com/myshell-ai/OpenVoice
cd OpenVoice
pip install -r requirements.txt
```

## الاستخدام
```python
from openvoice import se_extractor
from openvoice.api import ToneColorConverter

ckpt_converter = 'checkpoints_v2/converter'
tone_color_converter = ToneColorConverter(f'{ckpt_converter}/config.json')
tone_color_converter.load_ckpt(f'{ckpt_converter}/checkpoint.pth')
```

## المميزات
- تحويل لون الصوت
- دعم لهجات متعددة
- رخصة: MIT (تجاري ✅)

## المستودع الأصلي
https://github.com/myshell-ai/OpenVoice
