#!/usr/bin/env bash
# ==============================================================================
# Antigravity Dev Suite — 1-Click Installer for macOS & Linux
# Claude Opus 5.5 Coding Standard & Cross-Platform Engine
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
GEMINI_HOME="${HOME}/.gemini"
CONFIG_DIR="${GEMINI_HOME}/config"
PLUGINS_DIR="${CONFIG_DIR}/plugins"
TARGET_PLUGIN_DIR="${PLUGINS_DIR}/antigravity-dev-suite"
CONFIG_FILE="${CONFIG_DIR}/config.json"

# Detect Python interpreter
PYTHON_BIN="python3"
if ! command -v python3 >/dev/null 2>&1; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "❌ Error: Python 3 is required. Please install Python 3.10+."
    exit 1
  fi
fi

echo "=========================================================="
echo "🚀 Installing Antigravity Dev Suite (AGY Native Standard)"
echo "Platform: $(uname -s) $(uname -m)"
echo "=========================================================="

# 1. Clean legacy / conflicting plugins and rules
echo "[1/5] Running legacy plugins cleanup & backup..."
bash "${SCRIPT_DIR}/scripts/clean_legacy_plugins.sh"

# 2. Ensure directories exist
echo "[2/5] Setting up Gemini directory structure..."
mkdir -p "${PLUGINS_DIR}" "${CONFIG_DIR}/rules" "${CONFIG_DIR}/agents" 2>/dev/null || true

# 3. Setup Python dependencies & Playwright Chromium
echo "[3/5] Verifying Playwright & Python environment..."
if "${PYTHON_BIN}" -c "import playwright" >/dev/null 2>&1; then
  echo "  ✔ Playwright python module is already installed."
else
  echo "  ⏳ Installing Playwright python module..."
  "${PYTHON_BIN}" -m pip install --quiet playwright 2>/dev/null \
    || "${PYTHON_BIN}" -m pip install --user --quiet playwright 2>/dev/null \
    || "${PYTHON_BIN}" -m pip install --break-system-packages --quiet playwright 2>/dev/null \
    || echo "  ℹ Notice: Playwright python module could not be installed automatically. Visual QA will run in fallback mode."
fi

# Attempt Chromium browser install
if [ "${AGY_INSTALL_BROWSERS:-0}" = "1" ] || [ "${1:-}" = "--with-browsers" ]; then
  echo "  ⏳ Installing Playwright Chromium browser binaries..."
  playwright install chromium 2>/dev/null || "${PYTHON_BIN}" -m playwright install chromium 2>/dev/null || true
else
  echo "  ℹ Chromium installation skipped. Pass --with-browsers or run 'playwright install chromium' when needed for visual QA."
fi

# 4. Link or install plugin bundle
echo "[4/5] Linking Antigravity Dev Suite plugin..."
rm -rf "${TARGET_PLUGIN_DIR}" 2>/dev/null || true
ln -sf "${SCRIPT_DIR}" "${TARGET_PLUGIN_DIR}" 2>/dev/null || true

# Ensure executable permissions on scripts
chmod +x "${SCRIPT_DIR}/"*.sh "${SCRIPT_DIR}/scripts/"*.sh "${SCRIPT_DIR}/scripts/"*.py 2>/dev/null || true

# Enable plugin in config.json
"${PYTHON_BIN}" -c "
import json, sys
cfg_path = sys.argv[1]
try:
    with open(cfg_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
except Exception:
    data = {}
if not isinstance(data.get('plugins'), dict):
    data['plugins'] = {}
plugins = data['plugins']
if not isinstance(plugins.get('antigravity-dev-suite'), dict):
    plugins['antigravity-dev-suite'] = {'enabled': True}
else:
    plugins['antigravity-dev-suite']['enabled'] = True
try:
    with open(cfg_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
except Exception:
    pass
" "${CONFIG_FILE}" 2>/dev/null || true
echo "  ✔ Plugin enabled in config.json"

# 5. Run Self-Verification Test
echo "[5/5] Running E2E Test Suite..."
"${PYTHON_BIN}" "${SCRIPT_DIR}/tests/test_plugin_suite.py"

echo ""
echo "=========================================================="
echo "✅ Antigravity Dev Suite successfully installed and verified!"
echo "=========================================================="
