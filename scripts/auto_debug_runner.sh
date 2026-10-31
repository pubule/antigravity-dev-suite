#!/usr/bin/env bash
# ==============================================================================
# Antigravity Auto-Debug & Visual QA Hook Runner (PostToolUse Protocol Compliant)
# ==============================================================================
set -euo pipefail

# Ensure valid JSON {} on stdout upon exit under all conditions
trap 'echo "{}"' EXIT

# 1. Feature Flag check
if [ "${AGY_AUTO_DEBUG:-1}" = "0" ] || [ "${AGY_AUTO_DEBUG:-true}" = "false" ] || [ "${AGY_AUTO_DEBUG:-on}" = "off" ]; then
  exit 0
fi

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${TMPDIR:-/tmp}/agy_visual_qa"

# 2. Read stdin JSON payload safely
PAYLOAD=$(cat || true)

# 3. Extract changed file path from toolCall.args (handling Path, path, FilePath, or $1 fallback)
CHANGED_FILE=$(python3 -c "
import sys, json

payload_str = '''$PAYLOAD'''
file_path = ''
try:
    if payload_str.strip():
        data = json.loads(payload_str)
        args = data.get('toolCall', {}).get('args', {})
        file_path = args.get('Path') or args.get('path') or args.get('FilePath') or args.get('file_path') or ''
except Exception:
    pass

if not file_path and len(sys.argv) > 1:
    file_path = sys.argv[1]

print(file_path)
" "${1:-}" 2>/dev/null || echo "")

# 4. Trigger actions on modified files
if [ -n "${CHANGED_FILE}" ] && [ -f "${CHANGED_FILE}" ]; then
  # Visual QA check on frontend assets
  if [[ "${CHANGED_FILE}" =~ \.(html|htm|svg|css|jsx|tsx|vue|svelte)$ ]]; then
    python3 "${SCRIPTS_DIR}/visual_qa.py" "${CHANGED_FILE}" --output-dir "${OUTPUT_DIR}" >/dev/null 2>&1 || true
  fi
fi

exit 0
