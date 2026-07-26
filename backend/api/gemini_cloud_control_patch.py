"""Final compatibility patch for legacy studio routes.

The old text-preparation route imported key functions before the stability runtimes loaded.
Point it to the strict verified pool and transient-safe recorder so a temporary 429 cannot
clear an active key.
"""
from backend.api import gemini_cloud_control_runtime, gemini_stability_runtime, studio_routes

studio_routes.ordered_keys = gemini_cloud_control_runtime.strict_ordered_keys
studio_routes.record_result = gemini_stability_runtime.stable_record_result
