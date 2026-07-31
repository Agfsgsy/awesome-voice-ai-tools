#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"
if [[ ! -x .venv/bin/python ]]; then
  python3 scripts/setup_mobile_backend.py
fi
exec .venv/bin/python scripts/run_mobile_backend.py "$@"
