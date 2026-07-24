"""نظام التسجيل المركزي"""
import logging
from logging.handlers import RotatingFileHandler
import sys
from pathlib import Path

from backend.core.config import LOGS_DIR

LOG_FILE = LOGS_DIR / "app.log"

_file_handler = None
_console_handler = None
_handlers_initialized = False

def _init_handlers():
    global _file_handler, _console_handler, _handlers_initialized
    if _handlers_initialized:
        return

    # Always create console handler
    if _console_handler is None:
        _console_handler = logging.StreamHandler(sys.stdout)
        _console_handler.setLevel(logging.INFO)
        _console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))

    # Attempt to create file handler gracefully
    if _file_handler is None:
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            _file_handler = RotatingFileHandler(
                str(LOG_FILE),
                maxBytes=5*1024*1024, # 5MB
                backupCount=2,
                encoding='utf-8',
                delay=False # Set delay=False to eagerly catch PermissionError on init instead of spaming stderr later
            )
            _file_handler.setLevel(logging.DEBUG)
            _file_handler.setFormatter(logging.Formatter('%(asctime)s | %(name)s | %(levelname)s | %(message)s'))
        except Exception as e:
            # Fallback to console only if file access fails (e.g. permissions, locked file)
            _file_handler = None
            print(f"WARNING: Logging to file failed ({e}). Falling back to console only.", file=sys.stderr)

    _handlers_initialized = True

def get_logger(name: str = "app") -> logging.Logger:
    """الحصول على logger"""
    try:
        _init_handlers()
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)

        # Prevent duplicate handlers
        if not logger.handlers:
            if _file_handler is not None:
                logger.addHandler(_file_handler)
            if _console_handler is not None:
                logger.addHandler(_console_handler)

        # Also prevent propagation to root logger which might double-log
        logger.propagate = False
        return logger
    except Exception as e:
        # Absolute fallback to prevent application crash
        fallback = logging.getLogger(name + "_fallback")
        if not fallback.handlers:
            ch = logging.StreamHandler(sys.stdout)
            fallback.addHandler(ch)
        return fallback
