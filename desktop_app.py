"""مشغل سطح المكتب لبرنامج Voice AI Studio Arabic على ويندوز."""
from __future__ import annotations

import ctypes
import os
import socket
import threading
import time
from typing import Optional


def _message(title: str, text: str, error: bool = False) -> None:
    flags = 0x10 if error else 0x40
    try:
        ctypes.windll.user32.MessageBoxW(None, text, title, flags)
    except Exception:
        print(f"{title}: {text}")


def _free_port(start: int = 8765, attempts: int = 30) -> int:
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(port: int, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.4):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def main() -> int:
    port = _free_port()
    os.environ["APP_HOST"] = "127.0.0.1"
    os.environ["APP_PORT"] = str(port)
    os.environ["APP_DEBUG"] = "false"

    try:
        import uvicorn
        from main import app
    except Exception as exc:
        _message("Voice AI Studio", f"تعذر تحميل مكونات البرنامج:\n{exc}", True)
        return 1

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None
    thread = threading.Thread(target=server.run, name="voice-ai-server", daemon=True)
    thread.start()

    if not _wait_for_server(port):
        server.should_exit = True
        _message("Voice AI Studio", "تعذر تشغيل الخادم المحلي للبرنامج.", True)
        return 1

    try:
        import webview

        window = webview.create_window(
            "استوديو المواعظ والصوت العربي",
            f"http://127.0.0.1:{port}/static/pro.html",
            width=1280,
            height=820,
            min_size=(900, 620),
            text_select=True,
        )
        webview.start(debug=False, private_mode=False)
    except Exception as exc:
        _message(
            "Voice AI Studio",
            "تعذر فتح نافذة التطبيق. تأكد من وجود Microsoft Edge WebView2.\n\n"
            f"التفاصيل: {exc}",
            True,
        )
        return 1
    finally:
        server.should_exit = True
        thread.join(timeout=5)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
