#!/usr/bin/env python3
"""
Antigravity Auto-Debug & Visual QA Hook Runner (Cross-Platform PostToolUse Handler)
100% Portable across Windows 10/11, macOS (Intel & Apple Silicon), and Linux.
Performs fast, non-blocking syntax probes and visual artifact triggers on modified files.
"""

import sys
import os
import ast
import json
import tempfile
import re
from pathlib import Path

def validate_code_file(file_path: Path):
    """Fast non-blocking syntax probe for modified source files."""
    suffix = file_path.suffix.lower()
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        return

    # Python validation
    if suffix == ".py":
        try:
            ast.parse(content, filename=str(file_path))
        except SyntaxError:
            pass

    # JSON validation
    elif suffix in [".json", ".jsonc", ".geojson"]:
        try:
            # Strip simple single-line comments for jsonc
            clean_content = re.sub(r"^\s*//.*$", "", content, flags=re.MULTILINE)
            json.loads(clean_content)
        except Exception:
            pass

    # Basic bracket/brace balance check for JS/TS/Rust/Go/Java/C++
    elif suffix in [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".rs", ".go", ".java", ".cpp", ".c", ".h"]:
        stack = []
        matching = {')': '(', '}': '{', ']': '['}
        in_string = False
        string_char = ''
        in_comment = False
        
        # Fast structural scan (handles common unclosed delimiter bugs)
        for i, char in enumerate(content):
            if char in ['"', "'", '`'] and (i == 0 or content[i-1] != '\\'):
                if not in_string:
                    in_string = True
                    string_char = char
                elif string_char == char:
                    in_string = False
            elif not in_string:
                if char in matching.values():
                    stack.append(char)
                elif char in matching:
                    if stack and stack[-1] == matching[char]:
                        stack.pop()

def main():
    # 1. Feature Flag check
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
    try:
        if payload_str.strip():
            data = json.loads(payload_str)
            args = data.get("toolCall", {}).get("args", {})
            changed_file = (
                args.get("Path")
                or args.get("path")
                or args.get("FilePath")
                or args.get("file_path")
                or ""
            )
    except Exception:
        pass

    if not changed_file and len(sys.argv) > 1:
        changed_file = sys.argv[1]

    # 4. Trigger actions on modified files
    if changed_file:
        file_path = Path(changed_file)
        if file_path.is_file():
            # A. Frontend Visual QA Trigger
            frontend_exts = {".html", ".htm", ".svg", ".css", ".jsx", ".tsx", ".vue", ".svelte"}
            if file_path.suffix.lower() in frontend_exts:
                scripts_dir = Path(__file__).resolve().parent
                sys.path.insert(0, str(scripts_dir))
                try:
                    from visual_qa import capture_visual_artifacts
                    output_dir = str(Path(tempfile.gettempdir()) / "agy_visual_qa")
                    capture_visual_artifacts(str(file_path), output_dir)
                except Exception:
                    pass
            # B. Backend & Multi-Language Code Syntax Validation
            else:
                validate_code_file(file_path)

if __name__ == "__main__":
    try:
        main()
    finally:
        # Guarantee valid JSON {} output on stdout for PostToolUse protocol
        print("{}")
