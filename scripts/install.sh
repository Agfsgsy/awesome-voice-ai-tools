#!/bin/bash
# install.sh for Linux and macOS

echo "Installing ffmpeg..."
if [ "$(uname)" == "Darwin" ]; then
    brew install ffmpeg
elif [ "$(expr substr $(uname -s) 1 5)" == "Linux" ]; then
    sudo apt update && sudo apt install -y ffmpeg python3-venv
fi

echo "Setting up Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-ai.txt

echo "Setup complete! Run 'source .venv/bin/activate && python main.py' to start the server."
