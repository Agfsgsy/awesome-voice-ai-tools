# Changelog

## v3.0.0 - Production Platform Release

### Core Infrastructure
- Enhanced configuration system with Pydantic Settings
- Structured logging with JSON formatting and rotation
- Security middleware: headers, rate limiting, request logging
- Comprehensive health monitoring with 12+ check types
- GPU/CPU auto-detection (CUDA, MPS, CPU)

### New Managers (8 modules)
- **Task Manager** - Priority queue, batch processing, scheduler
- **Cache Manager** - TTL, LRU/LFU eviction, statistics
- **Language Manager** - 50+ languages, auto-detection
- **Download Manager** - Resume support, progress tracking
- **Upload Manager** - Validation, processing pipeline
- **Output Manager** - File organization, cleanup
- **Settings Manager** - Persistent configuration

### Enhanced Managers
- **Plugin Manager** - Full CRUD, enable/disable, dependencies, health checks
- **Model Manager** - Resume download, SHA-256 verification, search, import/export
- **Voice Manager** - Voice packs, categories, tags, favorites, search

### TTS Engine
- Streaming TTS support
- Batch TTS processing
- 5 new plugins: F5-TTS, Fish Speech, CosyVoice, Parler TTS, OpenVoice
- GPU/CPU auto-selection

### API (50+ endpoints)
- Batch TTS endpoint
- Streaming TTS endpoint
- Full plugin management CRUD
- Model search, download, verify, delete
- Voice search, favorites
- Language detection
- Task queue management
- Cache management
- Download/Upload management
- Settings management
- Health monitoring
- System statistics

### Frontend
- Complete redesigned UI
- Plugin Manager panel
- Model Library with search/download
- Voice Library with favorites
- Downloads Manager with progress
- Uploads Manager with drag-drop
- Tasks Manager
- System Health dashboard
- Logs Viewer with filtering
- Settings panel
- Dark/Light mode toggle
- Full RTL Arabic support
- Responsive design

### Infrastructure
- Updated Dockerfile with health checks
- Updated docker-compose with resource limits
- Updated all requirements files
- Comprehensive test suite (10+ test classes)
- Full API documentation

## v2.0.0 - Initial Release
- Basic TTS with 5 engines
- Simple plugin system
- Voice cloning with XTTS
- Basic web UI
