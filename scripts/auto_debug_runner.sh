#!/usr/bin/env bash
# ==============================================================================
# Antigravity Auto-Debug Hook Runner (PostToolUse Protocol Shell Wrapper)
# ==============================================================================
set -euo pipefail

# Guarantee valid JSON {} on stdout upon exit under all conditions
trap 'echo "{}"' EXIT

# Feature Flag check
if [ "${AGY_AUTO_DEBUG:-1}" = "0" ] || [ "${AGY_AUTO_DEBUG:-true}" = "false" ] || [ "${AGY_AUTO_DEBUG:-on}" = "off" ]; then
  exit 0
fi

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="python3"
if ! command -v python3 >/dev/null 2>&1; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    exit 0
  fi
fi

# Pass stdin through to Python runner
"${PYTHON_BIN}" "${SCRIPTS_DIR}/auto_debug_runner.py" "${@}" || true
