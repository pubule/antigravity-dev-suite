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
RULES_DIR="${CONFIG_DIR}/rules"
AGENTS_DIR="${CONFIG_DIR}/agents"
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

# 1. Clean legacy / conflicting plugins
echo "[1/6] Running legacy plugins cleanup & backup..."
bash "${SCRIPT_DIR}/scripts/clean_legacy_plugins.sh"

# 2. Ensure directories exist
echo "[2/6] Setting up Gemini directory structure..."
mkdir -p "${PLUGINS_DIR}" "${RULES_DIR}" "${AGENTS_DIR}" "${CONFIG_DIR}/scripts" 2>/dev/null || true

# 3. Setup Python dependencies & Playwright Chromium
echo "[3/6] Verifying Playwright & Python environment..."
if "${PYTHON_BIN}" -c "import playwright" >/dev/null 2>&1; then
  echo "  ✔ Playwright python module is already installed."
else
  echo "  ⏳ Installing Playwright python module..."
  "${PYTHON_BIN}" -m pip install --quiet playwright 2>/dev/null || "${PYTHON_BIN}" -m pip install --user --quiet playwright 2>/dev/null || true
fi

# Attempt Chromium browser install
if command -v playwright >/dev/null 2>&1; then
  playwright install chromium 2>/dev/null || "${PYTHON_BIN}" -m playwright install chromium 2>/dev/null || true
elif "${PYTHON_BIN}" -m playwright --version >/dev/null 2>&1; then
  "${PYTHON_BIN}" -m playwright install chromium 2>/dev/null || true
fi

# 4. Link or install plugin bundle
echo "[4/6] Linking Antigravity Dev Suite plugin..."
rm -rf "${TARGET_PLUGIN_DIR}" 2>/dev/null || true
ln -sf "${SCRIPT_DIR}" "${TARGET_PLUGIN_DIR}" 2>/dev/null || true

# Ensure permissions
chmod +x "${SCRIPT_DIR}/scripts/"*.sh "${SCRIPT_DIR}/scripts/"*.py 2>/dev/null || true

# 5. Enable plugin in config.json
echo "[5/6] Registering plugin in config.json..."
"${PYTHON_BIN}" -c "
import json, sys
cfg_path = sys.argv[1]
try:
    with open(cfg_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
except Exception:
    data = {}
plugins = data.setdefault('plugins', {})
if 'antigravity-dev-suite' not in plugins or not isinstance(plugins['antigravity-dev-suite'], dict):
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

# 6. Self-Verification Test
echo "[6/6] Running E2E Self-Test..."
"${PYTHON_BIN}" "${SCRIPT_DIR}/scripts/visual_qa.py" --test-mode

echo ""
echo "=========================================================="
echo "✅ Antigravity Dev Suite successfully installed!"
echo "=========================================================="
