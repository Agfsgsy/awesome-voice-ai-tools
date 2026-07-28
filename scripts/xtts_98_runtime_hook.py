"""PyInstaller runtime hook for the additive XTTS 98-percent finalization repair.

The hook runs before desktop_app/main. It deliberately does not import main.py and
therefore cannot replace or alter the user's preserved interface. Loading the base
submodules first also supports local projects whose backend.api/__init__.py does not
explicitly export these modules.
"""
from __future__ import annotations

import importlib
import logging

logger = logging.getLogger("xtts_98_runtime_hook")

MODULES = (
    "backend.api.voice_clone_repair_runtime",
    "backend.api.voice_clone_routes",
    "backend.api.voice_clone_xtts_runtime",
    "backend.api.voice_clone_download_resume_patch",
    "backend.api.voice_clone_download_source_fix",
    "backend.api.voice_clone_98_finalize_patch",
    "backend.api.voice_clone_auto_finalize_patch",
    "backend.api.voice_clone_fast_runtime_patch",
)

for module_name in MODULES:
    try:
        importlib.import_module(module_name)
    except Exception as exc:
        # Do not prevent the complete Studio from opening. Voice Clone status will
        # expose the concrete setup/runtime error to the user instead.
        logger.exception("Unable to activate %s: %s", module_name, exc)
        break
