#!/usr/bin/env python3
"""
Antigravity Stop Gate Hook Runner (Cross-Platform)
Prevents premature agent exits on Gemini Flash 3.8 by verifying:
1. Zero cached syntax errors in diagnostic store.
2. Verified 100% green test execution when production code is modified.
100% Portable across macOS, Linux, and Windows 10/11.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from auto_debug_runner import (
        get_last_syntax_error,
        clear_last_syntax_error,
        get_last_test_run,
        get_last_critic_run,
        clear_last_critic_run,
        detect_project_framework,
        safe_git_env,
    )
except ImportError:
    get_last_syntax_error = lambda: None
    clear_last_syntax_error = lambda: False
    get_last_test_run = lambda: None
    get_last_critic_run = lambda: None
    clear_last_critic_run = lambda: False
    detect_project_framework = lambda ws: {"status": "UNKNOWN"}
    safe_git_env = lambda: dict(os.environ)

CODE_EXTENSIONS = {
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".rs", ".go", ".c", ".cpp", ".cc", ".h", ".hpp", ".cs", ".java",
    ".kt", ".swift", ".php", ".rb", ".sql", ".sh"
}


def get_modified_code_files(ws_dir: Path) -> List[str]:
    """Finds modified or untracked code files in the git workspace."""
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(ws_dir),
            capture_output=True,
            text=True,
            env=safe_git_env(),
            check=False,
            timeout=10
        )
        if res.returncode != 0:
            return []
        
        modified_code: List[str] = []
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                file_rel = parts[1].strip()
                if any(file_rel.lower().endswith(ext) for ext in CODE_EXTENSIONS):
                    modified_code.append(file_rel)
        return modified_code
    except Exception:
        return []


def audit_stop_permission(payload: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """Evaluates whether agent is permitted to terminate execution.

    Returns:
        (decision, reason) where decision is 'continue' or 'allow'.
    """
    # 0. Check disable environment flag
    if os.environ.get("AGY_STOP_GATE_DISABLE", "0").lower() in ("1", "true", "yes"):
        return "allow", None

    # 1. Protect against infinite loops (allow after 3 blocked attempts)
    execution_num = payload.get("executionNum", 1)
    if isinstance(execution_num, int) and execution_num >= 3:
        return "allow", None

    # Only gate on normal completion (NO_TOOL_CALL)
    termination_reason = payload.get("terminationReason", "NO_TOOL_CALL")
    if termination_reason not in ("NO_TOOL_CALL", "TERMINAL_STEP_TYPE", ""):
        return "allow", None

    # 2. Check for cached syntax errors
    last_syntax = get_last_syntax_error()
    if last_syntax and isinstance(last_syntax.get("errors"), list) and last_syntax["errors"]:
        err_file = last_syntax.get("file", "unknown")
        err_path = Path(err_file).resolve() if err_file and err_file != "unknown" else None
        if not err_path or not err_path.is_file():
            clear_last_syntax_error()
        else:
            err_msg = last_syntax["errors"][0]
            reason = (
                f"[Antigravity Stop Gate] Unresolved syntax defect in {err_file}: {err_msg}. "
                "You must heal the syntax error before completing the task."
            )
            return "continue", reason

    # 3. Determine workspace directory
    ws_paths = payload.get("workspacePaths", [])
    ws = Path(ws_paths[0]).resolve() if ws_paths else Path.cwd().resolve()

    # 4. Check for modified code files
    modified_files = get_modified_code_files(ws)
    if not modified_files:
        return "allow", None

    # 5. Check if workspace has a test framework configured
    framework_info = detect_project_framework(ws)
    if framework_info.get("status") != "DETECTED":
        return "allow", None

    # 6. Check last recorded test run
    last_test = get_last_test_run()
    if not last_test:
        reason = (
            f"[Antigravity Stop Gate] {len(modified_files)} code file(s) modified "
            f"({', '.join(modified_files[:3])}) but no test suite run was recorded. "
            "Execute the project tests (python3 scripts/auto_debug_runner.py --run-tests) "
            "and verify a 100% green pass before completing."
        )
        return "continue", reason

    if last_test.get("status") != "PASS":
        failed_status = last_test.get("status", "FAIL")
        reason = (
            f"[Antigravity Stop Gate] Test suite status is '{failed_status}'. "
            "All tests must pass (100% GREEN) before completing the task. "
            "Execute python3 scripts/auto_debug_runner.py --run-tests to re-verify."
        )
        return "continue", reason

    # 7. Check last recorded critic loop audit
    last_critic = get_last_critic_run()
    if last_critic:
        c_target = last_critic.get("target")
        if c_target and c_target != ".":
            try:
                c_path = Path(c_target).resolve()
                if not c_path.exists() or (ws not in c_path.parents and c_path != ws):
                    clear_last_critic_run()
                    last_critic = None
            except Exception:
                clear_last_critic_run()
                last_critic = None

    if not last_critic:
        reason = (
            f"[Antigravity Stop Gate] {len(modified_files)} code file(s) modified "
            f"({', '.join(modified_files[:3])}) but no critic loop audit was recorded. "
            "Execute the critic loop audit (python3 scripts/critic_loop.py --mode logic --target .) "
            "and achieve a clean 100% PASS before completing."
        )
        return "continue", reason

    if last_critic.get("status") != "PASS":
        failed_count = last_critic.get("violations_count", 0)
        reason = (
            f"[Antigravity Stop Gate] Critic loop reported {failed_count} unresolved defect(s) (status 'RETRY'). "
            "All critic violations must be resolved before completing the task. "
            "Execute python3 scripts/critic_loop.py --mode logic --target . to re-verify."
        )
        return "continue", reason

    return "allow", None


def main() -> None:
    # CLI check mode
    if len(sys.argv) > 1 and sys.argv[1] in ("--check", "-c"):
        target_ws = sys.argv[2] if len(sys.argv) > 2 else "."
        decision, reason = audit_stop_permission({
            "executionNum": 1,
            "terminationReason": "NO_TOOL_CALL",
            "workspacePaths": [target_ws]
        })
        print(json.dumps({"decision": decision, "reason": reason}, indent=2))
        sys.exit(0 if decision == "allow" else 1)

    # Read stdin payload from Antigravity lifecycle event
    payload_str = ""
    try:
        if not sys.stdin.isatty():
            payload_str = sys.stdin.read()
    except (OSError, UnicodeDecodeError):
        payload_str = ""

    payload: Dict[str, Any] = {}
    if payload_str.strip():
        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError:
            payload = {}

    decision, reason = audit_stop_permission(payload)
    output: Dict[str, Any] = {"decision": decision}
    if reason:
        output["reason"] = reason

    print(json.dumps(output))


if __name__ == "__main__":
    main()
