#!/bin/bash
# Voice AI Studio Arabic - Download TTS Models
set -e
echo "=== Downloading TTS Models ==="

python3 download_models.py --engine all

echo ""
echo "=== Model Download Complete ==="
