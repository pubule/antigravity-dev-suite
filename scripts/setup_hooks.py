#!/usr/bin/env python3
"""Register, update or remove the dev suite hooks in Antigravity (macOS, Linux, Windows).

    python setup_hooks.py install     # write hooks into ~/.gemini/config/hooks.json
    python setup_hooks.py uninstall   # remove only our entry, keep any other hooks
    python setup_hooks.py status      # show what is registered
    python setup_hooks.py update      # git pull the suite, then install again

The global hooks file is read by both the Antigravity IDE and the CLI. Commands use
the absolute path of the Python interpreter that runs this script, so no PATH,
"python3" vs "py" or shell differences matter at hook time.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

SUITE_DIR = Path(__file__).resolve().parent.parent
HOOK_SCRIPT = SUITE_DIR / "scripts" / "agy_hook.py"
HOOK_KEY = "antigravity-dev-suite"
LEGACY_KEYS = ("antigravity-dev-suite-hooks",)
FILE_TOOLS = "write_to_file|replace_file_content|multi_replace_file_content"


def gemini_home() -> Path:
    env = os.environ.get("GEMINI_HOME")
    return Path(env).expanduser() if env else Path.home() / ".gemini"


def hooks_file() -> Path:
    return gemini_home() / "config" / "hooks.json"


def _windows_short_path(path: str) -> str:
    """8.3 short form of a Windows path (no spaces), or the path unchanged."""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        n = ctypes.windll.kernel32.GetShortPathNameW(path, buf, 1024)  # type: ignore[attr-defined]
        return buf.value if 0 < n < 1024 else path
    except Exception:
        return path


def _quote(path: str) -> str:
    """Make a path safe for whatever shell runs the hook (sh, cmd or PowerShell).

    A bare path works in all three shells. A quoted path followed by arguments is a
    syntax error in PowerShell, so on Windows spaces are removed with the 8.3 form.
    """
    if not any(c.isspace() or c in "\"'$`&;|<>()" for c in path.replace("\\", "")):
        return path
    if os.name == "nt":
        short = _windows_short_path(path)
        if not any(c.isspace() for c in short):
            return short
        return f'"{path}"'
    import shlex
    return shlex.quote(path)


def hook_command(sub: str) -> str:
    return f"{_quote(sys.executable)} {_quote(str(HOOK_SCRIPT))} {sub}"


def build_entry() -> Dict[str, Any]:
    return {
        "enabled": True,
        "SessionStart": [{"type": "command", "command": hook_command("session-start"), "timeout": 15}],
        "PreToolUse": [{
            "matcher": "run_command|" + FILE_TOOLS,
            "hooks": [{"type": "command", "command": hook_command("pre-tool"), "timeout": 10}],
        }],
        "PostToolUse": [{
            "matcher": FILE_TOOLS,
            "hooks": [{"type": "command", "command": hook_command("post-tool"), "timeout": 15}],
        }],
        "PreInvocation": [{"type": "command", "command": hook_command("pre-invocation"), "timeout": 15}],
        # The Stop gate runs the project's tests: give it room.
        "Stop": [{"type": "command", "command": hook_command("stop"), "timeout": 900}],
    }


def _load(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        backup = path.with_suffix(f".json.broken-{int(time.time())}")
        shutil.copy2(str(path), str(backup))
        print(f"  ! {path} was not valid JSON; saved a copy to {backup}")
        return {}


def _save(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(str(tmp), str(path))


def install() -> int:
    if sys.version_info < (3, 9):
        print("Python 3.9 or newer is required.")
        return 1
    path = hooks_file()
    data = _load(path)
    for key in LEGACY_KEYS:
        data.pop(key, None)
    data[HOOK_KEY] = build_entry()
    _save(path, data)
    print(f"  + Hooks registered in {path}")
    print(f"    Interpreter: {sys.executable}")
    return 0


def uninstall() -> int:
    path = hooks_file()
    data = _load(path)
    removed = False
    for key in (HOOK_KEY,) + LEGACY_KEYS:
        if key in data:
            data.pop(key)
            removed = True
    if removed:
        _save(path, data)
        print(f"  - Hooks removed from {path}")
    else:
        print("  = No dev suite hooks were registered")
    return 0


def _commands(entry: Dict[str, Any]) -> List[str]:
    cmds: List[str] = []
    for handlers in entry.values():
        if not isinstance(handlers, list):
            continue
        for h in handlers:
            if not isinstance(h, dict):
                continue
            if "hooks" in h:
                cmds.extend(x.get("command", "") for x in h["hooks"] if isinstance(x, dict))
            elif "command" in h:
                cmds.append(h["command"])
    return cmds


def installed_status() -> Dict[str, Any]:
    data = _load(hooks_file())
    entry = data.get(HOOK_KEY)
    if not isinstance(entry, dict):
        return {"installed": False, "paths_ok": False, "commands": []}
    cmds = _commands(entry)
    paths_ok = bool(cmds)
    import shlex
    for c in cmds:
        try:
            parts = [x.strip("\"'") for x in shlex.split(c, posix=(os.name != "nt"))]
        except ValueError:
            parts = []
        if len(parts) < 2 or not (Path(parts[0]).is_file() and Path(parts[1]).is_file()):
            paths_ok = False
    return {"installed": True, "paths_ok": paths_ok, "commands": cmds, "up_to_date": entry == build_entry()}


def status() -> int:
    st = installed_status()
    print(json.dumps(dict(st, hooks_file=str(hooks_file())), indent=2))
    return 0 if st["installed"] and st["paths_ok"] else 1


def update() -> int:
    if (SUITE_DIR / ".git").exists():
        print(f"  Updating {SUITE_DIR} ...")
        res = subprocess.run(["git", "-C", str(SUITE_DIR), "pull", "--ff-only"], check=False, timeout=60)
        if res.returncode != 0:
            print("  ! git pull failed. Resolve it, then run the installer again.")
            return res.returncode
    else:
        print("  Suite folder is not a git clone: download the new version, then run the installer.")
    return install()


def main(argv: List[str]) -> int:
    cmd = argv[0] if argv else "status"
    actions = {"install": install, "uninstall": uninstall, "status": status, "update": update}
    if cmd not in actions:
        print(__doc__)
        return 2
    return actions[cmd]()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
