# Advanced Voice AI Suite

This additive module keeps every existing feature and adds a safer multi-engine layer for voice cloning, Arabic number reading, audio/frequency analysis, isolated music runtimes, candidate generation, and measurable ranking.

## Important limitation

No voice-cloning system can guarantee a 100% identical voice for every recording, language, emotion, or sentence. The suite reports measured scores when optional evaluators are installed and returns `null` instead of inventing a score.

Use only a voice that you own or have explicit permission to synthesize.

## Included engine registry

| Engine | Purpose | Official source |
|---|---|---|
| XTTS-v2 | Local zero-shot speech cloning | https://github.com/coqui-ai/TTS |
| OpenVoice V2 | Tone-color transfer and conversion | https://github.com/myshell-ai/OpenVoice |
| F5-TTS | Reference-conditioned TTS | https://github.com/SWivid/F5-TTS |
| GPT-SoVITS | Zero/few-shot speech generation | https://github.com/RVC-Boss/GPT-SoVITS |
| CosyVoice | Zero-shot/cross-lingual speech | https://github.com/FunAudioLLM/CosyVoice |
| RVC | Singing/voice conversion | https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI |
| ACE-Step | Song/music generation runtime | https://github.com/ace-step/ACE-Step |
| YuE | Long-form song generation runtime | https://github.com/multimodal-art-projection/YuE |

XTTS runs natively when `TTS` is installed. Other heavy engines are isolated behind a runtime API to avoid incompatible Torch/CUDA dependencies crashing the main application. Each runtime is expected to expose:

- `GET /health`
- `POST /clone` for speech/voice engines
- `POST /song/generate` for song engines

Environment variables select their endpoints, for example `F5TTS_ENDPOINT=http://127.0.0.1:8102`.

## Install core suite

### Linux

```bash
bash scripts/install_voice_ai_suite.sh
```

### Windows

```bat
scripts\install_voice_ai_suite.bat
```

Then install only the engines needed:

```bash
python scripts/voice_ai_manager.py install xtts
python scripts/voice_ai_manager.py install openvoice
python scripts/voice_ai_manager.py install f5tts
python scripts/voice_ai_manager.py install gpt_sovits
python scripts/voice_ai_manager.py install cosyvoice
python scripts/voice_ai_manager.py install rvc
python scripts/voice_ai_manager.py install ace_step
python scripts/voice_ai_manager.py install yue
```

The manager clones official sources into separate `runtimes/<engine>` directories. Review each code and model license before downloading weights or using it commercially. External projects have different launch commands, model sizes, GPU requirements, and API contracts; use a small local wrapper matching the contract above instead of mixing all dependencies into the main environment.

## Run

```bash
python main.py
```

Open:

- Main application: `http://localhost:8000`
- Advanced studio: `http://localhost:8000/voice-ai-studio`
- API documentation: `http://localhost:8000/docs`

## New endpoints

- `GET /api/voice-ai/engines`
- `POST /api/voice-ai/audio/analyze`
- `POST /api/voice-ai/audio/clone/ensemble`
- `POST /api/voice-ai/read/text`
- `POST /api/voice-ai/text/numbers`
- `POST /api/voice-ai/song/generate`

Compatibility aliases are also available under `/api/audio`, `/api/read`, `/api/text`, and `/api/song`.

## Clone example

```bash
curl -X POST http://localhost:8000/api/voice-ai/audio/clone/ensemble \
  -F "files=@voice-1.wav" \
  -F "files=@voice-2.wav" \
  -F "text=مرحبًا، هذا اختبار للصوت بعد تحليل التسجيل." \
  -F "engine=auto" \
  -F "language=ar" \
  -F "quality_mode=high" \
  -F "candidate_count=3" \
  -F "consent_confirmed=true"
```

## Quality path

1. Validates that references are inside allowed application directories.
2. Checks format and decodes through FFmpeg/ffprobe.
3. Measures duration, silence, clipping, loudness, F0, and spectral centroid when dependencies are present.
4. Converts references to mono 24 kHz WAV without pitch/formant shifting.
5. Generates bounded candidates across healthy engines.
6. Measures speaker similarity with SpeechBrain when installed.
7. Measures reading accuracy with faster-whisper when installed.
8. Combines identity, intelligibility, audio quality, and frequency scores.
9. Returns the best valid candidate and never invents unavailable metrics.

## Gemini and Google Custom Voice

Gemini prebuilt TTS is a reading engine, not arbitrary voice cloning. Google Cloud custom voice is a separate restricted service that requires Google credentials, explicit consent, service availability, and may incur charges. It is not represented as a free local cloning engine.
