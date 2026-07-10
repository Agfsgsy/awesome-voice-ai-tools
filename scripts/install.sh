#!/bin/bash
# سكريبت تثبيت موحد لجميع أدوات الصوت

echo "🎙️ تثبيت Voice AI Unified Launcher..."

# التحقق من Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 غير موجود. الرجاء تثبيته أولاً."
    exit 1
fi

# إنشاء بيئة افتراضية
echo "📦 إنشاء بيئة افتراضية..."
python3 -m venv venv
source venv/bin/activate

# ترقية pip
pip install --upgrade pip

# تثبيت المتطلبات الأساسية
echo "⬇️ تثبيت المتطلبات الأساسية..."
pip install gradio soundfile numpy

echo ""
echo "اختر المحركات التي تريد تثبيتها:"
echo "1) F5-TTS (موصى به - جودة عالية)"
echo "2) Coqui XTTS-v2 (أفضل استنساخ)"
echo "3) Bark (صوت إبداعي)"
echo "4) Kokoro (سريع وخفيف)"
echo "5) MeloTTS (خفيف جداً)"
echo "6) جميع المحركات"
echo ""
read -p "أدخل أرقام اختيارك مفصولة بمسافة (مثال: 1 2): " choices

for choice in $choices; do
    case $choice in
        1)
            echo "⬇️ تثبيت F5-TTS..."
            pip install torch torchaudio
            pip install f5-tts
            ;;
        2)
            echo "⬇️ تثبيت Coqui XTTS-v2..."
            pip install torch torchaudio
            pip install TTS
            ;;
        3)
            echo "⬇️ تثبيت Bark..."
            pip install torch
            pip install git+https://github.com/suno-ai/bark
            ;;
        4)
            echo "⬇️ تثبيت Kokoro..."
            pip install kokoro
            ;;
        5)
            echo "⬇️ تثبيت MeloTTS..."
            pip install git+https://github.com/myshell-ai/MeloTTS
            ;;
        6)
            echo "⬇️ تثبيت جميع المحركات..."
            pip install -r requirements/requirements-all.txt
            pip install git+https://github.com/suno-ai/bark
            pip install git+https://github.com/myshell-ai/MeloTTS
            ;;
    esac
done

echo ""
echo "✅ التثبيت اكتمل!"
echo "▶️ لتشغيل الواجهة: python app.py"
