#!/usr/bin/env bash
# ==============================================================================
# Antigravity Dev Suite — 1-Click Installer for macOS & Linux
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GEMINI_HOME="${HOME}/.gemini"
CONFIG_DIR="${GEMINI_HOME}/config"
PLUGINS_DIR="${CONFIG_DIR}/plugins"
RULES_DIR="${CONFIG_DIR}/rules"
AGENTS_DIR="${CONFIG_DIR}/agents"
TARGET_PLUGIN_DIR="${PLUGINS_DIR}/antigravity-dev-suite"

echo "=========================================================="
echo "🚀 Installing Antigravity Dev Suite (AGY Native Standard)"
echo "=========================================================="

# 1. Clean legacy / conflicting plugins
echo "[1/6] Running legacy plugins cleanup & backup..."
bash "${SCRIPT_DIR}/scripts/clean_legacy_plugins.sh"

# 2. Ensure directories exist
echo "[2/6] Setting up Gemini directory structure..."
mkdir -p "${PLUGINS_DIR}" "${RULES_DIR}" "${AGENTS_DIR}" "${CONFIG_DIR}/scripts"

# 3. Setup Python dependencies & Playwright Chromium
echo "[3/6] Verifying Playwright & Python environment..."
if python3 -c "import playwright" >/dev/null 2>&1; then
  echo "  ✔ Playwright python module is already installed."
else
  echo "  ⏳ Installing Playwright python module..."
  pip3 install --quiet playwright || pip3 install --user --quiet playwright || true
fi

if command -v playwright >/dev/null 2>&1; then
  playwright install chromium 2>/dev/null || true
fi

# 4. Link or install plugin bundle
echo "[4/6] Linking Antigravity Dev Suite plugin..."
rm -rf "${TARGET_PLUGIN_DIR}"
ln -sf "${SCRIPT_DIR}" "${TARGET_PLUGIN_DIR}"

# Ensure permissions
chmod +x "${SCRIPT_DIR}/scripts/"*.sh "${SCRIPT_DIR}/scripts/"*.py 2>/dev/null || true

# 5. Enable plugin in config.json
echo "[5/6] Registering plugin in config.json..."
CONFIG_FILE="${CONFIG_DIR}/config.json"
if [ -f "${CONFIG_FILE}" ] && command -v jq >/dev/null 2>&1; then
  TMP_CONFIG=$(mktemp)
  jq '.plugins["antigravity-dev-suite"].enabled = true' "${CONFIG_FILE}" > "${TMP_CONFIG}" && mv "${TMP_CONFIG}" "${CONFIG_FILE}"
fi

# 6. Self-Verification Test
echo "[6/6] Running E2E Self-Test..."
python3 "${SCRIPT_DIR}/scripts/visual_qa.py" --test-mode

echo ""
echo "=========================================================="
echo "✅ Antigravity Dev Suite successfully installed!"
echo "=========================================================="
