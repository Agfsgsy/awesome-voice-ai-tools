#!/usr/bin/env python3
"""
سكريبت معالجة الصوت الديني / صوت المشيخ
يطبق مؤثرات مختلفة على الصوت بشكل تلقائي
"""

import argparse
import sys

try:
    from pedalboard import Pedalboard, Reverb, Compressor, HighpassFilter, LowCutFilter, Gain
    from pedalboard.io import AudioFile
except ImportError:
    print("❌ الرجاء تثبيت: pip install pedalboard")
    sys.exit(1)

try:
    import noisereduce as nr
    import soundfile as sf
    import numpy as np
except ImportError:
    print("❌ الرجاء تثبيت: pip install noisereduce soundfile numpy")
    sys.exit(1)

PRESETS = {
    "masjid": Pedalboard([
        LowCutFilter(cutoff_frequency_hz=80),
        Compressor(threshold_db=-20, ratio=2.5),
        Reverb(room_size=0.45, damping=0.4, wet_level=0.25, dry_level=0.75),
        Gain(gain_db=2),
    ]),
    "lecture": Pedalboard([
        HighpassFilter(cutoff_frequency_hz=120),
        Compressor(threshold_db=-18, ratio=4),
        Reverb(room_size=0.1, wet_level=0.05),
        Gain(gain_db=2),
    ]),
    "studio": Pedalboard([
        HighpassFilter(cutoff_frequency_hz=100),
        Compressor(threshold_db=-12, ratio=2),
        Gain(gain_db=1),
    ]),
    "deep": Pedalboard([
        LowCutFilter(cutoff_frequency_hz=60),
        Compressor(threshold_db=-22, ratio=3),
        Reverb(room_size=0.3, wet_level=0.15),
        Gain(gain_db=3),
    ]),
}


def process_voice(input_path: str, output_path: str, preset: str = "studio", denoise: bool = True):
    print(f"🎵 معالجة: {input_path}")
    print(f"🔧 الإعداد: {preset}")

    if denoise:
        print("🧹 إزالة الضجيج...")
        y, sr = sf.read(input_path)
        if len(y.shape) > 1:
            y = y.mean(axis=1)
        y_clean = nr.reduce_noise(y=y, sr=sr)
        clean_path = input_path.replace(".wav", "_denoised.wav")
        sf.write(clean_path, y_clean, sr)
        input_path = clean_path

    board = PRESETS.get(preset, PRESETS["studio"])

    with AudioFile(input_path) as f:
        audio = f.read(f.frames)
        samplerate = f.samplerate

    processed = board(audio, samplerate)

    with AudioFile(output_path, "w", samplerate, audio.shape[0]) as f:
        f.write(processed)

    print(f"✅ تمت المعالجة! النتيجة: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="معالجة الصوت الديني")
    parser.add_argument("input", help="مسار ملف الصوت المدخل")
    parser.add_argument("output", help="مسار ملف الصوت الناتج")
    parser.add_argument(
        "--preset",
        choices=["masjid", "lecture", "studio", "deep"],
        default="studio",
        help="الإعداد المختار",
    )
    parser.add_argument(
        "--no-denoise",
        action="store_true",
        help="تعطيل إزالة الضجيج",
    )
    args = parser.parse_args()
    process_voice(args.input, args.output, args.preset, not args.no_denoise)
