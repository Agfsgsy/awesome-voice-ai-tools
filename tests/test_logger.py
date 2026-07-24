import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import logging

# Reset global handlers before each test to ensure fresh state
@pytest.fixture(autouse=True)
def reset_logger_state():
    import backend.core.logger as backend_logger
    backend_logger._handlers_initialized = False
    backend_logger._file_handler = None
    backend_logger._console_handler = None
    yield

def test_logger_normal_initialization():
    """Test logger initializes normally when permissions are fine."""
    from backend.core.logger import get_logger
    logger = get_logger("test_normal")
    assert logger.name == "test_normal"
    assert len(logger.handlers) > 0

@patch('backend.core.logger.RotatingFileHandler')
def test_logger_no_permissions(mock_rotating_handler):
    """Test logging fallback when LOGS_DIR/app.log throws a PermissionError."""
    # Simulate a PermissionError when trying to initialize RotatingFileHandler
    mock_rotating_handler.side_effect = PermissionError("[Errno 13] Permission denied")

    from backend.core.logger import get_logger
    logger = get_logger("test_permission")

    assert logger.name == "test_permission"
    # Ensure at least the console handler is attached
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], logging.StreamHandler)

@patch('backend.core.logger._init_handlers')
def test_get_logger_absolute_fallback(mock_init_handlers):
    """Test get_logger absolute fallback if _init_handlers completely crashes."""
    # Force _init_handlers to throw an unexpected error
    mock_init_handlers.side_effect = RuntimeError("Total disaster")

    from backend.core.logger import get_logger
    logger = get_logger("test_disaster")

    assert logger.name == "test_disaster_fallback"
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], logging.StreamHandler)
