"""Standalone Windows desktop launcher for Voice AI Studio Arabic.

Starts the local FastAPI server in the background and displays the professional
Arabic studio in a native desktop window using pywebview.
"""
from __future__ import annotations

import ctypes
import os
import socket
import sys
import threading
import time
from typing import Optional

APP_TITLE = "Voice AI Studio Arabic Pro"
START_PORT = 8000
MUTEX_NAME = "Local\\VoiceAIStudioArabicPro"


def _message(text: str, title: str = APP_TITLE, error: bool = False) -> None:
    if sys.platform == "win32":
        flags = 0x10 if error else 0x40
        ctypes.windll.user32.MessageBoxW(None, text, title, flags)
    else:
        print(f"{title}: {text}")


def _acquire_single_instance() -> Optional[int]:
    """Prevent two desktop instances from using the same local service."""
    if sys.platform != "win32":
        return None
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return None
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.kernel32.CloseHandle(handle)
        _message("البرنامج يعمل بالفعل. ابحث عن نافذته في شريط المهام.")
        raise SystemExit(0)
    return handle


def _free_port(start: int = START_PORT, attempts: int = 30) -> int:
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


def _wait_for_server(port: int, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.2)
    return False


def main() -> int:
    mutex = _acquire_single_instance()
    port = _free_port()
    os.environ["APP_HOST"] = "127.0.0.1"
    os.environ["APP_PORT"] = str(port)
    os.environ.setdefault("APP_DEBUG", "false")

    try:
        import uvicorn
        import webview
        from main import app
    except Exception as exc:
        _message(f"تعذر تحميل مكونات التطبيق:\n{exc}", error=True)
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
    server_thread = threading.Thread(
        target=server.run,
        name="voice-ai-local-server",
        daemon=True,
    )
    server_thread.start()

    if not _wait_for_server(port):
        server.should_exit = True
        _message("تعذر تشغيل الخادم المحلي. أعد تشغيل الجهاز ثم حاول مرة أخرى.", error=True)
        return 2

    window = webview.create_window(
        APP_TITLE,
        url=f"http://127.0.0.1:{port}/static/pro.html",
        width=1320,
        height=860,
        min_size=(980, 680),
        resizable=True,
        text_select=True,
        background_color="#07111f",
    )

    def stop_server() -> None:
        server.should_exit = True

    window.events.closed += stop_server
    try:
        webview.start(debug=False, private_mode=False)
    except Exception as exc:
        _message(
            "تعذر فتح نافذة التطبيق. تأكد من تحديث Microsoft Edge وWebView2.\n\n"
            f"التفاصيل: {exc}",
            error=True,
        )
        return 3
    finally:
        server.should_exit = True
        server_thread.join(timeout=5)
        if mutex and sys.platform == "win32":
            ctypes.windll.kernel32.CloseHandle(mutex)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
