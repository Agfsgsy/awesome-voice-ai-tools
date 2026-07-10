# 🇦🇷 نماذج TTS العربية مفتوحة المصدر

| النموذج | الرابط | الجودة | اللهجة |
|---|---|---|---|
| ArTST | https://github.com/mbzuai-nlp/ArTST | عالية | فصحى |
| XTTS-v2 | https://github.com/coqui-ai/TTS | عالية | فصحى + لهجات |
| Fish Speech | https://github.com/fishaudio/fish-speech | عالية جداً | متعددة |
| CosyVoice2 | https://github.com/FunAudioLLM/CosyVoice | عالية | فصحى |
| F5-TTS | https://github.com/SWivid/F5-TTS | عالية | متعددة |

## ملاحظات للعربية
- فصحى القرآنية تحتاج عينات صوتية خاصة بها
- أفضل نتيجة: استخدم XTTS-v2 مع عينة للشيخ نفسه
- لتحسين التشكيل: أضف التشكيل للنص العربي قبل التوليد
- تطبيق التشكيل:
```python
import arabic_reshaper
from bidi.algorithm import get_display

text = "بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ"
reshaped = arabic_reshaper.reshape(text)
# تمرير لنموذج TTS
```

## مجموعة بيانات عربية موصى بها

- **Quran MD (Hugging Face)**: 187,080 ملف صوتي من 30 قارئ
  https://huggingface.co/datasets/Buraaq/quran-audio-text-dataset
- **Mozilla Common Voice Arabic**: مجانية
  https://commonvoice.mozilla.org/ar
- **Arabic Speech Corpus**: للتدريب
  https://en.arabicspeechcorpus.com
