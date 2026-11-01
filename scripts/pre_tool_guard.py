#!/usr/bin/env python3
"""Pre-tool execution safety guardrail for Antigravity Dev Suite.

Inspects tool calls before execution to prevent:
1. Catastrophic system commands (e.g. rm -rf /, fork bomb, raw disk write).
2. Direct destruction of Git tracking metadata (e.g. rm -rf .git).
3. Secret leaks (e.g. unencrypted private keys, cloud tokens).
4. Direct modification of internal .git repository storage.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

# Catastrophic shell command patterns
CATASTROPHIC_COMMAND_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    (
        "Root or home filesystem deletion",
        re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+(?:/[*\s]*|~[*\s]*|\$HOME[*\s]*)(?:$|[\s;&|])")
    ),
    (
        "Git repository metadata deletion",
        re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+(?:\.git|\.git/|\./\.git)(?:$|[\s;&|/*])")
    ),
    (
        "Filesystem formatting",
        re.compile(r"\b(?:mkfs|mkfs\.[a-z0-9]+)\s+/dev/")
    ),
    (
        "Direct disk block device overwrite",
        re.compile(r"\bdd\s+.*of=/dev/(?:sd[a-z]|nvme[0-9]|disk[0-9]|rdisk[0-9])\b")
    ),
    (
        "Shell fork bomb",
        re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:")
    ),
    (
        "Force push to primary branch",
        re.compile(r"\bgit\s+push\s+.*(?:--force|-f)\s+(?:origin|upstream)\s+(?:main|master)\b")
    )
]

# Sensitive secret patterns for file writes
SENSITIVE_SECRET_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    (
        "Unencrypted private key",
        re.compile(r"-----BEGIN (?:RSA|OPENSSH|DSA|EC|PGP)? ?PRIVATE KEY-----")
    ),
    (
        "AWS Access Key ID",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b")
    ),
    (
        "GitHub Personal Access Token",
        re.compile(r"\bghp_[A-Za-z0-9]{36}\b")
    ),
    (
        "GitHub Fine-grained Token",
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{82}\b")
    ),
    (
        "Slack Bot Token",
        re.compile(r"\bxoxb-[0-9]{10,13}-[0-9]{10,13}-[A-Za-z0-9]{24}\b")
    )
]

# Forbidden target paths
PROTECTED_PATH_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    (
        "Direct .git repository internal file modification",
        re.compile(r"(?:^|/)\.git/(?:objects|refs|HEAD|config|index)(?:/|$)")
    )
]


def audit_command_safety(command: str) -> Optional[str]:
    """Inspect shell command string for catastrophic operations.

    Returns violation reason if unsafe, otherwise None.
    """
    clean_cmd = command.strip()
    for rule_name, pattern in CATASTROPHIC_COMMAND_PATTERNS:
        if pattern.search(clean_cmd):
            return f"Blocked dangerous command pattern: {rule_name}"
    return None


def audit_file_content_safety(content: str) -> Optional[str]:
    """Inspect file content for hardcoded unencrypted credentials.

    Returns violation reason if unsafe, otherwise None.
    """
    for rule_name, pattern in SENSITIVE_SECRET_PATTERNS:
        if pattern.search(content):
            return f"Blocked file write containing secret: {rule_name}"
    return None


def audit_path_safety(file_path: str) -> Optional[str]:
    """Inspect target file path for forbidden system or git repository paths.

    Returns violation reason if unsafe, otherwise None.
    """
    normalized_path = file_path.replace("\\", "/")
    for rule_name, pattern in PROTECTED_PATH_PATTERNS:
        if pattern.search(normalized_path):
            return f"Blocked protected path write: {rule_name}"
    return None


def inspect_tool_call(tool_name: str, args: Dict[str, Any]) -> Tuple[bool, str]:
    """Evaluate tool invocation arguments against safety rules.

    Returns (is_allowed, reason).
    """
    if tool_name == "run_command":
        cmd = args.get("CommandLine", "") or args.get("command", "")
        if isinstance(cmd, str) and cmd:
            violation = audit_command_safety(cmd)
            if violation:
                return False, violation

    elif tool_name in ("write_file", "edit_file"):
        path = args.get("Path", "") or args.get("path", "")
        if isinstance(path, str) and path:
            violation = audit_path_safety(path)
            if violation:
                return False, violation

        # Check content or replacement
        content = args.get("Content", "") or args.get("content", "")
        if not content:
            content = args.get("Replacement", "") or args.get("replacement", "")

        if isinstance(content, str) and content:
            violation = audit_file_content_safety(content)
            if violation:
                return False, violation

    return True, "Operation permitted"


def handle_cli_mode() -> bool:
    """Handle standalone command-line testing arguments."""
    args = sys.argv[1:]
    if not args:
        return False

    first = args[0]
    if first in ("--check-cmd", "-c"):
        cmd_to_test = " ".join(args[1:])
        violation = audit_command_safety(cmd_to_test)
        result = {
            "decision": "deny" if violation else "allow",
            "reason": violation or "Operation permitted"
        }
        print(json.dumps(result, indent=2))
        sys.exit(0 if not violation else 1)

    if first in ("--check-content", "-k"):
        content_to_test = " ".join(args[1:])
        violation = audit_file_content_safety(content_to_test)
        result = {
            "decision": "deny" if violation else "allow",
            "reason": violation or "Operation permitted"
        }
        print(json.dumps(result, indent=2))
        sys.exit(0 if not violation else 1)

    if first in ("--check-path", "-p"):
        path_to_test = args[1] if len(args) > 1 else ""
        violation = audit_path_safety(path_to_test)
        result = {
            "decision": "deny" if violation else "allow",
            "reason": violation or "Operation permitted"
        }
        print(json.dumps(result, indent=2))
        sys.exit(0 if not violation else 1)

    return False


def main() -> None:
    """PreToolUse hook entry point."""
    if handle_cli_mode():
        return

    # Check feature flag
    guard_enabled = os.environ.get("AGY_PRE_TOOL_GUARD", "1").lower() not in ["0", "false", "off", "no"]
    if not guard_enabled:
        print(json.dumps({"decision": "allow"}))
        return

    # Read stdin payload
    payload_str = ""
    try:
        if not sys.stdin.isatty():
            payload_str = sys.stdin.read()
    except (OSError, UnicodeDecodeError):
        payload_str = ""

    if not payload_str.strip():
        # Fallback to allow if stdin empty
        print(json.dumps({"decision": "allow"}))
        return

    try:
        data = json.loads(payload_str)
    except json.JSONDecodeError:
        # Cannot parse payload, allow execution safely
        print(json.dumps({"decision": "allow"}))
        return

    tool_call = data.get("toolCall", {})
    tool_name = tool_call.get("name", "")
    args = tool_call.get("args", {})

    allowed, reason = inspect_tool_call(tool_name, args)
    if not allowed:
        output = {
            "decision": "deny",
            "reason": f"[Antigravity Pre-Tool Guard] {reason}"
        }
        print(json.dumps(output))
        sys.exit(0)

    print(json.dumps({"decision": "allow"}))


if __name__ == "__main__":
    main()
