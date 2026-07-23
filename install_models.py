#!/usr/bin/env python3
"""تثبيت نماذج TTS لجميع المحركات المتاحة"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.tts_registry import tts_registry

def main():
    print("=== Installing TTS Models ===\n")
    tts_registry.initialize()
    plugins = tts_registry.get_all_plugins()

    for plugin in plugins:
        print(f"--- {plugin.label} ({plugin.name}) ---")
        if not plugin.check():
            print(f"  [INFO] Not installed. Attempting auto-installation for {plugin.name}...")
            install_result = plugin.install()
            if install_result.get("success"):
                print(f"  [SUCCESS] Auto-installed {plugin.name}.")
            else:
                print(f"  [SKIP] Auto-install failed: {install_result.get('message', 'Unknown error')}. Please run install_ai.sh or install_ai.bat first.")
                continue

        models = plugin.list_models()
        for model in models:
            if not model.get("downloaded"):
                print(f"  Downloading: {model['name']}...")
                result = plugin.download_models(model["name"])
                if result.get("success"):
                    print(f"  [OK] {result.get('message', 'Done')}")
                else:
                    print(f"  [FAIL] {result.get('message', 'Unknown error')}")
            else:
                print(f"  [SKIP] Already downloaded: {model['name']}")
        print()

    print("=== Model Installation Complete ===")

if __name__ == "__main__":
    main()
