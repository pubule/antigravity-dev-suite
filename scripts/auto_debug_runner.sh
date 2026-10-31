#!/usr/bin/env bash
# ==============================================================================
# Antigravity Auto-Debug & Visual QA Hook Runner
# ==============================================================================
set -o pipefail

# 1. Feature Flag check
if [ "${AGY_AUTO_DEBUG:-1}" = "0" ] || [ "${AGY_AUTO_DEBUG:-true}" = "false" ] || [ "${AGY_AUTO_DEBUG:-on}" = "off" ]; then
  exit 0
fi

CHANGED_FILE="${1:-}"
OUTPUT_DIR="${TMPDIR:-/tmp}/agy_visual_qa"
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 2. Check if a visual/frontend artifact was modified
if [[ "${CHANGED_FILE}" =~ \.(html|htm|svg|css|jsx|tsx|vue|svelte)$ ]]; then
  if [ -f "${CHANGED_FILE}" ]; then
    python3 "${SCRIPTS_DIR}/visual_qa.py" "${CHANGED_FILE}" --output-dir "${OUTPUT_DIR}" || true
  fi
fi

# 3. Smart Project Test Runner Discovery (if triggered)
find_repo_root() {
  local dir="${1:-$(pwd)}"
  while [ "${dir}" != "/" ]; do
    if [ -f "${dir}/package.json" ] || [ -f "${dir}/pyproject.toml" ] || [ -f "${dir}/Cargo.toml" ] || [ -f "${dir}/pom.xml" ] || [ -f "${dir}/build.gradle" ]; then
      echo "${dir}"
      return 0
    fi
    dir="$(dirname "${dir}")"
  done
  echo "$(pwd)"
}

REPO_ROOT=$(find_repo_root "$(dirname "${CHANGED_FILE:-$(pwd)}")")

# Run project typecheck / lint if config exists in REPO_ROOT (non-blocking notification)
if [ -f "${REPO_ROOT}/package.json" ]; then
  if grep -q '"test"' "${REPO_ROOT}/package.json" 2>/dev/null; then
    # If npm test exists and is fast, run in check mode
    echo "[Antigravity Auto-Debug] Monitored Node project at ${REPO_ROOT}"
  fi
elif [ -f "${REPO_ROOT}/pyproject.toml" ] || [ -f "${REPO_ROOT}/pytest.ini" ]; then
  echo "[Antigravity Auto-Debug] Monitored Python project at ${REPO_ROOT}"
fi

exit 0
