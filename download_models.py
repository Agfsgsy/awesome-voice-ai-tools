#!/usr/bin/env python3
"""تحميل نماذج TTS"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.tts_registry import tts_registry

def main():
    parser = argparse.ArgumentParser(description="Download TTS models")
    parser.add_argument("--engine", "-e", default="all", help="Engine name (piper, kokoro, coqui, melotts, styletts2, all)")
    parser.add_argument("--model", "-m", default="default", help="Model name")
    args = parser.parse_args()

    tts_registry.initialize()

    if args.engine == "all":
        plugins = tts_registry.get_all_plugins()
        for plugin in plugins:
            print(f"\n--- {plugin.label} ---")
            if not plugin.check():
                print(f"  [SKIP] Not installed")
                continue
            result = plugin.download_models(args.model)
            status = "OK" if result.get("success") else "FAIL"
            print(f"  [{status}] {result.get('message', '')}")
    else:
        plugin = tts_registry.get_plugin(args.engine)
        if not plugin:
            print(f"Engine '{args.engine}' not found. Available: {list(tts_registry.plugins.keys())}")
            sys.exit(1)
        result = plugin.download_models(args.model)
        status = "OK" if result.get("success") else "FAIL"
        print(f"[{status}] {result}")

if __name__ == "__main__":
    main()
