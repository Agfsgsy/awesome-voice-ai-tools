"""Tests for audio_utils module"""
import sys
import os
import pytest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.audio_utils import generate_sine_wave, save_audio


def test_generate_sine_wave_default():
    """Test generating a sine wave with default parameters."""
    data = generate_sine_wave()
    # Default duration is 1.0, sample_rate is 22050, 1 channel, 2 bytes per sample
    # so length should be 22050 * 2 = 44100
    assert isinstance(data, bytes)
    assert len(data) == 44100


def test_generate_sine_wave_custom():
    """Test generating a sine wave with custom parameters."""
    data = generate_sine_wave(frequency=880.0, duration=0.5, sample_rate=16000)
    # duration 0.5, sample_rate 16000 -> 8000 samples -> 16000 bytes
    assert isinstance(data, bytes)
    assert len(data) == 16000


@pytest.fixture
def mock_outputs_dir(tmp_path):
    with patch("backend.core.audio_utils.OUTPUTS_DIR", tmp_path):
        yield tmp_path


def test_save_audio_bytes(mock_outputs_dir):
    """Test saving audio from bytes."""
    data = generate_sine_wave(duration=0.1)
    filename = "test_bytes.wav"
    filepath = save_audio(data, filename)

    assert isinstance(filepath, Path)
    assert filepath.exists()
    assert filepath.parent == mock_outputs_dir
    assert filepath.name == filename

    # Check if it's a valid wav file
    import wave
    with wave.open(str(filepath), 'r') as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 22050


def test_save_audio_array(mock_outputs_dir):
    """Test saving audio from array-like data."""
    # Create a simple list of floats
    data = [0.0, 0.5, -0.5, 0.0]
    filename = "test_array.wav"
    filepath = save_audio(data, filename, sample_rate=16000)

    assert isinstance(filepath, Path)
    assert filepath.exists()
    assert filepath.parent == mock_outputs_dir
    assert filepath.name == filename

    import wave
    with wave.open(str(filepath), 'r') as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 16000


def test_save_audio_unsupported():
    """Test saving audio with an unsupported data type raises ValueError."""
    data = 12345  # integer is unsupported
    with pytest.raises(ValueError, match="Unsupported audio data type"):
        save_audio(data, "test_error.wav")
