#!/usr/bin/env bash
# ==============================================================================
# Antigravity Legacy Plugins & Redundant Rules Cleaner
# ==============================================================================
set -euo pipefail

GEMINI_CONFIG_DIR="${HOME}/.gemini/config"
PLUGINS_DIR="${GEMINI_CONFIG_DIR}/plugins"
CONFIG_FILE="${GEMINI_CONFIG_DIR}/config.json"
BACKUP_TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "=== [1/3] Starting Antigravity Legacy Cleanup ==="

# 1. Backup config.json if present
if [ -f "${CONFIG_FILE}" ]; then
  cp "${CONFIG_FILE}" "${CONFIG_FILE}.bak-${BACKUP_TIMESTAMP}"
  echo "[+] Backed up config.json -> ${CONFIG_FILE}.bak-${BACKUP_TIMESTAMP}"
fi

# 2. Disable conflicting/redundant plugins in config.json
if [ -f "${CONFIG_FILE}" ] && command -v jq >/dev/null 2>&1; then
  # Disable ponytail, superpowers, skill-anything, opencode-agy
  TMP_CONFIG=$(mktemp)
  jq '
    .plugins["ponytail"].enabled = false |
    .plugins["superpowers"].enabled = false |
    .plugins["skill-anything"].enabled = false |
    .plugins["opencode-agy"].enabled = false
  ' "${CONFIG_FILE}" > "${TMP_CONFIG}" && mv "${TMP_CONFIG}" "${CONFIG_FILE}"
  echo "[+] Disabled conflicting plugins (ponytail, superpowers, skill-anything, opencode-agy) in config.json"
fi

# 3. Clean up conflicting plugin symlinks/directories
PLUGINS_TO_REMOVE=("ponytail" "skill-anything" "opencode-agy")
for plugin in "${PLUGINS_TO_REMOVE[@]}"; do
  PLUGIN_PATH="${PLUGINS_DIR}/${plugin}"
  if [ -L "${PLUGIN_PATH}" ] || [ -d "${PLUGIN_PATH}" ]; then
    rm -rf "${PLUGIN_PATH}"
    echo "[-] Removed plugin link/dir: ${PLUGIN_PATH}"
  fi
done

# 4. Clean up legacy disabled superpowers if present
if [ -d "${HOME}/.gemini/plugins_disabled/superpowers" ]; then
  rm -rf "${HOME}/.gemini/plugins_disabled/superpowers"
  echo "[-] Removed legacy disabled superpowers directory"
fi

echo "=== [2/3] Legacy Cleanup Completed Successfully ==="
