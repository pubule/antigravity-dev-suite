#!/usr/bin/env bash
# ==============================================================================
# Antigravity Legacy Plugins & Redundant Rules Cleaner (macOS & Linux)
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

# 2. Disable conflicting/redundant plugins in config.json via Python or jq
if [ -f "${CONFIG_FILE}" ]; then
  if command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    "${PYTHON_BIN}" -c "
import json, sys
cfg_path = sys.argv[1]
try:
    with open(cfg_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
except Exception:
    data = {}
plugins = data.setdefault('plugins', {})
for legacy in ['ponytail', 'superpowers', 'skill-anything', 'opencode-agy']:
    if legacy in plugins:
        if isinstance(plugins[legacy], dict):
            plugins[legacy]['enabled'] = False
        else:
            plugins[legacy] = {'enabled': False}
try:
    with open(cfg_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
except Exception:
    pass
" "${CONFIG_FILE}" 2>/dev/null || true
    echo "[+] Disabled conflicting plugins (ponytail, superpowers, skill-anything, opencode-agy) in config.json"
  elif command -v jq >/dev/null 2>&1; then
    TMP_CONFIG=$(mktemp)
    (jq '
      .plugins["ponytail"].enabled = false |
      .plugins["superpowers"].enabled = false |
      .plugins["skill-anything"].enabled = false |
      .plugins["opencode-agy"].enabled = false
    ' "${CONFIG_FILE}" > "${TMP_CONFIG}" && mv "${TMP_CONFIG}" "${CONFIG_FILE}") 2>/dev/null || true
    echo "[+] Disabled conflicting plugins via jq in config.json"
  fi
fi

# 3. Clean up conflicting plugin symlinks/directories
PLUGINS_TO_REMOVE=("ponytail" "skill-anything" "opencode-agy")
for plugin in "${PLUGINS_TO_REMOVE[@]}"; do
  PLUGIN_PATH="${PLUGINS_DIR}/${plugin}"
  if [ -L "${PLUGIN_PATH}" ] || [ -d "${PLUGIN_PATH}" ]; then
    rm -rf "${PLUGIN_PATH}" 2>/dev/null || true
    echo "[-] Removed plugin link/dir: ${PLUGIN_PATH}"
  fi
done

# 4. Clean up legacy disabled superpowers if present
if [ -d "${HOME}/.gemini/plugins_disabled/superpowers" ]; then
  rm -rf "${HOME}/.gemini/plugins_disabled/superpowers" 2>/dev/null || true
  echo "[-] Removed legacy disabled superpowers directory"
fi

echo "=== [2/3] Legacy Cleanup Completed Successfully ==="
