"""نظام تسجيل مركزي يعمل بأمان حتى عند منع الكتابة داخل مجلد المشروع."""
from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

from backend.core.config import LOGS_DIR

_file_handler: Optional[logging.Handler] = None
_console_handler: Optional[logging.Handler] = None


def _build_file_handler() -> logging.Handler:
    """إنشاء ملف سجل مع انتقال تلقائي لمجلد مؤقت عند فشل الصلاحيات."""
    requested = os.getenv("APP_LOG_FILE", "").strip()
    candidates = []
    if requested:
        candidates.append(Path(requested).expanduser())
    candidates.extend([
        LOGS_DIR / "app.log",
        Path(tempfile.gettempdir()) / "voice-ai-studio" / "app.log",
    ])

    for log_file in candidates:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(str(log_file), encoding="utf-8")
            handler.setLevel(logging.DEBUG)
            handler.setFormatter(logging.Formatter(
                "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
            ))
            return handler
        except OSError:
            continue

    return logging.NullHandler()


def _init_handlers() -> None:
    global _file_handler, _console_handler
    if _file_handler is None:
        _file_handler = _build_file_handler()
    if _console_handler is None:
        _console_handler = logging.StreamHandler(sys.stdout)
        _console_handler.setLevel(logging.INFO)
        _console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))


def get_logger(name: str = "app") -> logging.Logger:
    """الحصول على logger بدون تكرار المعالجات."""
    _init_handlers()
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    if not logger.handlers:
        logger.addHandler(_file_handler)
        logger.addHandler(_console_handler)
    return logger
