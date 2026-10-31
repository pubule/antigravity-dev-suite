#!/usr/bin/env python3
"""
Antigravity Auto-Debug Hook Runner (Cross-Platform PostToolUse Handler)
100% Portable across Windows 10/11, macOS (Intel & Apple Silicon), and Linux.
Performs fast, non-blocking syntax probes and outputs actionable diagnostics to stderr.
"""

import sys
import os
import json
import tempfile
from pathlib import Path

# Add current scripts directory to sys.path for robust relative import
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from validator_core import validate_code_file, extract_target_file
except ImportError:
    # Fallback to local import
    import validator_core
    validate_code_file = validator_core.validate_code_file
    extract_target_file = validator_core.extract_target_file

def main():
    # 1. Feature flag check
    auto_debug_enabled = os.environ.get("AGY_AUTO_DEBUG", "1").lower() not in ["0", "false", "off", "no"]
    if not auto_debug_enabled:
        return

    # 2. Read stdin JSON payload safely
    payload_str = ""
    try:
        if not sys.stdin.isatty():
            payload_str = sys.stdin.read()
    except Exception:
        pass

    # 3. Extract changed file path
    changed_file = ""
    if payload_str.strip():
        changed_file = extract_target_file(payload_str)

    if not changed_file and len(sys.argv) > 1:
        changed_file = sys.argv[1]

    # 4. Perform syntax probe on modified file
    if changed_file:
        file_path = Path(changed_file)
        if file_path.is_file():
            errors = validate_code_file(file_path)
            if errors:
                for err in errors:
                    print(f"⚠️ [Antigravity Auto-Debug] {err}", file=sys.stderr)
                # Persist diagnostic record for auto-debug inspection
                try:
                    diag_file = Path(tempfile.gettempdir()) / "agy_last_syntax_error.json"
                    with open(diag_file, "w", encoding="utf-8") as f:
                        json.dump({
                            "file": str(file_path),
                            "errors": errors
                        }, f, indent=2)
                except Exception:
                    pass

if __name__ == "__main__":
    try:
        main()
    finally:
        # Guarantee valid JSON {} output on stdout for PostToolUse protocol
        print("{}")
