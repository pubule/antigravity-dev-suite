#!/usr/bin/env bash
# ==============================================================================
# Antigravity Dev Suite — Uninstaller & Rollback
# ==============================================================================
set -euo pipefail

GEMINI_HOME="${HOME}/.gemini"
CONFIG_DIR="${GEMINI_HOME}/config"
PLUGINS_DIR="${CONFIG_DIR}/plugins"
TARGET_PLUGIN_DIR="${PLUGINS_DIR}/antigravity-dev-suite"

echo "=== Uninstalling Antigravity Dev Suite ==="

# 1. Remove plugin link
if [ -L "${TARGET_PLUGIN_DIR}" ] || [ -d "${TARGET_PLUGIN_DIR}" ]; then
  rm -rf "${TARGET_PLUGIN_DIR}"
  echo "[-] Removed plugin link: ${TARGET_PLUGIN_DIR}"
fi

# 2. Remove global rules copies if any
rm -f "${CONFIG_DIR}/rules/claude_discipline.md" "${CONFIG_DIR}/rules/visual_qa_mandate.md" "${CONFIG_DIR}/rules/AGENTS.md"

# 3. Remove global agents copies if any
rm -f "${CONFIG_DIR}/agents/claude-critic.json" "${CONFIG_DIR}/agents/visual-qa-critic.json"
rm -f "${CONFIG_DIR}/agents/claude-critic.md" "${CONFIG_DIR}/agents/visual-qa-critic.md"

# 4. Remove hooks & scripts
rm -f "${CONFIG_DIR}/hooks.json"
rm -f "${CONFIG_DIR}/scripts/visual_qa.py" "${CONFIG_DIR}/scripts/auto_debug_runner.sh" "${CONFIG_DIR}/scripts/critic_loop.py" "${CONFIG_DIR}/scripts/clean_legacy_plugins.sh"

echo "=== Antigravity Dev Suite uninstalled successfully. ==="
