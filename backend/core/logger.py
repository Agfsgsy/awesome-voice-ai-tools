"""Structured Logging System - Production Ready"""
import logging
import logging.handlers
import sys
import json
import traceback
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from contextvars import ContextVar

from backend.core.config import settings

# Context variable for request tracking
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add request ID if available
        request_id = request_id_var.get("")
        if request_id:
            log_entry["request_id"] = request_id
        
        # Add exception info
        if record.exc_info:
            log_entry["exception"] = traceback.format_exception(*record.exc_info)
        
        # Add extra fields
        for key in ["engine", "plugin", "model", "duration_ms", "user", "ip", "status_code"]:
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)
        
        return json.dumps(log_entry, ensure_ascii=False, default=str)


class ColoredFormatter(logging.Formatter):
    """Colored console formatter"""
    
    COLORS = {
        "DEBUG": "\033[36m",      # Cyan
        "INFO": "\033[32m",       # Green
        "WARNING": "\033[33m",    # Yellow
        "ERROR": "\033[31m",      # Red
        "CRITICAL": "\033[35m",   # Magenta
        "RESET": "\033[0m",
    }
    
    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
        reset = self.COLORS["RESET"]
        record.levelname = f"{color}{record.levelname}{reset}"
        return super().format(record)


class LogManager:
    """Central log manager with file rotation and structured output"""
    
    def __init__(self):
        self.logs_dir = settings.LOGS_DIR
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        self._app_log = self.logs_dir / "app.log"
        self._error_log = self.logs_dir / "error.log"
        self._json_log = self.logs_dir / "app.json.log"
        self._initialized = False
    
    def _init(self):
        if self._initialized:
            return
        
        # Create formatters
        detailed_fmt = "%(asctime)s | %(request_id)s | %(name)s | %(levelname)s | %(message)s"
        simple_fmt = "%(levelname)s: %(message)s"
        
        # Root logger configuration
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        
        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # File handler with rotation (app.log)
        app_handler = logging.handlers.RotatingFileHandler(
            str(self._app_log), maxBytes=10*1024*1024, backupCount=10,
            encoding="utf-8"
        )
        app_handler.setLevel(logging.DEBUG)
        app_handler.setFormatter(logging.Formatter(detailed_fmt))
        root_logger.addHandler(app_handler)
        
        # Error file handler with rotation
        error_handler = logging.handlers.RotatingFileHandler(
            str(self._error_log), maxBytes=5*1024*1024, backupCount=5,
            encoding="utf-8"
        )
        error_handler.setLevel(logging.WARNING)
        error_handler.setFormatter(logging.Formatter(detailed_fmt))
        root_logger.addHandler(error_handler)
        
        # JSON structured log
        json_handler = logging.handlers.RotatingFileHandler(
            str(self._json_log), maxBytes=10*1024*1024, backupCount=5,
            encoding="utf-8"
        )
        json_handler.setLevel(logging.INFO)
        json_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(json_handler)
        
        # Console handler with colors
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG if settings.APP_DEBUG else logging.INFO)
        console_handler.setFormatter(ColoredFormatter(simple_fmt))
        root_logger.addHandler(console_handler)
        
        self._initialized = True
    
    def get_logger(self, name: str) -> logging.Logger:
        """Get a logger with the specified name"""
        self._init()
        logger = logging.getLogger(name)
        return logger
    
    def set_request_id(self, request_id: str):
        """Set the current request ID for context tracking"""
        request_id_var.set(request_id)
    
    def get_recent_logs(self, lines: int = 200, level: Optional[str] = None) -> list:
        """Get recent log lines"""
        if not self._app_log.exists():
            return []
        try:
            all_lines = self._app_log.read_text(encoding="utf-8", errors="replace").splitlines()
            if level:
                all_lines = [l for l in all_lines if f" | {level.upper()} | " in l]
            return all_lines[-lines:]
        except Exception:
            return []
    
    def clear_logs(self):
        """Clear all log files"""
        for log_file in [self._app_log, self._error_log, self._json_log]:
            if log_file.exists():
                log_file.write_text("")


# Global log manager
_log_manager = LogManager()


def get_logger(name: str = "app") -> logging.Logger:
    """Get a logger instance"""
    return _log_manager.get_logger(name)


def set_request_id(request_id: str):
    """Set request ID for context tracking"""
    _log_manager.set_request_id(request_id)


def get_recent_logs(lines: int = 200, level: Optional[str] = None) -> list:
    """Get recent log lines"""
    return _log_manager.get_recent_logs(lines, level)


def clear_logs():
    """Clear all log files"""
    _log_manager.clear_logs()


# Legacy compatibility
LOG_FILE = settings.LOGS_DIR / "app.log"
