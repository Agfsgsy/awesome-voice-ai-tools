# Voice AI Studio Arabic v3.0

Professional open-source voice AI platform for text-to-speech, voice cloning, and audio processing.

## Features

### Text-to-Speech (15+ Engines)
- **Piper** - Fast local neural TTS, ideal for Termux/CPU
- **Kokoro** - Lightweight TTS with good quality
- **Coqui XTTS** - Multilingual voice cloning TTS
- **MeloTTS** - Fast multilingual TTS with Arabic support
- **StyleTTS2** - High-quality style-based TTS
- **F5-TTS** - Diffusion-based TTS
- **Fish Speech** - Streaming-capable TTS
- **CosyVoice** - Cross-lingual voice cloning by Alibaba
- **Parler TTS** - Description-based voice generation
- **OpenVoice** - Voice cloning with tone color control
- **Bark** - Open-source generative TTS
- **Google Gemini TTS** - Cloud-based neural TTS
- **Whisper** - Speech recognition (STT)

### Voice Cloning
- XTTS-v2, OpenVoice, CosyVoice support
- Reference audio upload and processing

### Plugin System
- Full lifecycle: install, update, enable, disable, reload, delete
- Auto-discovery and registration
- Health checks and dependency management

### Model & Voice Management
- Download with resume support
- SHA-256 checksum verification
- Search, filter, import/export
- Voice packs, categories, tags, favorites

### Audio Processing
- Format conversion (WAV, MP3, FLAC, OGG, M4A)
- Effects presets: studio, lecture, mosque, podcast
- Noise reduction, normalization, silence trimming

### Infrastructure
- Task queue with priority scheduling
- Cache manager with TTL and eviction policies
- Health monitoring with detailed checks
- Rate limiting and security headers
- Structured logging with rotation
- GPU/CPU auto-detection
- 50+ languages with auto-detection

## Quick Start

```bash
# Install
pip install -r requirements.txt
pip install -r requirements-ai.txt

# Run
python main.py

# Open http://localhost:8000
```

### Docker
```bash
docker-compose up -d
```

## API
- Web UI: http://localhost:8000
- Swagger: http://localhost:8000/docs
- API Docs: See [API.md](API.md)

## Supported Platforms
- Linux, macOS, Windows (WSL2)
- Google Colab, Termux (Android)
- Docker

## Project Structure
```
backend/
  api/routes.py          - 50+ API endpoints
  core/                  - 18 core modules
    config.py            - Configuration management
    logger.py            - Structured logging
    security.py          - Rate limiting, validation
    health.py            - Health monitoring
    audio_utils.py       - Audio processing
    tts_engine.py        - TTS engine with streaming/batch
    tts_registry.py      - Plugin registry
    plugin_manager.py    - Plugin lifecycle management
    model_manager.py     - Model download/verify/search
    voice_manager.py     - Voice library
    task_manager.py      - Task queue
    cache_manager.py     - TTL caching
    language_manager.py  - 50+ languages
    download_manager.py  - Resume downloads
    upload_manager.py    - File upload processing
    output_manager.py    - File organization
    settings_manager.py  - Persistent settings
  plugins/               - 10 TTS plugins
frontend/
  templates/index.html   - Full management UI
tests/                   - Comprehensive test suite
```

## License
MIT - Open Source
