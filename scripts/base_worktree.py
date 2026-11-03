#!/usr/bin/env python3
"""Temporary checkout of the base commit, shared by the visual baseline and the
"tests must fail without the change" check.

The checkout is a detached `git worktree` inside the gate state folder. It gets a
link to the project's `node_modules` (symlink on POSIX, junction on Windows, no
admin rights needed) and copies of local `.env` files, so dev servers and test
runners work as in the project. The link is always removed before the worktree,
so the real `node_modules` is never deleted.

Python 3.9+ standard library only.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any, List, Tuple

logger = logging.getLogger("base_worktree")

# Untracked folders the base checkout needs to run: dependencies and virtualenvs.
LINKED_DIRS = ("node_modules", ".venv", "venv")
ENV_FILES = (".env", ".env.local", ".env.development", ".env.development.local")


def git(args: List[str], cwd: Path, timeout: int = 120) -> Tuple[int, str]:
    try:
        res = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True,
                             timeout=timeout, check=False, encoding="utf-8", errors="replace")
        return res.returncode, (res.stdout or "") + (res.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def _link_dir(target: Path, link: Path) -> bool:
    """Directory link that works without admin rights: symlink on POSIX, junction on Windows."""
    try:
        if os.name == "nt":
            res = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                                 capture_output=True, check=False, timeout=30)
            return res.returncode == 0
        os.symlink(str(target), str(link), target_is_directory=True)
        return True
    except (OSError, subprocess.SubprocessError) as err:
        logger.debug("Cannot link %s: %s", link, err)
        return False


def _unlink_dir(link: Path) -> None:
    """Remove a directory link without touching what it points to."""
    try:
        if os.name == "nt":
            os.rmdir(str(link))  # removes a junction, never its target
        elif link.is_symlink():
            link.unlink()
    except OSError as err:
        logger.debug("Cannot remove link %s: %s", link, err)


class Worktree:
    """Detached checkout of the base commit, with the project's node_modules and .env files."""

    def __init__(self, root: Path, base: str, path: Path) -> None:
        self.root = root
        self.base = base
        self.path = path
        self.links: List[Path] = []

    def __enter__(self) -> "Worktree":
        self.remove()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        code, out = git(["worktree", "add", "--detach", "--force", str(self.path), self.base], self.root)
        if code != 0:
            raise RuntimeError(f"git worktree add failed: {out.strip()[-500:]}")
        for name in LINKED_DIRS:
            src = self.root / name
            dst = self.path / name
            if src.is_dir() and not dst.exists() and _link_dir(src, dst):
                self.links.append(dst)
        for name in ENV_FILES:
            src = self.root / name
            dst = self.path / name
            if src.is_file() and not dst.exists():
                try:
                    dst.write_bytes(src.read_bytes())
                except OSError as err:
                    logger.debug("Cannot copy %s: %s", name, err)
        return self

    def __exit__(self, *exc: Any) -> None:
        self.remove()

    def remove(self) -> None:
        for link in self.links:
            _unlink_dir(link)
        self.links = []
        if self.path.exists():
            # Links left by an interrupted run: remove the links themselves first, so that
            # "git worktree remove" can never delete the project's real node_modules or venv.
            for name in LINKED_DIRS:
                _unlink_dir(self.path / name)
            git(["worktree", "remove", "--force", str(self.path)], self.root)
        git(["worktree", "prune"], self.root)
