# Voice AI Studio Arabic - API Documentation v3.0

## Base URL
- Local: `http://localhost:8000`
- Default port: `8000`

## Interactive Documentation
- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI Schema: `/openapi.json`

## Rate Limiting
- 120 requests per minute (default)
- Rate limit info included in response headers

---

## Endpoints

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | App info |
| GET | `/health` | Health check |
| GET | `/health/detailed` | Detailed health |
| GET | `/status` | System status |
| GET | `/version` | Version info |
| GET | `/api/info` | App configuration |
| GET | `/api/system` | System info |
| GET | `/api/system/stats` | Aggregated stats |

### Text-to-Speech
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/tts` | Generate speech |
| POST | `/api/tts/batch` | Batch TTS |
| POST | `/api/tts/stream` | Streaming TTS |
| POST | `/api/speech` | Alias for /api/tts |

### Voice Cloning
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/audio/clone` | Clone voice |

### Plugins
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/plugins` | List plugins |
| GET | `/api/plugins/{name}` | Plugin detail |
| POST | `/api/plugins/install` | Install plugin |
| POST | `/api/plugins/action` | Enable/disable/reload/delete |
| GET | `/api/plugins/{name}/health` | Health check |

### Models
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/models` | List models |
| POST | `/api/models/search` | Search models |
| POST | `/api/models/download` | Download model |
| GET | `/api/models/{engine}/{model_name}` | Model info |
| DELETE | `/api/models/{engine}/{model_name}` | Delete model |
| POST | `/api/models/{engine}/{model_name}/verify` | Verify checksum |
| GET | `/api/models/stats` | Statistics |

### Voices
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/voices` | List voices |
| POST | `/api/voices/search` | Search voices |
| GET | `/api/voices/{voice_id}` | Voice detail |
| POST | `/api/voices/{voice_id}/favorite` | Toggle favorite |
| GET | `/api/voices/favorites/list` | Favorites |
| GET | `/api/voices/stats` | Statistics |

### Languages
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/languages` | List languages |
| POST | `/api/languages/detect` | Detect language |
| GET | `/api/languages/{code}/engines` | Supported engines |

### Tasks
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/tasks` | List tasks |
| POST | `/api/tasks` | Create task |
| GET | `/api/tasks/{task_id}` | Task detail |
| POST | `/api/tasks/{task_id}/cancel` | Cancel task |
| GET | `/api/tasks/stats` | Statistics |

### Cache
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/cache` | Cache info |
| POST | `/api/cache` | Clear/cleanup |

### Downloads
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/downloads/create` | Create download |
| POST | `/api/downloads/{task_id}/start` | Start download |
| GET | `/api/downloads/tasks` | List downloads |
| GET | `/api/downloads/{task_id}` | Download status |
| GET | `/api/downloads/stats` | Statistics |

### Uploads
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/uploads` | Upload file |
| GET | `/api/uploads` | List uploads |
| DELETE | `/api/uploads/{entry_id}` | Delete upload |

### Outputs
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/downloads` | List outputs |
| GET | `/api/downloads/{filename}` | Download file |
| DELETE | `/api/downloads/{filename}` | Delete file |
| POST | `/api/downloads/{filename}/rename` | Rename file |
| GET | `/api/downloads/{filename}/info` | File info |
| POST | `/api/downloads/{filename}/effects` | Apply effects |
| GET | `/api/outputs/stats` | Statistics |

### Settings
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/settings` | All settings |
| GET | `/api/settings/{section}` | Section settings |
| POST | `/api/settings/{section}` | Update section |
| POST | `/api/settings/reset` | Reset settings |

### Logs
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/logs` | View logs |
| GET | `/api/logs/download` | Download logs |

---

## Examples

### TTS
```bash
curl -X POST http://localhost:8000/api/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "مرحبا بالعالم", "engine": "kokoro", "language": "ar"}'
```

### Batch TTS
```bash
curl -X POST http://localhost:8000/api/tts/batch \
  -H "Content-Type: application/json" \
  -d '{"texts": ["text 1", "text 2"], "engine": "kokoro"}'
```

### Voice Clone
```bash
curl -X POST http://localhost:8000/api/audio/clone \
  -H "Content-Type: application/json" \
  -d '{"reference_audio": "/path/to/voice.wav", "text": "Hello", "engine": "xtts"}'
```

### Upload
```bash
curl -X POST http://localhost:8000/api/uploads \
  -F "file=@audio.wav"
```
