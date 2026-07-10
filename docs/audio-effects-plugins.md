# 🎵 المؤثرات والإضافات الصوتية مفتوحة المصدر

## 🎧 مجموعات الإضافات (Bundles)

### LADSPA / LV2 / VST Open Source
- **OpenAudio Plugins List**: https://github.com/webprofusion/OpenAudio
  قائمة شاملة بأفضل إضافات وتطبيقات صوتية مفتوحة

- **MFreeFXBundle (Melda Production)**: https://www.meldaproduction.com/MFreeFXBundle
  حزمة مجانية 40+ إضافة بما فيها EQ متقدم

- **Airwindows**: https://github.com/airwindows/airwindows
  مجموعة ضخمة مجانية من إضافات فريدة (إدخال تمثيلي)

## 🌁 مؤثرات الريفرب (Reverb) للمحتوى الديني

| الإضافة | الرابط | مناسب لـ |
|---|---|---|
| ValhallaDSP Supermassive | مجاني - valhallaDSP.com | صوت مسجدي وديني |
| Reverb Trickery | https://github.com/unicornsasfuel/reverb_trickery | ريفرب إبداعي |
| Ambience (FDN Reverb) | https://github.com/webprofusion/OpenAudio | جودة عالية |
| OrilRiver | مجاني - kvraudio.com | صوت كنسي طبيعي |

## 🎤 معالجة الصوت ب**Python** (مباشر)

### إزالة ضجيج + تحسين
```python
import librosa
import soundfile as sf
import numpy as np

# تحميل الصوت
y, sr = librosa.load("input.wav", sr=None)

# تكبير الصوت (الحدة في dB)
y_normalized = librosa.util.normalize(y)

# حفظ النتيجة
sf.write("output_clean.wav", y_normalized, sr)
print("✅ تم تنظيف الصوت")
```

### إضافة إيكو (Echo)
```python
import numpy as np
import soundfile as sf

def add_echo(audio, sr, delay=0.3, decay=0.4):
    delay_samples = int(sr * delay)
    echo = np.zeros(len(audio) + delay_samples)
    echo[:len(audio)] += audio
    echo[delay_samples:] += audio * decay
    return echo[:len(audio)]

y, sr = sf.read("input.wav")
y_echo = add_echo(y, sr, delay=0.3, decay=0.5)
sf.write("output_echo.wav", y_echo, sr)
```

### إضافة ريفرب خفيف (صوت مسجد)
```python
from scipy import signal
import numpy as np
import soundfile as sf

def add_reverb(audio, sr, room_scale=0.5):
    # Room Impulse Response بسيط
    ir_length = int(sr * room_scale)
    ir = np.random.randn(ir_length) * np.exp(-6 * np.arange(ir_length) / ir_length)
    reverbed = signal.fftconvolve(audio, ir, mode="full")[:len(audio)]
    return 0.6 * audio + 0.4 * reverbed / np.max(np.abs(reverbed))

y, sr = sf.read("input.wav")
y_reverb = add_reverb(y, sr, room_scale=0.3)
sf.write("output_reverb.wav", y_reverb, sr)
```

### تغيير طبقة الصوت (Pitch Shift) للمشيخ
```python
import librosa
import soundfile as sf

y, sr = librosa.load("sheikh_voice.wav", sr=None)
# تخفيض طبقة الصوت لصوت أعمق (-2 مقام)
y_shifted = librosa.effects.pitch_shift(y, sr=sr, n_steps=-2)
sf.write("sheikh_voice_deep.wav", y_shifted, sr)
```

## 🛠️ أدوات معالجة صوتية ب**Python** مفتوحة المصدر

| المكتبة | الاستخدام | pip install |
|---|---|---|
| pedalboard | إضافات VST ب**Python** | `pip install pedalboard` |
| librosa | تحليل ومعالجة صوتية | `pip install librosa` |
| pydub | تحرير صوت سهل | `pip install pydub` |
| noisereduce | إزالة ضجيج | `pip install noisereduce` |
| pyworld | تغيير طبقة وجودة الصوت | `pip install pyworld` |
| scipy | فلترة وتحويل رياضي | `pip install scipy` |

## 🎚️ مؤثرات Pedalboard (إضافات VST بالبايثون)

```python
from pedalboard import Pedalboard, Reverb, Compressor, LowCutFilter, HighpassFilter, Gain
from pedalboard.io import AudioFile

# إعداد المؤثرات لصوت مشيخ / خطاب ديني
board = Pedalboard([
    HighpassFilter(cutoff_frequency_hz=100),  # إزالة ترددات داخلية
    Compressor(threshold_db=-20, ratio=3),     # تقليص التشويه
    Reverb(room_size=0.15, damping=0.7, wet_level=0.1),  # ريفرب خفيف
    Gain(gain_db=3)                           # رفع مستوى الصوت
])

with AudioFile("input_voice.wav") as f:
    audio = f.read(f.frames)
    samplerate = f.samplerate

processed = board(audio, samplerate)

with AudioFile("output_voice_enhanced.wav", "w", samplerate, audio.shape[0]) as f:
    f.write(processed)

print("✅ تمت المعالجة بنجاح!")
```

## 🎧 إعدادات مؤثرات جاهزة

### صوت بث مسجد
```python
board_masjid = Pedalboard([
    LowCutFilter(cutoff_frequency_hz=80),
    Reverb(room_size=0.5, damping=0.3, wet_level=0.3, dry_level=0.7),
    Compressor(threshold_db=-15, ratio=2),
])
```

### صوت خطاب عام
```python
board_lecture = Pedalboard([
    HighpassFilter(cutoff_frequency_hz=120),
    Compressor(threshold_db=-18, ratio=4),
    Reverb(room_size=0.1, wet_level=0.05),
    Gain(gain_db=2),
])
```

### صوت استوديو (نظيف جداً)
```python
board_studio = Pedalboard([
    HighpassFilter(cutoff_frequency_hz=100),
    Compressor(threshold_db=-12, ratio=2.5),
    Gain(gain_db=1),
])
```
