#!/usr/bin/env bash
# ==============================================================================
# Antigravity Dev Suite — Uninstaller & Rollback
# ==============================================================================
set -euo pipefail

GEMINI_HOME="${HOME}/.gemini"
CONFIG_DIR="${GEMINI_HOME}/config"
PLUGINS_DIR="${CONFIG_DIR}/plugins"
TARGET_PLUGIN_DIR="${PLUGINS_DIR}/antigravity-dev-suite"
CONFIG_FILE="${CONFIG_DIR}/config.json"

echo "=== Uninstalling Antigravity Dev Suite ==="

# 1. Remove plugin link
if [ -L "${TARGET_PLUGIN_DIR}" ] || [ -d "${TARGET_PLUGIN_DIR}" ]; then
  rm -rf "${TARGET_PLUGIN_DIR}"
  echo "[-] Removed plugin link: ${TARGET_PLUGIN_DIR}"
fi

# 2. Disable plugin in config.json
if [ -f "${CONFIG_FILE}" ]; then
  python3 -c "
import json, sys
cfg_path = sys.argv[1]
try:
    with open(cfg_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data.get('plugins'), dict) and isinstance(data['plugins'].get('antigravity-dev-suite'), dict):
        data['plugins']['antigravity-dev-suite']['enabled'] = False
    with open(cfg_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
except Exception:
    pass
" "${CONFIG_FILE}" 2>/dev/null || true
  echo "[-] Disabled plugin in config.json"
fi

# 3. Clean legacy rule stubs if any
rm -f "${CONFIG_DIR}/rules/claude_discipline.md" "${CONFIG_DIR}/rules/visual_qa_mandate.md"

echo "=== Antigravity Dev Suite uninstalled successfully. ==="
