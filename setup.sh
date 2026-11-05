#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Setup /dev SDLC Pipeline Suite ==="
echo ""

# 1. Check prerequisites
echo "[1/4] Checking prerequisites..."

if ! command -v git >/dev/null 2>&1; then
    echo "ERROR: 'git' is not installed or not in PATH." >&2
    exit 1
fi

if ! command -v node >/dev/null 2>&1; then
    echo "ERROR: 'node' is not installed or not in PATH. Required for hooks and Claude Code." >&2
    exit 1
fi

if ! command -v claude >/dev/null 2>&1; then
    echo "ERROR: 'claude' CLI is not installed or not in PATH." >&2
    echo "Install Claude Code first: npm install -g @anthropic-ai/claude-code" >&2
    exit 1
fi

echo "  ✓ git $(git --version | awk '{print $3}')"
echo "  ✓ node $(node --version)"
echo "  ✓ claude CLI detected"
echo ""

# 2. Install superpowers plugin
echo "[2/4] Installing dependency: superpowers plugin..."
if claude plugin install superpowers@claude-plugins-official --scope user; then
    echo "  ✓ superpowers plugin installed"
else
    echo "  ! Warning: could not install superpowers automatically. Verify marketplace access." >&2
fi
echo ""

# 3. Install llm-council skill
echo "[3/4] Installing dependency: llm-council skill..."
LLM_COUNCIL_DIR="${HOME}/.claude/skills/llm-council"
mkdir -p "${HOME}/.claude/skills"

if [ -d "${LLM_COUNCIL_DIR}/.git" ]; then
    echo "  Updating existing llm-council repository..."
    git -C "${LLM_COUNCIL_DIR}" pull --ff-only || true
    echo "  ✓ llm-council updated"
elif [ -d "${LLM_COUNCIL_DIR}" ]; then
    echo "  ✓ llm-council folder already exists at ${LLM_COUNCIL_DIR}"
else
    echo "  Cloning llm-council into ${LLM_COUNCIL_DIR}..."
    git clone https://github.com/tenfoldmarc/llm-council-skill.git "${LLM_COUNCIL_DIR}"
    echo "  ✓ llm-council cloned"
fi
echo ""

# 4. Install dev plugin
echo "[4/4] Installing dev plugin..."
if claude plugin install "${SCRIPT_DIR}" --scope user; then
    echo "  ✓ dev plugin installed from ${SCRIPT_DIR}"
else
    echo "  ! Falling back to copying skill into ~/.claude/skills/dev..."
    mkdir -p "${HOME}/.claude/skills/dev"
    cp "${SCRIPT_DIR}/skills/dev/SKILL.md" "${HOME}/.claude/skills/dev/"
    cp "${SCRIPT_DIR}/skills/dev/implement-and-review.js" "${HOME}/.claude/skills/dev/"
    cp "${SCRIPT_DIR}/skills/dev/dev-trace.js" "${HOME}/.claude/skills/dev/"
    echo "  ! Note: the bare-skill fallback has no hooks, so production tracing (dev-trace) will NOT record. /dev will flag this at gate GT." >&2
    echo "  ✓ Copied skill directly to ~/.claude/skills/dev"
fi
echo ""

# Default AI observability choice for tools that call an AI (asked/confirmed by /dev, gate GA)
DEFAULTS="${HOME}/.claude/dev-pipeline.json"
if [ ! -f "${DEFAULTS}" ]; then
    printf '{\n  "agentObservabilityDefault": "A"\n}\n' > "${DEFAULTS}"
    echo "  ✓ AI observability default set to A (full) in ${DEFAULTS}"
fi
echo ""

echo "=== Installation complete ==="
echo "You can now run /dev inside any Claude Code session."
