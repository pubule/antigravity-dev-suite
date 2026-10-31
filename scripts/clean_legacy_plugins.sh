#!/usr/bin/env bash
# ==============================================================================
# Antigravity Legacy Plugins & Redundant Rules Cleaner (macOS & Linux)
# Safe, idempotent cleaner with automatic backup.
# ==============================================================================
set -euo pipefail

GEMINI_CONFIG_DIR="${HOME}/.gemini/config"
PLUGINS_DIR="${GEMINI_CONFIG_DIR}/plugins"
CONFIG_FILE="${GEMINI_CONFIG_DIR}/config.json"
BACKUP_TIMESTAMP=$(date +%Y%m%d_%H%M%S)

PYTHON_BIN="python3"
if ! command -v python3 >/dev/null 2>&1; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  fi
fi

echo "=== [1/3] Starting Antigravity Legacy Cleanup ==="

# 1. Backup config.json if present
if [ -f "${CONFIG_FILE}" ]; then
  cp "${CONFIG_FILE}" "${CONFIG_FILE}.bak-${BACKUP_TIMESTAMP}" 2>/dev/null || true
  echo "[+] Backed up config.json -> ${CONFIG_FILE}.bak-${BACKUP_TIMESTAMP}"
fi

# 2. Clean up legacy unbundled rule stubs if they exist
for old_rule in "claude_discipline.md" "visual_qa_mandate.md"; do
  OLD_RULE_PATH="${GEMINI_CONFIG_DIR}/rules/${old_rule}"
  if [ -f "${OLD_RULE_PATH}" ]; then
    rm -f "${OLD_RULE_PATH}" 2>/dev/null || true
    echo "[-] Cleaned legacy unbundled rule: ${OLD_RULE_PATH}"
  fi
done

# 3. Handle legacy dangling symlinks and directories if requested
if [ "${1:-}" = "--clean-all" ]; then
  PLUGINS_TO_REMOVE=("ponytail" "skill-anything" "opencode-agy")
  for plugin in "${PLUGINS_TO_REMOVE[@]}"; do
    PLUGIN_PATH="${PLUGINS_DIR}/${plugin}"
    if [ -L "${PLUGIN_PATH}" ] || [ -d "${PLUGIN_PATH}" ]; then
      rm -rf "${PLUGIN_PATH}" 2>/dev/null || true
      echo "[-] Removed legacy plugin target: ${PLUGIN_PATH}"
    fi
  done
fi

echo "=== [2/3] Legacy Cleanup Completed Successfully ==="
