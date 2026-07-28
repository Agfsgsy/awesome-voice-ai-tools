"""Add XTTS finalization imports to the existing local main.py without replacing it."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

MAIN = Path(sys.argv[1] if len(sys.argv) > 1 else "main.py").resolve()
source = MAIN.read_text(encoding="utf-8")
lines = source.splitlines()

aliases = {
    "_voice_clone_download_resume_patch",
    "_voice_clone_download_source_fix",
    "_voice_clone_98_finalize_patch",
    "_voice_clone_auto_finalize_patch",
    "_voice_clone_fast_runtime_patch",
}

kept: list[str] = []
for line in lines:
    if any(alias in line for alias in aliases):
        continue
    kept.append(line)

block = [
    "import backend.api.voice_clone_download_resume_patch as _voice_clone_download_resume_patch",
    "import backend.api.voice_clone_download_source_fix as _voice_clone_download_source_fix",
    "import backend.api.voice_clone_98_finalize_patch as _voice_clone_98_finalize_patch",
    "import backend.api.voice_clone_auto_finalize_patch as _voice_clone_auto_finalize_patch",
    "import backend.api.voice_clone_fast_runtime_patch as _voice_clone_fast_runtime_patch",
]

anchor_index = -1
for index, line in enumerate(kept):
    if "voice_clone_xtts_runtime import router as voice_clone_runtime_router" in line:
        anchor_index = index + 1
        break
if anchor_index < 0:
    for index, line in enumerate(kept):
        if "voice_clone_fast_routes import router as voice_clone_fast_router" in line:
            anchor_index = index + 1
            break
if anchor_index < 0:
    raise SystemExit("Could not find the Voice Clone import block in the existing main.py")

patched_lines = kept[:anchor_index] + block + kept[anchor_index:]
patched = "\n".join(patched_lines) + "\n"
ast.parse(patched, filename=str(MAIN))
MAIN.write_text(patched, encoding="utf-8")
print("PATCHED_EXISTING_MAIN_OK")
