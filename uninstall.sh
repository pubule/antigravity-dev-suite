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

# 2. Clean unbundled rules and agents if any
rm -f "${CONFIG_DIR}/rules/claude_discipline.md" "${CONFIG_DIR}/rules/visual_qa_mandate.md" "${CONFIG_DIR}/rules/AGENTS.md"
rm -f "${CONFIG_DIR}/agents/claude-critic.json" "${CONFIG_DIR}/agents/visual-qa-critic.json"
rm -f "${CONFIG_DIR}/agents/claude-critic.md" "${CONFIG_DIR}/agents/visual-qa-critic.md" "${CONFIG_DIR}/agents/opus-architect.md"

echo "=== Antigravity Dev Suite uninstalled successfully. ==="
