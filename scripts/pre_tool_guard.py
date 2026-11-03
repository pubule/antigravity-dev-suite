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
import shlex
import sys
from typing import Any, Dict, List, Optional, Tuple

# Antigravity tool names (see https://antigravity.google/docs/hooks)
SHELL_TOOLS = {"run_command"}
FILE_WRITE_TOOLS = {"write_to_file", "replace_file_content", "multi_replace_file_content"}
# Legacy names kept so older payload shapes still get inspected.
LEGACY_FILE_WRITE_TOOLS = {"write_file", "edit_file"}

PATH_ARG_KEYS = ("TargetFile", "AbsolutePath", "Path", "path", "FilePath", "file_path", "target_file")

# Catastrophic shell command patterns (regex part; rm and git push use token analysis)
CATASTROPHIC_COMMAND_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
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
]

# Commands that switch off or tamper with the verification gates. The gates
# are configured by the user, never by the agent.
GATE_BYPASS_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    (
        "Gate configuration variable (reserved for the user)",
        re.compile(r"\bAGY_(?:SKIP_PRECOMMIT|STOP_GATE_DISABLE|STOP_GATE_MAX_BLOCKS|PRE_TOOL_GUARD|AUTO_DEBUG|REQUIRE_TESTS|"
                   r"INTEGRITY|VISUAL_QA|COVERAGE|CRITERIA|READ_BEFORE_WRITE|LOOP_ESCALATE|TEST_TIMEOUT|BUILD)\b")
    ),
    (
        "Git hook bypass (--no-verify)",
        re.compile(r"\bgit\b[^;&|]*\s--no-verify\b")
    ),
    (
        "Git commit hook bypass (-n)",
        re.compile(r"\bgit\s+commit\b[^;&|]*\s-[a-zA-Z]*n[a-zA-Z]*(?:\s|$)")
    ),
    (
        "Git hooks path override",
        re.compile(r"\bcore\.hooksPath\b|\.git[/\\]hooks\b")
    ),
    (
        "Verification state tampering",
        re.compile(r"\.git[/\\]agy\b|agy_last_(?:test|critic)_run|agy_last_syntax_error|--clear-last-(?:error|critic)\b|\.agents[/\\]agy\.json")
    ),
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
        re.compile(r"(?:^|/)\.git/")
    ),
    (
        "Verification gate configuration (reserved for the user)",
        re.compile(r"(?:^|/)\.agents/(?:agy\.json|hooks\.json)$")
    ),
]

_DANGEROUS_RM_TARGETS = {"/", "/*", "~", "~/", "~/*", "$HOME", "$HOME/", "$HOME/*", "${HOME}", "${HOME}/", "${HOME}/*", ".git", ".git/", "./.git", "./.git/", ".git/*"}
_PRIMARY_BRANCHES = {"main", "master"}


def _split_segments(command: str) -> List[List[str]]:
    """Split a shell line into simple command segments of tokens."""
    segments: List[List[str]] = []
    for raw in re.split(r"&&|\|\||;|\||\n", command):
        raw = raw.strip()
        if not raw:
            continue
        try:
            tokens = shlex.split(raw, posix=True)
        except ValueError:
            tokens = raw.split()
        # Drop leading env assignments and sudo-like wrappers
        while tokens and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]) or tokens[0] in ("sudo", "doas", "env", "command", "exec", "nohup")):
            tokens = tokens[1:]
        if tokens:
            segments.append(tokens)
    return segments


def _audit_rm(tokens: List[str]) -> Optional[str]:
    recursive = force = False
    targets: List[str] = []
    for tok in tokens[1:]:
        if tok == "--":
            continue
        if tok.startswith("--"):
            recursive = recursive or tok in ("--recursive",)
            force = force or tok in ("--force",)
        elif tok.startswith("-") and len(tok) > 1:
            recursive = recursive or "r" in tok or "R" in tok
            force = force or "f" in tok
        else:
            targets.append(tok)
    if not recursive:
        return None
    for t in targets:
        if t in _DANGEROUS_RM_TARGETS:
            return "Git repository metadata deletion" if ".git" in t else "Root or home filesystem deletion"
    return None


def _audit_git_push(tokens: List[str]) -> Optional[str]:
    if len(tokens) < 2 or tokens[1] != "push":
        return None
    forced = any(t in ("-f", "--force") or (re.match(r"^-[a-zA-Z]+$", t) and "f" in t) for t in tokens[2:])
    refs = [t for t in tokens[2:] if not t.startswith("-")]
    plus_ref = any(r.startswith("+") for r in refs)
    if not (forced or plus_ref):
        return None
    for r in refs:
        name = r.lstrip("+").split(":")[-1]
        name = name.replace("refs/heads/", "")
        if name in _PRIMARY_BRANCHES:
            return "Force push to primary branch"
    return None


def audit_command_safety(command: str) -> Optional[str]:
    """Inspect shell command string for catastrophic operations or gate bypasses.

    Returns violation reason if unsafe, otherwise None.
    """
    clean_cmd = command.strip()
    for rule_name, pattern in CATASTROPHIC_COMMAND_PATTERNS:
        if pattern.search(clean_cmd):
            return f"Blocked dangerous command pattern: {rule_name}"
    for tokens in _split_segments(clean_cmd):
        prog = os.path.basename(tokens[0])
        if prog == "rm":
            hit = _audit_rm(tokens)
            if hit:
                return f"Blocked dangerous command pattern: {hit}"
        elif prog == "git":
            hit = _audit_git_push(tokens)
            if hit:
                return f"Blocked dangerous command pattern: {hit}"
    for rule_name, pattern in GATE_BYPASS_PATTERNS:
        if pattern.search(clean_cmd):
            return (
                f"Blocked verification bypass: {rule_name}. "
                "Fix the reported problems instead of disabling the checks."
            )
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


def extract_write_path(args: Dict[str, Any]) -> str:
    """Return the target file path of a file-write tool call."""
    for key in PATH_ARG_KEYS:
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            val = val.strip()
            if val.startswith("file://"):
                val = val[7:]
            return val
    return ""


def _collect_strings(value: Any, skip_keys: Tuple[str, ...] = PATH_ARG_KEYS) -> List[str]:
    """Collect every string leaf of the tool arguments (content, chunks, replacements)."""
    found: List[str] = []
    if isinstance(value, str):
        found.append(value)
    elif isinstance(value, dict):
        for k, v in value.items():
            if k in skip_keys:
                continue
            found.extend(_collect_strings(v, skip_keys))
    elif isinstance(value, list):
        for v in value:
            found.extend(_collect_strings(v, skip_keys))
    return found


def inspect_tool_call(tool_name: str, args: Dict[str, Any]) -> Tuple[bool, str]:
    """Evaluate tool invocation arguments against safety rules.

    Returns (is_allowed, reason).
    """
    if not isinstance(args, dict):
        args = {}
    if tool_name in SHELL_TOOLS:
        cmd = args.get("CommandLine", "") or args.get("command", "")
        if isinstance(cmd, str) and cmd:
            violation = audit_command_safety(cmd)
            if violation:
                return False, violation

    elif tool_name in FILE_WRITE_TOOLS or tool_name in LEGACY_FILE_WRITE_TOOLS:
        path = extract_write_path(args)
        if path:
            violation = audit_path_safety(path)
            if violation:
                return False, violation

        for content in _collect_strings(args):
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
