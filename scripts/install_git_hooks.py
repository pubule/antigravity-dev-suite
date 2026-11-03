#!/usr/bin/env python3
"""
Antigravity Pre-Commit Git Hook Installer (Cross-Platform)
Installs or updates .git/hooks/pre-commit to enforce Claude Opus 5.5 quality gates:
The hook runs `agy_hook.py check`, the same gate as the Antigravity Stop hook:
syntax, static critic, test-first, typecheck/lint when configured, and tests.
The browser step (visual QA) is skipped here to keep commits fast; the Stop gate runs it.
Compatible with Windows, macOS, and Linux.
"""

from __future__ import annotations

import sys
import os
import json
import stat
import argparse
from pathlib import Path

HOOK_SCRIPT_TEMPLATE = """#!/bin/sh
# Antigravity Enterprise Quality Gate - Claude Opus 5.5 Standard
# Runs the same verification gate as the Antigravity Stop hook before every commit:
# syntax, static critic, test-first, typecheck/lint (if configured) and tests.

PYTHON_BIN="{python_path}"
GATE_SCRIPT="{gate_script_path}"

if [ ! -f "$GATE_SCRIPT" ] || [ ! -f "$PYTHON_BIN" ]; then
    echo "❌ [Antigravity] Quality gate or Python not found ($PYTHON_BIN / $GATE_SCRIPT)."
    echo "   Reinstall the suite, or remove this hook with: python3 <suite>/scripts/install_git_hooks.py --uninstall"
    exit 1
fi

echo "🧠 [Antigravity] Running the pre-commit quality gate..."
exec "$PYTHON_BIN" "$GATE_SCRIPT" check --no-visual .
"""

def find_git_root(start_dir: Path | None = None) -> Path | None:
    """Finds the root of the current Git repository."""
    current = (start_dir or Path.cwd()).resolve()
    for parent in [current] + list(current.parents):
        if (parent / ".git").exists():
            return parent
    return None

def install_git_hook(workspace_dir: str | Path | None = None, force: bool = False) -> dict:
    """Installs .git/hooks/pre-commit quality gate into target repository."""
    ws = Path(workspace_dir).resolve() if workspace_dir else Path.cwd().resolve()
    git_root = find_git_root(ws)

    if not git_root:
        return {
            "status": "ERROR",
            "message": f"No .git directory found at or above {ws}",
            "workspace": str(ws)
        }

    hooks_dir = git_root / ".git" / "hooks"
    # Support git worktrees or submodules where .git is a file
    git_entry = git_root / ".git"
    if git_entry.is_file():
        try:
            content = git_entry.read_text(encoding="utf-8").strip()
            if content.startswith("gitdir:"):
                real_git_dir = (git_root / content.split(":", 1)[1].strip()).resolve()
                hooks_dir = real_git_dir / "hooks"
        except OSError as gitdir_err:
            # Fallback to standard .git/hooks directory
            hooks_dir = git_root / ".git" / "hooks"

    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_file = hooks_dir / "pre-commit"

    if hook_file.exists() and not force:
        try:
            existing = hook_file.read_text(encoding="utf-8")
            if "Antigravity Enterprise Quality Gate" in existing:
                return {
                    "status": "ALREADY_INSTALLED",
                    "hook_path": str(hook_file),
                    "git_root": str(git_root)
                }
        except OSError as read_err:
            existing = ""

    # Resolve scripts paths relative to current script installation
    this_dir = Path(__file__).resolve().parent
    gate_path = (this_dir / "agy_hook.py").resolve()

    hook_content = HOOK_SCRIPT_TEMPLATE.format(
        python_path=str(Path(sys.executable).resolve()).replace("\\", "/"),
        gate_script_path=str(gate_path).replace("\\", "/")
    )

    try:
        hook_file.write_text(hook_content, encoding="utf-8")
        # Ensure executable permissions on POSIX
        current_perms = hook_file.stat().st_mode
        hook_file.chmod(current_perms | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return {
            "status": "SUCCESS",
            "hook_path": str(hook_file),
            "git_root": str(git_root)
        }
    except (OSError, PermissionError) as e:
        return {
            "status": "ERROR",
            "message": str(e),
            "hook_path": str(hook_file)
        }

def uninstall_git_hook(workspace_dir: str | Path | None = None) -> dict:
    """Removes Antigravity .git/hooks/pre-commit hook."""
    ws = Path(workspace_dir).resolve() if workspace_dir else Path.cwd().resolve()
    git_root = find_git_root(ws)
    if not git_root:
        return {"status": "ERROR", "message": "No .git root found"}

    hook_file = git_root / ".git" / "hooks" / "pre-commit"
    if not hook_file.exists():
        return {"status": "NOT_FOUND", "hook_path": str(hook_file)}

    try:
        content = hook_file.read_text(encoding="utf-8")
        if "Antigravity Enterprise Quality Gate" in content:
            hook_file.unlink()
            return {"status": "REMOVED", "hook_path": str(hook_file)}
        return {"status": "SKIPPED", "message": "Hook does not originate from Antigravity"}
    except OSError as e:
        return {"status": "ERROR", "message": str(e)}

def main():
    parser = argparse.ArgumentParser(description="Antigravity Pre-Commit Git Hook Manager")
    parser.add_argument("--workspace", "-w", default=None, help="Path to workspace / repository")
    parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing hook")
    parser.add_argument("--uninstall", action="store_true", help="Uninstall existing hook")

    args = parser.parse_args()
    if args.uninstall:
        res = uninstall_git_hook(args.workspace)
    else:
        res = install_git_hook(args.workspace, force=args.force)

    print(json.dumps(res, indent=2))
    sys.exit(0 if res.get("status") in ("SUCCESS", "ALREADY_INSTALLED", "REMOVED") else 1)

if __name__ == "__main__":
    main()
