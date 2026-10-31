#!/usr/bin/env python3
"""
Antigravity Auto-Debug Hook Runner (Cross-Platform PostToolUse Handler)
100% Portable across Windows 10/11, macOS (Intel & Apple Silicon), and Linux.
Performs fast, non-blocking syntax probes and outputs actionable diagnostics to stderr.
"""

import sys
import os
import ast
import json
import tempfile
import re
from pathlib import Path

def validate_code_file(file_path: Path) -> list[str]:
    """Fast non-blocking syntax probe for modified source files. Returns list of errors."""
    suffix = file_path.suffix.lower()
    errors = []
    
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        return [f"ReadError in {file_path.name}: {str(e)}"]

    # 1. Python AST Validation
    if suffix == ".py":
        try:
            ast.parse(content, filename=str(file_path))
        except SyntaxError as e:
            errors.append(f"SyntaxError in {file_path.name}: {e.msg} (line {e.lineno}, col {e.offset})")

    # 2. JSON / JSONC Validation
    elif suffix in [".json", ".jsonc", ".geojson"]:
        try:
            clean_content = re.sub(r"^\s*//.*$", "", content, flags=re.MULTILINE)
            json.loads(clean_content)
        except json.JSONDecodeError as e:
            errors.append(f"JSONDecodeError in {file_path.name}: {e.msg} (line {e.lineno}, col {e.colno})")
        except Exception as e:
            errors.append(f"JSONError in {file_path.name}: {str(e)}")

    # 3. Delimiter & String Balancer for JS/TS/Rust/Go/Java/C++
    elif suffix in [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".rs", ".go", ".java", ".cpp", ".c", ".h"]:
        stack = []
        matching = {')': '(', '}': '{', ']': '['}
        in_string = False
        string_char = ''
        in_single_comment = False
        in_multi_comment = False
        i = 0
        n = len(content)

        while i < n:
            char = content[i]
            next_char = content[i + 1] if i + 1 < n else ''

            # Comment handling
            if in_single_comment:
                if char == '\n':
                    in_single_comment = False
                i += 1
                continue
            if in_multi_comment:
                if char == '*' and next_char == '/':
                    in_multi_comment = False
                    i += 2
                    continue
                i += 1
                continue

            # Check start of comment if not in string
            if not in_string:
                if char == '/' and next_char == '/':
                    in_single_comment = True
                    i += 2
                    continue
                if char == '/' and next_char == '*':
                    in_multi_comment = True
                    i += 2
                    continue

            # String handling
            if char in ['"', "'", '`']:
                is_escaped = (i > 0 and content[i - 1] == '\\' and (i < 2 or content[i - 2] != '\\'))
                if not is_escaped:
                    if not in_string:
                        in_string = True
                        string_char = char
                    elif string_char == char:
                        in_string = False
                i += 1
                continue

            # Delimiter checks
            if not in_string:
                if char in matching.values():
                    # Calculate line number
                    line_num = content.count('\n', 0, i) + 1
                    stack.append((char, line_num))
                elif char in matching:
                    line_num = content.count('\n', 0, i) + 1
                    if not stack or stack[-1][0] != matching[char]:
                        expected = matching[char]
                        actual = stack[-1][0] if stack else "none"
                        errors.append(f"BracketMismatch in {file_path.name}: unmatched '{char}' at line {line_num} (expected pair for '{actual}')")
                        break
                    else:
                        stack.pop()
            i += 1

        if not errors and stack:
            unclosed_char, line_num = stack[-1]
            errors.append(f"UnclosedBracket in {file_path.name}: unclosed '{unclosed_char}' opened at line {line_num}")

    return errors

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
