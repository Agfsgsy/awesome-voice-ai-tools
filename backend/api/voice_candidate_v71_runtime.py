"""Activate reference-aware candidate scoring after all cloning routes are loaded."""
from __future__ import annotations

import backend.api.voice_engine_suite_routes as suite
from backend.core.voice_candidate_precision import score_candidate_against_profile

suite._candidate_quality = score_candidate_against_profile
