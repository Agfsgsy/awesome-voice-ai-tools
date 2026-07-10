#!/bin/bash
# Voice AI Studio Arabic - AI Engines Doctor
echo "=== AI Engines Doctor ==="

python3 -c "
import sys
sys.path.insert(0, '.')
from backend.core.tts_registry import tts_registry
tts_registry.initialize()

plugins = tts_registry.get_all_plugins()
print(f'TTS Plugins registered: {len(plugins)}')
print()

for plugin in plugins:
    h = plugin.health()
    status = '✓' if h['ready'] else '✗'
    print(f'{status} {h["label"]:20s} | installed: {h["installed"]} | models: {h["models_count"]} | voices: {h["voices_count"]} | ready: {h["ready"]}')

print()
auto = tts_registry.auto_select_engine()
if auto:
    print(f'Auto-selected engine: {auto}')
else:
    print('No engine ready. Install engines: ./scripts/install_ai.sh')
    print('Download models: ./scripts/download_models.sh')
"

echo ""
echo "=== Doctor AI Complete ==="
