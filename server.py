#!/usr/bin/env python3
"""
Voice AI Studio - Backend Server
الخادم الخلفي الموحد لجميع أدوات الصوت
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
import uuid
import shutil
from pathlib import Path

app = FastAPI(title="Voice AI Studio API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")
app.mount("/", StaticFiles(directory="web", html=True), name="web")


class TTSRequest(BaseModel):
    text: str
    engine: str = "f5tts"
    language: str = "ar"


class IslamicRequest(BaseModel):
    text: str
    style: str = "murattal"
    type: str = "adhan"


def save_upload(file: UploadFile) -> Path:
    ext = Path(file.filename).suffix
    path = UPLOAD_DIR / f"{uuid.uuid4()}{ext}"
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return path


def apply_audio_effects(input_path: str, output_path: str, preset: str = "studio",
                        reverb: float = 0.1, echo: float = 0.0,
                        pitch: int = 0, denoise: bool = True) -> str:
    try:
        from pedalboard import Pedalboard, Reverb, Compressor, HighpassFilter, Gain
        from pedalboard.io import AudioFile
        import numpy as np

        PRESETS = {
            "studio": Pedalboard([HighpassFilter(100), Compressor(-12, 2), Gain(1)]),
            "masjid": Pedalboard([HighpassFilter(80), Compressor(-20, 2.5), Reverb(0.45, 0.4, 0.25, 0.75), Gain(2)]),
            "lecture": Pedalboard([HighpassFilter(120), Compressor(-18, 4), Reverb(0.1, 0.6, 0.05), Gain(2)]),
            "deep": Pedalboard([HighpassFilter(60), Compressor(-22, 3), Reverb(0.3, 0.5, 0.15), Gain(3)]),
        }

        if denoise:
            import noisereduce as nr
            import soundfile as sf
            y, sr = sf.read(input_path)
            if len(y.shape) > 1:
                y = y.mean(axis=1)
            y_clean = nr.reduce_noise(y=y, sr=sr)
            clean_path = str(input_path).replace(".wav", "_clean.wav")
            sf.write(clean_path, y_clean, sr)
            input_path = clean_path

        board = PRESETS.get(preset, PRESETS["studio"])
        with AudioFile(input_path) as f:
            audio = f.read(f.frames)
            samplerate = f.samplerate

        processed = board(audio, samplerate)

        if pitch != 0:
            import librosa
            import soundfile as sf
            import numpy as np
            mono = processed[0] if processed.ndim > 1 else processed
            shifted = librosa.effects.pitch_shift(mono, sr=samplerate, n_steps=pitch)
            processed = np.array([shifted])

        with AudioFile(output_path, "w", samplerate, processed.shape[0]) as f:
            f.write(processed)

        return output_path
    except ImportError as e:
        raise HTTPException(400, f"مكتبة غير مثبتة: {e}. شغّل: pip install pedalboard noisereduce librosa")


@app.post("/api/tts")
async def tts_endpoint(req: TTSRequest):
    output_file = OUTPUT_DIR / f"tts_{uuid.uuid4()}.wav"

    if req.engine == "f5tts":
        try:
            from f5_tts.api import F5TTS
            import soundfile as sf
            tts = F5TTS()
            wav, sr, _ = tts.infer(ref_file=None, ref_text="", gen_text=req.text)
            sf.write(str(output_file), wav, sr)
        except ImportError:
            raise HTTPException(400, "F5-TTS غير مثبت. شغّل: pip install f5-tts")

    elif req.engine == "xtts":
        try:
            from TTS.api import TTS
            tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
            tts.tts_to_file(text=req.text, language=req.language, file_path=str(output_file))
        except ImportError:
            raise HTTPException(400, "Coqui TTS غير مثبت. شغّل: pip install TTS")

    elif req.engine == "bark":
        try:
            from bark import SAMPLE_RATE, generate_audio, preload_models
            import soundfile as sf
            preload_models()
            audio = generate_audio(req.text)
            sf.write(str(output_file), audio, SAMPLE_RATE)
        except ImportError:
            raise HTTPException(400, "Bark غير مثبت")

    elif req.engine == "kokoro":
        try:
            from kokoro import KPipeline
            import soundfile as sf
            pipeline = KPipeline(lang_code="a")
            for _, _, audio in pipeline(req.text, voice="af_heart"):
                sf.write(str(output_file), audio, 24000)
                break
        except ImportError:
            raise HTTPException(400, "Kokoro غير مثبت. شغّل: pip install kokoro")

    else:
        raise HTTPException(400, f"المحرك '{req.engine}' غير مدعوم")

    return {"audio_url": f"/outputs/{output_file.name}", "engine": req.engine}


@app.post("/api/clone")
async def clone_endpoint(
    text: str = Form(...),
    engine: str = Form("xtts"),
    reference: UploadFile = File(...)
):
    ref_path = save_upload(reference)
    output_file = OUTPUT_DIR / f"clone_{uuid.uuid4()}.wav"

    if engine == "xtts":
        try:
            from TTS.api import TTS
            tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
            tts.tts_to_file(text=text, speaker_wav=str(ref_path), language="ar", file_path=str(output_file))
        except ImportError:
            raise HTTPException(400, "Coqui TTS غير مثبت")

    elif engine == "f5tts":
        try:
            from f5_tts.api import F5TTS
            import soundfile as sf
            tts = F5TTS()
            wav, sr, _ = tts.infer(ref_file=str(ref_path), ref_text="", gen_text=text)
            sf.write(str(output_file), wav, sr)
        except ImportError:
            raise HTTPException(400, "F5-TTS غير مثبت")

    else:
        raise HTTPException(400, f"المحرك '{engine}' غير مدعوم للاستنساخ")

    return {"audio_url": f"/outputs/{output_file.name}"}


@app.post("/api/effects")
async def effects_endpoint(
    audio: UploadFile = File(...),
    preset: str = Form("studio"),
    reverb: float = Form(0.1),
    echo: float = Form(0.0),
    compress: float = Form(0.5),
    pitch: int = Form(0),
    denoise: bool = Form(True)
):
    input_path = save_upload(audio)
    output_path = str(OUTPUT_DIR / f"fx_{uuid.uuid4()}.wav")
    apply_audio_effects(str(input_path), output_path, preset, reverb, echo, pitch, denoise)
    return {"audio_url": f"/outputs/{Path(output_path).name}"}


@app.post("/api/islamic/quran")
async def quran_endpoint(req: IslamicRequest):
    try:
        from TTS.api import TTS
        tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
        output_file = OUTPUT_DIR / f"quran_{uuid.uuid4()}.wav"
        tts.tts_to_file(text=req.text, language="ar", file_path=str(output_file))
        return {"audio_url": f"/outputs/{output_file.name}"}
    except ImportError:
        raise HTTPException(400, "Coqui TTS غير مثبت")


@app.post("/api/islamic/sheikh")
async def sheikh_endpoint(
    text: str = Form(...),
    preset: str = Form("masjid"),
    reference: UploadFile = File(None)
):
    output_file = OUTPUT_DIR / f"sheikh_{uuid.uuid4()}.wav"
    raw_output = OUTPUT_DIR / f"raw_{uuid.uuid4()}.wav"

    try:
        from TTS.api import TTS
        tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
        ref_path = save_upload(reference) if reference else None
        if ref_path:
            tts.tts_to_file(text=text, speaker_wav=str(ref_path), language="ar", file_path=str(raw_output))
        else:
            tts.tts_to_file(text=text, language="ar", file_path=str(raw_output))
    except ImportError:
        raise HTTPException(400, "Coqui TTS غير مثبت")

    apply_audio_effects(str(raw_output), str(output_file), preset)
    return {"audio_url": f"/outputs/{output_file.name}"}


@app.post("/api/islamic/adhan")
async def adhan_endpoint(req: IslamicRequest):
    adhan_texts = {
        "adhan": "اللَّهُ أَكْبَرُ اللَّهُ أَكْبَرُ. أَشْهَدُ أَنْ لَا إِلَهَ إِلَّا اللَّهُ. أَشْهَدُ أَنَّ مُحَمَّدًا رَسُولُ اللَّهِ. حَيَّ عَلَى الصَّلَاةِ. حَيَّ عَلَى الْفَلَاحِ. اللَّهُ أَكْبَرُ. لَا إِلَهَ إِلَّا اللَّهُ.",
        "dhikr": "سُبْحَانَ اللَّهِ وَبِحَمْدِهِ سُبْحَانَ اللَّهِ الْعَظِيمِ",
        "dua": "اللَّهُمَّ إِنِّي أَسْأَلُكَ الْعَفْوَ وَالْعَافِيَةَ فِي الدُّنْيَا وَالْآخِرَةِ",
    }
    text = req.text if req.text else adhan_texts.get(req.type, adhan_texts["adhan"])
    try:
        from TTS.api import TTS
        tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
        raw_output = OUTPUT_DIR / f"raw_{uuid.uuid4()}.wav"
        output_file = OUTPUT_DIR / f"adhan_{uuid.uuid4()}.wav"
        tts.tts_to_file(text=text, language="ar", file_path=str(raw_output))
        apply_audio_effects(str(raw_output), str(output_file), "masjid")
        return {"audio_url": f"/outputs/{output_file.name}"}
    except ImportError:
        raise HTTPException(400, "Coqui TTS غير مثبت")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
