# دليل API - Voice AI Studio Arabic

## نقاط النهاية (Endpoints)

### عام
| المسار | الطريقة | الوصف |
|--------|---------|-------|
| `/` | GET | معلومات التطبيق |
| `/health` | GET | فحص الصحة |
| `/status` | GET | حالة النظام |
| `/version` | GET | إصدار التطبيق |

### API
| المسار | الطريقة | الوصف |
|--------|---------|-------|
| `/api/info` | GET | معلومات التطبيق والمحركات |
| `/api/plugins` | GET | قائمة الإضافات |
| `/api/models` | GET | قائمة النماذج |
| `/api/voices` | GET | قائمة الأصوات |
| `/api/settings` | GET | الإعدادات |
| `/api/settings` | POST | تحديث الإعدادات |
| `/api/system` | GET | معلومات النظام |
| `/api/logs` | GET | سجلات التطبيق |
| `/api/downloads` | GET | قائمة الملفات للتنزيل |
| `/api/downloads/{filename}` | GET | تنزيل ملف |
| `/api/downloads/{filename}` | DELETE | حذف ملف |
| `/api/uploads` | GET | قائمة الملفات المرفوعة |
| `/api/uploads` | POST | رفع ملف |
| `/api/tts` | POST | توليد صوت |
| `/api/speech` | POST | توليد صوت (alias) |
| `/api/audio/clone` | POST | استنساخ صوت |
| `/api/audio/upload` | POST | رفع ملف صوت |
| `/api/audio/list` | GET | قائمة كل الملفات الصوتية |
| `/api/cache` | GET | معلومات الذاكرة المؤقتة |
| `/api/cache` | DELETE | مسح الذاكرة المؤقتة |
| `/api/files/{filename}/rename` | POST | إعادة تسمية ملف |

### أمثلة

#### توليد صوت
```bash
curl -X POST http://localhost:8000/api/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "مرحباً بالعالم", "engine": "kokoro", "language": "ar"}'
```

#### استنساخ صوت
```bash
curl -X POST http://localhost:8000/api/audio/clone \
  -H "Content-Type: application/json" \
  -d '{"reference_audio": "/path/to/voice.wav", "text": "هذا نص للاستنساخ", "engine": "xtts"}'
```

#### رفع ملف
```bash
curl -X POST http://localhost:8000/api/uploads \
  -F "file=@audio.wav"
```

## وثائق تفاعلية

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
