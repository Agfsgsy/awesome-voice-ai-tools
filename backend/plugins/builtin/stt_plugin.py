"""إضافة التعرف على الكلام (STT) باستخدام SpeechRecognition"""
__version__ = "1.0.0"
PLUGIN_NAME = "Speech-To-Text"
PLUGIN_DESCRIPTION = "تحويل الصوت إلى نص باستخدام SpeechRecognition (Google API أو نماذج محلية)"

def register():
    pass

def transcribe_audio(filepath: str, language: str = "ar-SA") -> str:
    """تحويل ملف الصوت إلى نص"""
    import speech_recognition as sr
    import os
    from pydub import AudioSegment

    r = sr.Recognizer()

    # تحويل إلى wav إذا لم يكن كذلك
    temp_wav = filepath
    if not filepath.lower().endswith('.wav'):
        temp_wav = filepath + "_temp.wav"
        audio = AudioSegment.from_file(filepath)
        audio.export(temp_wav, format="wav")

    try:
        with sr.AudioFile(temp_wav) as source:
            audio_data = r.record(source)
            text = r.recognize_google(audio_data, language=language)
            return text
    except sr.UnknownValueError:
        return "لم يتم التعرف على الصوت"
    except sr.RequestError as e:
        return f"خطأ في الاتصال بالخدمة: {e}"
    except Exception as e:
        return f"حدث خطأ: {e}"
    finally:
        if temp_wav != filepath and os.path.exists(temp_wav):
            os.remove(temp_wav)
