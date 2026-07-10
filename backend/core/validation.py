"""Validation - التحقق من الملفات والطلبات"""

import os
import io
import mimetypes
import magic
from pathlib import Path
from typing import Optional, Tuple, List

from backend.core.config import MAX_UPLOAD_MB, SUPPORTED_AUDIO_FORMATS
from backend.core.logger import get_logger

logger = get_logger("validation")

# Allowed MIME types for audio files
ALLOWED_MIME_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/flac",
    "audio/x-flac",
    "audio/ogg",
    "audio/x-ogg",
    "audio/mp4",
    "audio/x-m4a",
    "audio/x-matroska",
    "application/octet-stream",  # Some files may report this
}

# File extension to expected MIME type mapping
EXT_TO_MIME = {
    ".wav": {"audio/wav", "audio/x-wav"},
    ".mp3": {"audio/mpeg", "audio/mp3"},
    ".flac": {"audio/flac", "audio/x-flac"},
    ".ogg": {"audio/ogg", "audio/x-ogg"},
    ".m4a": {"audio/mp4", "audio/x-m4a"},
}

# Magic bytes signatures for common audio formats
MAGIC_BYTES = {
    ".wav": [(b"RIFF", 0)],
    ".mp3": [(b"\xff\xfb", 0), (b"\xff\xf3", 0), (b"ID3", 0)],
    ".flac": [(b"fLaC", 0)],
    ".ogg": [(b"OggS", 0)],
    ".m4a": [(b"ftyp", 4)],  # QuickTime/MP4 container
}


def validate_file_extension(filename: str, allowed_extensions: Optional[List[str]] = None) -> Tuple[bool, str]:
    """Validate file extension"""
    if not filename or not isinstance(filename, str):
        return False, "Invalid filename"

    ext = Path(filename).suffix.lower()
    allowed = allowed_extensions or SUPPORTED_AUDIO_FORMATS

    if ext not in allowed:
        return False, f"File extension '{ext}' not allowed. Allowed: {', '.join(allowed)}"

    return True, ""


def validate_file_size(content: bytes, max_size_mb: Optional[int] = None) -> Tuple[bool, str]:
    """Validate file size"""
    if not content:
        return False, "Empty file"

    # If max_size_mb is explicitly 0, reject any non-empty file
    if max_size_mb is not None and max_size_mb <= 0:
        return False, f"File size limit is 0MB"

    max_size = (max_size_mb or MAX_UPLOAD_MB) * 1024 * 1024
    if len(content) > max_size:
        return False, f"File too large: {len(content) / (1024*1024):.1f}MB (max {max_size_mb or MAX_UPLOAD_MB}MB)"

    return True, ""


def validate_mime_type(content: bytes, expected_ext: Optional[str] = None) -> Tuple[bool, str, str]:
    """Validate file MIME type using python-magic"""
    try:
        detected = magic.from_buffer(content, mime=True)
    except Exception as e:
        logger.warning(f"MIME type detection failed: {e}")
        # Fallback: try mimetypes
        return True, "", "unknown"

    if detected not in ALLOWED_MIME_TYPES:
        # Check if it's a variation we accept
        if detected.startswith("audio/") or detected.startswith("video/"):
            return True, "", detected
        return False, f"File type '{detected}' not allowed", detected

    # Cross-check with expected extension if provided
    if expected_ext:
        expected_mimes = EXT_TO_MIME.get(expected_ext.lower(), set())
        if expected_mimes and detected not in expected_mimes:
            logger.warning(
                f"MIME type mismatch: expected {expected_mimes}, got {detected}"
            )
            # Allow but warn (some files may have variant MIME types)

    return True, "", detected


def validate_magic_bytes(content: bytes, expected_ext: Optional[str] = None) -> Tuple[bool, str]:
    """Validate file magic bytes signature"""
    if len(content) < 4:
        return False, "File too small to validate"

    if expected_ext:
        signatures = MAGIC_BYTES.get(expected_ext.lower(), [])
        if signatures:
            for sig, offset in signatures:
                if offset + len(sig) <= len(content):
                    if content[offset:offset + len(sig)] == sig:
                        return True, ""
            return False, f"File content does not match expected format: {expected_ext}"

    # Generic check: at least verify it looks like an audio file
    # Check all known signatures
    for ext, signatures in MAGIC_BYTES.items():
        for sig, offset in signatures:
            if offset + len(sig) <= len(content):
                if content[offset:offset + len(sig)] == sig:
                    return True, ""

    # If MIME type says it's audio, accept even without magic match
    return True, ""


def validate_filename_safety(filename: str) -> Tuple[bool, str]:
    """Validate filename is safe (no path traversal, no special chars)"""
    if not filename:
        return False, "Empty filename"

    # Check for path traversal attempts
    if ".." in filename or "/" in filename or "\\" in filename:
        return False, "Invalid filename: path traversal detected"

    # Check for null bytes
    if "\x00" in filename:
        return False, "Invalid filename: null byte detected"

    # Check filename length
    if len(filename) > 255:
        return False, "Filename too long (max 255 characters)"

    # Check for only safe characters
    safe_name = Path(filename).name
    if safe_name.startswith("."):
        return False, "Hidden files not allowed"

    return True, ""


def validate_uploaded_file(
    filename: str,
    content: bytes,
    allowed_extensions: Optional[List[str]] = None,
    max_size_mb: Optional[int] = None,
) -> Tuple[bool, str, dict]:
    """
    Full validation for uploaded files.
    Returns: (is_valid, error_message, info_dict)
    """
    info = {
        "filename": filename,
        "size_bytes": len(content),
        "mime_type": "unknown",
        "extension": Path(filename).suffix.lower() if filename else "",
    }

    # 1. Validate filename safety
    valid, error = validate_filename_safety(filename)
    if not valid:
        return False, error, info

    # 2. Validate extension
    valid, error = validate_file_extension(filename, allowed_extensions)
    if not valid:
        return False, error, info

    # 3. Validate size
    valid, error = validate_file_size(content, max_size_mb)
    if not valid:
        return False, error, info

    # 4. Validate MIME type
    ext = Path(filename).suffix.lower()
    valid, error, mime = validate_mime_type(content, ext)
    info["mime_type"] = mime
    if not valid:
        return False, error, info

    # 5. Validate magic bytes
    valid, error = validate_magic_bytes(content, ext)
    if not valid:
        return False, error, info

    return True, "", info


def validate_text_input(text: str, max_length: int = 10000, min_length: int = 1) -> Tuple[bool, str]:
    """Validate text input for TTS"""
    if not text:
        return False, "Text is required"

    if len(text) < min_length:
        return False, f"Text too short (min {min_length} character)"

    if len(text) > max_length:
        return False, f"Text too long (max {max_length} characters, got {len(text)})"

    # Check for null bytes
    if "\x00" in text:
        return False, "Invalid text: null byte detected"

    return True, ""


def sanitize_path(path_str: str, base_dir: Path) -> Optional[Path]:
    """
    Sanitize a path to prevent path traversal attacks.
    Returns resolved path within base_dir or None if invalid.
    """
    if not path_str:
        return None

    # Reject paths with null bytes
    if "\x00" in path_str:
        logger.warning("Path sanitization rejected: null byte detected")
        return None

    # Normalize the path
    try:
        # Join with base and resolve to absolute
        target = (base_dir / path_str).resolve()

        # Ensure the resolved path is within base_dir
        base_resolved = base_dir.resolve()

        # Check for path traversal
        try:
            target.relative_to(base_resolved)
        except ValueError:
            logger.warning(f"Path traversal attempt blocked: {path_str}")
            return None

        return target
    except Exception as e:
        logger.warning(f"Path sanitization failed for '{path_str}': {e}")
        return None


def validate_engine_name(engine: str, available_engines: List[str]) -> Tuple[bool, str]:
    """Validate TTS engine name"""
    if not engine:
        return False, "Engine name is required"

    if len(engine) > 50:
        return False, "Engine name too long"

    # Only allow alphanumeric, dash, underscore
    if not all(c.isalnum() or c in "_-" for c in engine):
        return False, "Invalid engine name format"

    return True, ""


def validate_voice_name(voice: str) -> Tuple[bool, str]:
    """Validate voice name"""
    if not voice:
        return False, "Voice name is required"

    if len(voice) > 100:
        return False, "Voice name too long"

    if "\x00" in voice or "/" in voice or "\\" in voice:
        return False, "Invalid voice name"

    return True, ""


def validate_language_code(language: str) -> Tuple[bool, str]:
    """Validate language code"""
    if not language:
        return False, "Language code is required"

    # ISO 639-1 codes are 2 letters
    if len(language) > 5:
        return False, "Invalid language code"

    if not all(c.isalpha() or c == "-" for c in language):
        return False, "Invalid language code format"

    return True, ""
