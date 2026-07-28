"""Patch an existing VoiceAIStudio.spec without replacing any of its other settings."""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

SPEC = Path(sys.argv[1] if len(sys.argv) > 1 else "VoiceAIStudio.spec").resolve()
source = SPEC.read_text(encoding="utf-8")
original = source

hook_expr = 'str(project_root / "scripts" / "xtts_98_runtime_hook.py")'
module_names = [
    "backend.api.voice_clone_repair_runtime",
    "backend.api.voice_clone_routes",
    "backend.api.voice_clone_xtts_runtime",
    "backend.api.voice_clone_download_resume_patch",
    "backend.api.voice_clone_download_source_fix",
    "backend.api.voice_clone_98_finalize_patch",
    "backend.api.voice_clone_auto_finalize_patch",
    "backend.api.voice_clone_fast_runtime_patch",
]

# Preserve every existing hidden import and append only missing XTTS modules.
missing_modules = [name for name in module_names if f'"{name}"' not in source and f"'{name}'" not in source]
if missing_modules:
    block = "\nhiddenimports += [\n" + "".join(f'    "{name}",\n' for name in missing_modules) + "]\n"
    analysis_pos = source.find("\na = Analysis(")
    if analysis_pos < 0:
        analysis_pos = source.find("\nAnalysis(")
    if analysis_pos < 0:
        raise SystemExit("Could not find Analysis(...) in VoiceAIStudio.spec")
    source = source[:analysis_pos] + block + source[analysis_pos:]

# Replace only the runtime_hooks argument. Keep all existing hooks and add ours.
match = re.search(r"(?m)^(\s*)runtime_hooks\s*=\s*\[(.*?)\]\s*,", source, flags=re.S)
if not match:
    raise SystemExit("Could not find runtime_hooks=[...] in VoiceAIStudio.spec")
indent, body = match.group(1), match.group(2).strip()
if hook_expr not in body:
    new_body = body
    if new_body:
        new_body = new_body.rstrip() + ",\n" + indent + "    " + hook_expr
    else:
        new_body = "\n" + indent + "    " + hook_expr + "\n" + indent
    replacement = f"{indent}runtime_hooks=[{new_body}],"
    source = source[: match.start()] + replacement + source[match.end() :]

if source == original:
    print("SPEC_XTTS_RUNTIME_HOOK_ALREADY_PRESENT")
else:
    # A .spec file is executable Python. Parsing catches malformed edits before build.
    ast.parse(source, filename=str(SPEC))
    SPEC.write_text(source, encoding="utf-8")
    print("SPEC_XTTS_RUNTIME_HOOK_PATCHED")

# Final contractual checks.
final = SPEC.read_text(encoding="utf-8")
if hook_expr not in final:
    raise SystemExit("XTTS runtime hook was not added to VoiceAIStudio.spec")
for name in module_names:
    if name not in final:
        raise SystemExit(f"Missing XTTS hidden import: {name}")
