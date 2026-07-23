import requests

BASE_URL = "http://localhost:8000"
GET_ENDPOINTS = [
    "/",
    "/health",
    "/status",
    "/version",
    "/api/info",
    "/api/plugins",
    "/api/settings",
    "/api/models",
    "/api/voices",
    "/api/cache",
    "/api/system",
    "/api/downloads",
    "/api/uploads",
    "/api/audio/list"
]

def run_get_tests():
    print("Running GET endpoint tests...")
    failed = []
    for ep in GET_ENDPOINTS:
        try:
            res = requests.get(BASE_URL + ep)
            if res.status_code == 200:
                print(f"[OK] {ep}")
            else:
                print(f"[FAIL] {ep} - Status: {res.status_code}")
                failed.append(ep)
        except Exception as e:
            print(f"[ERROR] {ep} - {e}")
            failed.append(ep)

    if failed:
        print(f"\nFailed {len(failed)} endpoints.")
        exit(1)
    else:
        print("\nAll GET endpoints passed!")

def run_post_tests():
    print("\nRunning POST endpoint tests...")
    failed = []

    # Simple JSON POSTs
    json_endpoints = [
        ("/api/settings", {"gemini_tts_model": "test-model"}),
        ("/api/tts", {"text": "مرحبا", "engine": "fallback"}),
        ("/api/speech", {"text": "مرحبا", "engine": "fallback"}),
        ("/api/plugins/check", {"engine": "piper"}),
        ("/api/plugins/install", {"engine": "piper"})
    ]

    for ep, payload in json_endpoints:
        try:
            res = requests.post(BASE_URL + ep, json=payload)
            if res.status_code == 200:
                print(f"[OK] {ep}")
            else:
                print(f"[FAIL] {ep} - Status: {res.status_code} - Response: {res.text}")
                failed.append(ep)
        except Exception as e:
            print(f"[ERROR] {ep} - {e}")
            failed.append(ep)

    # File upload POSTs
    # Create dummy wav file
    import wave
    import struct
    import math

    dummy_wav = "dummy.wav"
    with wave.open(dummy_wav, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(22050)
        for i in range(22050):
            val = int(32767.0 * math.sin(2.0 * math.pi * 440.0 * i / 22050))
            data = struct.pack('<h', val)
            f.writeframesraw(data)

    file_endpoints = [
        ("/api/uploads", "file"),
        ("/api/audio/upload", "file")
    ]

    for ep, file_key in file_endpoints:
        try:
            with open(dummy_wav, "rb") as f:
                res = requests.post(BASE_URL + ep, files={file_key: ("dummy.wav", f, "audio/wav")})
                if res.status_code == 200:
                    print(f"[OK] {ep}")
                else:
                    print(f"[FAIL] {ep} - Status: {res.status_code} - Response: {res.text}")
                    failed.append(ep)
        except Exception as e:
            print(f"[ERROR] {ep} - {e}")
            failed.append(ep)

    # Clone and effects logic tests
    try:
        # Clone needs reference audio path
        clone_ep = "/api/audio/clone"
        res = requests.post(BASE_URL + clone_ep, json={"reference_audio": "dummy.wav", "text": "test", "engine": "xtts"})
        if res.status_code == 200:
             print(f"[OK] {clone_ep}")
        else:
             print(f"[FAIL] {clone_ep} - Status: {res.status_code} - Response: {res.text}")
             failed.append(clone_ep)
    except Exception as e:
         print(f"[ERROR] {clone_ep} - {e}")
         failed.append(clone_ep)

    # Effects uses Form data for preset
    try:
        effects_ep = "/api/effects/apply"
        with open(dummy_wav, "rb") as f:
            res = requests.post(BASE_URL + effects_ep, files={"file": ("dummy.wav", f, "audio/wav")}, data={"preset": "studio"})
            if res.status_code == 200:
                print(f"[OK] {effects_ep}")
            else:
                print(f"[FAIL] {effects_ep} - Status: {res.status_code} - Response: {res.text}")
                failed.append(effects_ep)
    except Exception as e:
         print(f"[ERROR] {effects_ep} - {e}")
         failed.append(effects_ep)

    # STT uses Form data for language
    try:
        stt_ep = "/api/stt"
        with open(dummy_wav, "rb") as f:
            res = requests.post(BASE_URL + stt_ep, files={"file": ("dummy.wav", f, "audio/wav")}, data={"language": "ar-SA"})
            if res.status_code == 200:
                print(f"[OK] {stt_ep}")
            else:
                print(f"[FAIL] {stt_ep} - Status: {res.status_code} - Response: {res.text}")
                failed.append(stt_ep)
    except Exception as e:
         print(f"[ERROR] {stt_ep} - {e}")
         failed.append(stt_ep)

    import os
    if os.path.exists(dummy_wav):
        os.remove(dummy_wav)

    if failed:
        print(f"\nFailed {len(failed)} POST endpoints.")
        exit(1)
    else:
        print("\nAll POST endpoints passed!")

def run_additional_tests():
    print("\nRunning additional endpoint tests...")
    failed = []

    # Rename File
    try:
        rename_ep = "/api/files/dummy.wav/rename"
        res = requests.post(BASE_URL + rename_ep, json={"new_name": "dummy_renamed.wav"})
        if res.status_code == 200:
            print(f"[OK] {rename_ep}")
        else:
            print(f"[FAIL] {rename_ep} - Status: {res.status_code} - Response: {res.text}")
            failed.append(rename_ep)

        # Rename it back
        res = requests.post(BASE_URL + "/api/files/dummy_renamed.wav/rename", json={"new_name": "dummy.wav"})
    except Exception as e:
        print(f"[ERROR] {rename_ep} - {e}")
        failed.append(rename_ep)

    # Delete File
    try:
        delete_ep = "/api/uploads/dummy.wav"
        res = requests.delete(BASE_URL + delete_ep)
        if res.status_code == 200:
            print(f"[OK] {delete_ep}")
        else:
            print(f"[FAIL] {delete_ep} - Status: {res.status_code} - Response: {res.text}")
            failed.append(delete_ep)
    except Exception as e:
        print(f"[ERROR] {delete_ep} - {e}")
        failed.append(delete_ep)

    if failed:
        print(f"\nFailed {len(failed)} additional endpoints.")
        exit(1)
    else:
        print("\nAll additional endpoints passed!")

if __name__ == "__main__":
    run_get_tests()
    run_post_tests()
    run_additional_tests()
