#!/bin/bash
# Voice AI Studio Arabic - Google Colab Installer
set -e
echo "=== Installing Voice AI Studio Arabic on Google Colab ==="

pip install -q -r requirements-colab.txt

mkdir -p uploads outputs cache logs models voices downloads config

echo ""
echo "=== Installation Complete ==="
echo "Run: python main.py"
echo "Or use run_colab.ipynb"
