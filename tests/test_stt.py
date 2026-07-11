import sys
import os
import pytest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_stt_plugin_loading():
    from backend.core.plugin_manager import init_plugin_manager
    from backend.core.config import PLUGINS_DIR
    pm = init_plugin_manager(PLUGINS_DIR)
    pm.load_plugin("stt_plugin")
    info = pm.get_info()
    assert any(p["name"] == "Speech-To-Text" for p in info)

def test_stt_transcribe_dummy_audio():
    from backend.plugins.builtin.stt_plugin import transcribe_audio
    from backend.core.audio_utils import generate_sine_wave, save_audio

    # Generate a dummy audio file
    data = generate_sine_wave(duration=0.5)
    filepath = save_audio(data, "test_stt.wav")

    # Since it's a sine wave, STT will likely return nothing or an error, which is expected.
    # We just test that it runs without crashing.
    result = transcribe_audio(str(filepath))
    assert isinstance(result, str)

    # Clean up
    if filepath.exists():
        filepath.unlink()
