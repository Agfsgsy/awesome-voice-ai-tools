import os
import sys
import subprocess
import time

def run_command(command, description):
    print(f"[*] {description}...")
    try:
        subprocess.check_call(command, shell=True)
        print(f"[+] {description} completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"[-] Error during {description}: {e}")
        sys.exit(1)

def install_dependencies():
    print("====== Installing Dependencies ======")
    run_command("pip install -q -r requirements.txt", "Installing core requirements")

    if os.path.exists("requirements-colab.txt"):
        # Catch errors to handle environments where some dependencies might not be compatible
        # like Python 3.12 with TTS requiring <3.12. In Colab, Python is 3.10 so it's fine.
        try:
            run_command("pip install -q -r requirements-colab.txt", "Installing Colab specific requirements")
        except SystemExit:
            print("[-] Warning: Failed to install some Colab specific requirements. Continuing anyway...")

    if os.environ.get("NGROK_AUTHTOKEN"):
        run_command("pip install -q pyngrok", "Installing pyngrok")
    print("====== Dependencies Installed ======\n")

def setup_ngrok():
    auth_token = os.environ.get("NGROK_AUTHTOKEN")
    if not auth_token:
        print("[*] NGROK_AUTHTOKEN not found. Running on localhost only.")
        return None

    print("====== Setting up ngrok ======")
    try:
        from pyngrok import ngrok, conf
        conf.get_default().auth_token = auth_token

        # Open a HTTP tunnel on port 8000
        public_url = ngrok.connect(8000).public_url
        print(f"\n[+] ngrok tunnel successfully established!")
        print(f"[+] Public URL: {public_url}")
        print(f"[*] You can access the API at: {public_url}/docs\n")
        return public_url
    except Exception as e:
        print(f"[-] Failed to set up ngrok: {e}")
        return None

def start_server():
    print("====== Starting Uvicorn Server ======")
    try:
        import uvicorn
        # Try to import nest_asyncio to allow nested event loops in Colab
        try:
            import nest_asyncio
            nest_asyncio.apply()
        except ImportError:
            pass

        print("[*] Server running on http://127.0.0.1:8000")
        uvicorn.run("main:app", host="0.0.0.0", port=8000, log_level="info")
    except Exception as e:
        print(f"[-] Error starting server: {e}")

if __name__ == "__main__":
    print("🚀 Voice AI Studio Arabic - Google Colab Launcher 🚀\n")
    install_dependencies()
    setup_ngrok()
    start_server()
