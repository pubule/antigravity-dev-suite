#!/usr/bin/env python3
"""
Antigravity Validator Core
Unified, highly defensive syntax and structural validator for Antigravity Dev Suite.
Shared between PostToolUse auto-debug runner, critic loop, and test harnesses.
100% portable across macOS, Linux, and Windows 10/11.
"""

import sys
import os
import ast
import json
import re
from pathlib import Path
from html.parser import HTMLParser

MAX_VALIDATION_FILE_SIZE = 2 * 1024 * 1024  # 2 MB safety threshold

VOID_HTML_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr", "!doctype"
}

class DefensiveHTMLValidator(HTMLParser):
    """Defensive HTML structure and tag closure validator."""
    def __init__(self, filename: str):
        super().__init__()
        self.filename = filename
        self.tag_stack: list[tuple[str, int]] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        tag_lower = tag.lower()
        if tag_lower not in VOID_HTML_TAGS:
            self.tag_stack.append((tag_lower, self.getpos()[0]))

    def handle_endtag(self, tag: str):
        tag_lower = tag.lower()
        if tag_lower in VOID_HTML_TAGS:
            return
        if not self.tag_stack:
            self.errors.append(f"HTMLTagMismatch in {self.filename}: unexpected closing tag </{tag_lower}> at line {self.getpos()[0]}")
            return
        last_tag, line_num = self.tag_stack[-1]
        if last_tag == tag_lower:
            self.tag_stack.pop()
        else:
            self.errors.append(f"HTMLTagMismatch in {self.filename}: mismatched closing tag </{tag_lower}> at line {self.getpos()[0]} (expected </{last_tag}> opened at line {line_num})")

IGNORED_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".next",
    ".turbo",
    ".idea",
    ".vscode",
    "target",
}

SOURCE_EXTENSIONS = {
    ".py",
    ".json",
    ".jsonc",
    ".geojson",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".rs",
    ".go",
    ".java",
    ".cpp",
    ".c",
    ".h",
    ".html",
}

def extract_target_file(payload_data: dict | str) -> str:
    """Extracts target file path from diverse tool call JSON structures."""
    if isinstance(payload_data, str):
        try:
            payload_data = json.loads(payload_data)
        except Exception:
            return ""

    if not isinstance(payload_data, dict):
        return ""

    args = {}
    tool_call = payload_data.get("toolCall")
    if isinstance(tool_call, dict):
        raw_args = tool_call.get("args")
        if isinstance(raw_args, dict):
            args = raw_args
    if not args and isinstance(payload_data.get("args"), dict):
        args = payload_data["args"]
    if not args and "target" in payload_data:
        return str(payload_data["target"]).strip()

    if not isinstance(args, dict):
        return ""

    target = (
        args.get("AbsolutePath")
        or args.get("Path")
        or args.get("path")
        or args.get("FilePath")
        or args.get("file_path")
        or args.get("target_file")
        or args.get("file")
        or args.get("target")
        or args.get("filename")
        or ""
    )
    return str(target).strip()

def strip_jsonc_comments(content: str) -> str:
    """Strips line and block comments and trailing commas from JSONC content without corrupting string values."""
    out = []
    i = 0
    n = len(content)
    in_string = False
    
    while i < n:
        char = content[i]
        next_char = content[i + 1] if i + 1 < n else ''

        if in_string:
            out.append(char)
            if char == '\\':
                if next_char:
                    out.append(next_char)
                    i += 2
                    continue
            elif char == '"':
                in_string = False
            i += 1
            continue

        # Check comment starts
        if char == '/' and next_char == '/':
            # Single line comment: skip until newline
            i += 2
            while i < n and content[i] != '\n':
                i += 1
            continue
        elif char == '/' and next_char == '*':
            # Multi-line comment: skip until */
            i += 2
            while i < n:
                if content[i] == '*' and (i + 1 < n and content[i + 1] == '/'):
                    i += 2
                    break
                i += 1
            continue
        elif char == '"':
            in_string = True
            out.append(char)
            i += 1
            continue

        # Outside strings: strip trailing comma if followed only by whitespace/comments and ']' or '}'
        if char == ',':
            k = i + 1
            is_trailing = False
            while k < n:
                c = content[k]
                nc = content[k + 1] if k + 1 < n else ''
                if c.isspace():
                    k += 1
                    continue
                elif c == '/' and nc == '/':
                    k += 2
                    while k < n and content[k] != '\n':
                        k += 1
                    continue
                elif c == '/' and nc == '*':
                    k += 2
                    while k < n:
                        if content[k] == '*' and (k + 1 < n and content[k + 1] == '/'):
                            k += 2
                            break
                        k += 1
                    continue
                elif c in [']', '}']:
                    is_trailing = True
                    break
                else:
                    break
            if is_trailing:
                i += 1
                continue

        out.append(char)
        i += 1

    return "".join(out)

def validate_code_file(file_path: Path) -> list[str]:
    """Validates source file syntax and structural delimiter balance. Returns list of error messages."""
    suffix = file_path.suffix.lower()
    errors: list[str] = []

    try:
        stat = file_path.stat()
        if stat.st_size > MAX_VALIDATION_FILE_SIZE:
            return []  # Gracefully skip massive files
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

    # 2. JSON / JSONC / GeoJSON Validation
    elif suffix in [".json", ".jsonc", ".geojson"]:
        try:
            clean_content = strip_jsonc_comments(content)
            json.loads(clean_content)
        except json.JSONDecodeError as e:
            errors.append(f"JSONDecodeError in {file_path.name}: {e.msg} (line {e.lineno}, col {e.colno})")
        except Exception as e:
            errors.append(f"JSONError in {file_path.name}: {str(e)}")

    # 3. HTML Document Validation
    elif suffix in [".html", ".htm"]:
        validator = DefensiveHTMLValidator(file_path.name)
        try:
            validator.feed(content)
            validator.close()
            if validator.errors:
                errors.extend(validator.errors)
            elif validator.tag_stack:
                last_tag, line_num = validator.tag_stack[-1]
                errors.append(f"UnclosedTag in {file_path.name}: unclosed <{last_tag}> opened at line {line_num}")
        except Exception as e:
            errors.append(f"HTMLError in {file_path.name}: {str(e)}")

    # 4. Delimiter & String Balancer for TS / JS / Rust / Go / Java / C++
    elif suffix in [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".rs", ".go", ".java", ".cpp", ".c", ".h"]:
        stack: list[tuple[str, int]] = []
        matching = {')': '(', '}': '{', ']': '['}
        is_js_ts = suffix in [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"]
        
        string_mode: str | None = None  # None, '"', "'", or '`'
        in_single_comment = False
        in_multi_comment = False
        in_regex = False
        in_regex_class = False
        last_token = ''
        
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

            # Start comments if outside strings and regex
            if string_mode is None and not in_regex:
                if char == '/' and next_char == '/':
                    in_single_comment = True
                    i += 2
                    continue
                if char == '/' and next_char == '*':
                    in_multi_comment = True
                    i += 2
                    continue

            # JS/TS Regex Literal handling
            if is_js_ts:
                if in_regex:
                    if char == '\\':
                        # Escaped regex character
                        i += 2
                        continue
                    if char == '[' and not in_regex_class:
                        in_regex_class = True
                    elif char == ']' and in_regex_class:
                        in_regex_class = False
                    elif char == '/' and not in_regex_class:
                        in_regex = False
                        last_token = '/'
                    i += 1
                    continue
                elif string_mode is None and char == '/':
                    # Check if '/' is a regex start or division
                    pre_slice = content[:i].rstrip()
                    if not pre_slice:
                        # At start of file: '/' starts regex
                        in_regex = True
                        in_regex_class = False
                        i += 1
                        continue

                    # Match preceding token: word/identifier/number, multi-char operator, or single punctuation
                    prev_token_match = re.search(r'([a-zA-Z_$][a-zA-Z0-9_$]*|\d+(?:\.\d+)?|=>|\+\+|--|===|!==|==|!=|<=|>=|&&|\|\||\?\?|<<|>>|[=([{},;:!?&|^~+*%/<> -])$', pre_slice)
                    prev_token = prev_token_match.group(1) if prev_token_match else None

                    REGEX_STARTERS = {
                        '=', '+=', '-=', '*=', '/=', '%=', '&=', '|=', '^=', '&&=', '||=', '??=',
                        '(', '[', '{', ',', ';', ':', '?',
                        '!', '~', '&', '|', '^', '+', '-', '*', '%', '<', '>',
                        '==', '!=', '===', '!==', '<=', '>=', '&&', '||', '??',
                        '=>', 'return', 'case', 'typeof', 'yield', 'await', 'throw', 'delete', 'void', 'default'
                    }
                    if prev_token in REGEX_STARTERS:
                        in_regex = True
                        in_regex_class = False
                        i += 1
                        continue

            # C++ Raw String Literal handling (e.g. R"(...)" or R"delim(...)delim")
            if suffix in [".cpp", ".c", ".h"] and string_mode is None:
                raw_cpp_match = re.match(r'^(?:u8|u|U|L)?R"([^ ()\\\t\r\n]{0,16})\(', content[i:])
                if raw_cpp_match:
                    delim = raw_cpp_match.group(1)
                    end_marker = f"){delim}\""
                    end_idx = content.find(end_marker, i + raw_cpp_match.end())
                    if end_idx != -1:
                        i = end_idx + len(end_marker)
                        last_token = '"'
                        continue
                    else:
                        line_num = content.count('\n', 0, i) + 1
                        errors.append(f"UnclosedRawString in {file_path.name}: unclosed C++ raw string literal at line {line_num}")
                        break

            # Rust Raw String Literal handling (e.g. r#"..."# or r"..." or br#"..."#)
            if suffix == ".rs" and string_mode is None:
                raw_rs_match = re.match(r'^(?:b|c|cr|br)?r(#*)"', content[i:])
                if raw_rs_match:
                    hashes = len(raw_rs_match.group(1))
                    end_marker = '"' + ('#' * hashes)
                    end_idx = content.find(end_marker, i + raw_rs_match.end())
                    if end_idx != -1:
                        i = end_idx + len(end_marker)
                        last_token = '"'
                        continue
                    else:
                        line_num = content.count('\n', 0, i) + 1
                        errors.append(f"UnclosedRawString in {file_path.name}: unclosed Rust raw string literal at line {line_num}")
                        break

            # Rust Lifetime vs Char Literal handling
            if suffix == ".rs" and string_mode is None and char == "'":
                char_match = re.match(r"""^'(\\([nrt0'"]|x[0-9a-fA-F]{2}|u\{[0-9a-fA-F]{1,6}\})|[^\\'\n])'""", content[i:])
                if char_match:
                    i += char_match.end()
                    last_token = "'"
                    continue
                lifetime_match = re.match(r"^'([a-zA-Z_][a-zA-Z0-9_]*)", content[i:])
                if lifetime_match:
                    i += lifetime_match.end()
                    continue
                i += 1
                continue

            # Template literal interpolation start in JS/TS: ${ ... }
            if is_js_ts and string_mode == '`' and char == '$' and next_char == '{':
                bs_count = 0
                k = i - 1
                while k >= 0 and content[k] == '\\':
                    bs_count += 1
                    k -= 1
                if bs_count % 2 == 0:
                    line_num = content.count('\n', 0, i) + 1
                    stack.append(('${', line_num))
                    string_mode = None
                    i += 2
                    continue

            # String literal delimiter handling
            string_delims = ['"'] if suffix == ".rs" else (['"', "'", '`'] if (is_js_ts or suffix == ".go") else ['"', "'"])
            if char in string_delims:
                bs_count = 0
                k = i - 1
                while k >= 0 and content[k] == '\\':
                    bs_count += 1
                    k -= 1
                is_escaped = (bs_count % 2 == 1)

                # In Go raw strings (`...`), backslashes do NOT escape backticks
                if suffix == ".go" and char == '`':
                    is_escaped = False

                if not is_escaped:
                    if string_mode is None:
                        string_mode = char
                    elif string_mode == char:
                        string_mode = None
                        last_token = char
                i += 1
                continue

            # Delimiter checks when outside string and regex
            if string_mode is None and not in_regex:
                if not char.isspace():
                    last_token = char

                if char in matching.values():
                    line_num = content.count('\n', 0, i) + 1
                    stack.append((char, line_num))
                elif char in matching:
                    line_num = content.count('\n', 0, i) + 1
                    expected = matching[char]
                    if not stack:
                        errors.append(f"BracketMismatch in {file_path.name}: unmatched '{char}' at line {line_num} (expected pair for 'none')")
                        break
                    top_char, top_line = stack[-1]
                    if char == '}' and top_char == '${':
                        # Closing of JS/TS template literal interpolation: return to template string mode
                        stack.pop()
                        string_mode = '`'
                    elif top_char != expected:
                        errors.append(f"BracketMismatch in {file_path.name}: unmatched '{char}' at line {line_num} (expected pair for '{top_char}')")
                        break
                    else:
                        stack.pop()

            i += 1

        if not errors and string_mode is not None:
            errors.append(f"UnclosedString in {file_path.name}: unclosed string literal ({string_mode})")

        if not errors and stack:
            unclosed_char, line_num = stack[-1]
            errors.append(f"UnclosedBracket in {file_path.name}: unclosed '{unclosed_char}' opened at line {line_num}")

    return errors

def find_source_files(target_dir: Path, max_files: int = 500) -> list[Path]:
    """Recursively collects source files while skipping ignored directories and enforcing safety bounds."""
    files: list[Path] = []
    
    for root, dirs, filenames in os.walk(target_dir):
        # Prune ignored directories in-place
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
        for f in filenames:
            p = Path(root) / f
            if p.suffix.lower() in SOURCE_EXTENSIONS:
                files.append(p)
                if len(files) >= max_files:
                    return files
    return files
