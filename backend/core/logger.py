"""نظام التسجيل المركزي"""
import logging
import sys
from pathlib import Path

from backend.core.config import LOGS_DIR

LOG_FILE = LOGS_DIR / "app.log"

_file_handler = None
_console_handler = None

def _init_handlers():
    global _file_handler, _console_handler
    if _file_handler is None:
        _file_handler = logging.FileHandler(str(LOG_FILE), encoding='utf-8')
        _file_handler.setLevel(logging.DEBUG)
        _file_handler.setFormatter(logging.Formatter('%(asctime)s | %(name)s | %(levelname)s | %(message)s'))
    if _console_handler is None:
        _console_handler = logging.StreamHandler(sys.stdout)
        _console_handler.setLevel(logging.INFO)
        _console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))


def get_logger(name: str = "app") -> logging.Logger:
    """الحصول على logger"""
    _init_handlers()
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        logger.addHandler(_file_handler)
        logger.addHandler(_console_handler)
    return logger
