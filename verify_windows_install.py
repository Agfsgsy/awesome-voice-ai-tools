import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from backend.core.tts_registry import tts_registry

async def main():
    print("=== Verifying TTS Installation & Generation ===")
    tts_registry.initialize()
    plugins = tts_registry.get_all_plugins()

    any_failed = False

    for plugin in plugins:
        print(f"\n--- Testing {plugin.label} ({plugin.name}) ---")
        if not plugin.check():
            print(f"[FAIL] {plugin.name} is not installed.")
            any_failed = True
            continue

        models = plugin.list_models()
        downloaded = [m for m in models if m.get("downloaded")]
        if not downloaded:
            print(f"[FAIL] {plugin.name} has no models downloaded.")
            any_failed = True
            continue

        print(f"[INFO] Engine is installed and has models. Generating test audio...")
        try:
            result = await plugin.generate(text="اختبار", language="ar", speed=1.0)
            if result.get("success"):
                print(f"[SUCCESS] Audio generated: {result.get('file')}")
            else:
                print(f"[FAIL] Generation failed: {result.get('message')}")
                any_failed = True
        except Exception as e:
            print(f"[ERROR] Exception during generation: {e}")
            any_failed = True

    if any_failed:
        print("\n=== Verification Completed with Errors ===")
        sys.exit(1)
    else:
        print("\n=== Verification Completed Successfully ===")

if __name__ == "__main__":
    asyncio.run(main())
