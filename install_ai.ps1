Write-Host "=================================================="
Write-Host "Starting Installation Process..."
Write-Host "=================================================="

# Check for CUDA
$cuda_available = $false
try {
    $nvidia_smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if ($nvidia_smi) {
        Write-Host "[INFO] NVIDIA GPU detected. Will install CUDA-enabled PyTorch." -ForegroundColor Green
        $cuda_available = $true
    } else {
        Write-Host "[INFO] NVIDIA GPU not detected (nvidia-smi not found). Will install CPU-only PyTorch." -ForegroundColor Yellow
    }
} catch {
    Write-Host "[INFO] Error checking for NVIDIA GPU. Defaulting to CPU." -ForegroundColor Yellow
}

# Upgrade pip
Write-Host "`n[1/5] Upgrading pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip

# Install basic requirements
Write-Host "`n[2/5] Installing base requirements..." -ForegroundColor Cyan
pip install -r requirements.txt

# Install PyTorch
Write-Host "`n[3/5] Installing PyTorch..." -ForegroundColor Cyan
if ($cuda_available) {
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
} else {
    pip install torch torchvision torchaudio
}

# Install TTS Engines
Write-Host "`n[4/5] Installing TTS Engines..." -ForegroundColor Cyan

Write-Host "  - Piper TTS..."
pip install piper-tts

Write-Host "  - Kokoro TTS..."
pip install kokoro

Write-Host "  - Coqui TTS..."
pip install TTS

Write-Host "  - MeloTTS..."
pip install git+https://github.com/myshell-ai/MeloTTS.git
pip install unidic cn2an jieba g2p-en

Write-Host "  - StyleTTS2..."
# StyleTTS2 installation requires specific steps, often handled by the plugin, but we install base requirements here
# The plugin's install() method handles cloning the repo.
pip install soundfile librosa pydub

# Run the python installer script to auto-register and download models
Write-Host "`n[5/5] Downloading models and verifying installation..." -ForegroundColor Cyan
python install_models.py
python verify_windows_install.py

Write-Host "`n=================================================="
Write-Host "Installation Complete!" -ForegroundColor Green
Write-Host "You can now run: python main.py" -ForegroundColor Green
Write-Host "=================================================="
