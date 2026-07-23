"""إضافة المؤثرات الصوتية"""
__version__ = "1.0.0"
PLUGIN_NAME = "Audio Effects"
PLUGIN_DESCRIPTION = "معالجة الصوت: إزالة ضجيج، تغيير سرعة، طبقة، ضغط، ريفرب"

PRESETS = {
    "studio": {"noise_reduction": True, "compressor": True, "eq": True},
    "lecture": {"noise_reduction": True, "compressor": False, "reverb": "light"},
    "mosque": {"noise_reduction": True, "reverb": "heavy", "eq": "bass_boost"},
    "deep_voice": {"pitch": -3, "compressor": True},
    "podcast": {"noise_reduction": True, "compressor": True, "eq": True, "reverb": "none"},
    "video_commentary": {"noise_reduction": True, "compressor": True, "speed": 1.05},
}


def register():
    pass


def get_presets():
    return PRESETS


def edit_audio(input_path: str, output_path: str, trim_start_ms: int = None, trim_end_ms: int = None) -> bool:
    """Trim and edit audio files using pydub"""
    try:
        from pydub import AudioSegment
    except ImportError:
        print("pydub not installed, falling back to basic processing")
        return False

    try:
        audio = AudioSegment.from_file(input_path)

        if trim_start_ms is not None:
            audio = audio[trim_start_ms:]
        if trim_end_ms is not None and trim_end_ms > 0:
            audio = audio[:-trim_end_ms]

        audio.export(output_path, format="wav")
        return True
    except Exception as e:
        print(f"Error editing audio: {e}")
        return False

def process_audio(input_path: str, output_path: str, preset_name: str) -> bool:
    """تطبيق التأثيرات على ملف الصوت"""
    import numpy as np
    import scipy.io.wavfile as wavfile

    try:
        sample_rate, data = wavfile.read(input_path)
    except Exception as e:
        print(f"Error reading audio: {e}")
        return False

    preset = PRESETS.get(preset_name, {})

    # تحويل إلى float32 للمعالجة
    if data.dtype != np.float32:
        max_val = np.iinfo(data.dtype).max if np.issubdtype(data.dtype, np.integer) else 1.0
        data = data.astype(np.float32) / max_val

    # Pitch shift / speed change (simple resampling for speed, crude pitch)
    # Using simple speed changing as basic implementation since full pitch shifting without
    # external libraries like librosa/pydub is complex.
    speed = preset.get("speed", 1.0)
    pitch = preset.get("pitch", 0)

    # For speed change, just change sample rate
    new_sample_rate = sample_rate

    if speed != 1.0:
        new_sample_rate = int(sample_rate * speed)

    # For pitch, we'll do a simple speed change to simulate pitch without time stretching
    if pitch != 0:
        # pitch < 0 means lower pitch (slower)
        # pitch > 0 means higher pitch (faster)
        pitch_factor = 2 ** (pitch / 12.0)
        new_sample_rate = int(new_sample_rate / pitch_factor)

    # Basic compressor (normalize)
    if preset.get("compressor"):
        max_amp = np.max(np.abs(data))
        if max_amp > 0:
            data = data / max_amp * 0.9  # Normalize to 90%

    # Simple Reverb simulation using delay
    reverb = preset.get("reverb")
    if reverb and reverb != "none":
        delay_ms = 100 if reverb == "light" else 300
        decay = 0.3 if reverb == "light" else 0.6
        delay_samples = int(new_sample_rate * (delay_ms / 1000.0))

        # Create zero array for delayed signal
        delayed = np.zeros_like(data)
        if len(data.shape) > 1: # Stereo
            delayed[delay_samples:, :] = data[:-delay_samples, :] * decay
        else: # Mono
            delayed[delay_samples:] = data[:-delay_samples] * decay

        data = data + delayed

        # Re-normalize
        max_amp = np.max(np.abs(data))
        if max_amp > 0:
            data = data / max_amp * 0.9

    # Convert back to int16
    data_int16 = np.int16(data * 32767)

    try:
        wavfile.write(output_path, new_sample_rate, data_int16)
        return True
    except Exception as e:
        print(f"Error writing audio: {e}")
        return False
