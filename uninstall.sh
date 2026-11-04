#!/usr/bin/env bash
set -euo pipefail

echo "=== Uninstall /dev SDLC Pipeline Suite ==="
echo ""

# 1. Uninstall plugin
echo "Uninstalling dev plugin..."
claude plugin uninstall dev --scope user 2>/dev/null || true

# 2. Clean fallback if present
if [ -d "${HOME}/.claude/skills/dev" ]; then
    echo "Removing ~/.claude/skills/dev fallback folder..."
    rm -rf "${HOME}/.claude/skills/dev"
fi

echo ""
echo "dev plugin uninstalled."
echo "Note: dependencies 'superpowers' and 'llm-council' were left intact in case other workflows use them."
