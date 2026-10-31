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
import urllib.parse
from pathlib import Path
from html.parser import HTMLParser

MAX_VALIDATION_FILE_SIZE = 2 * 1024 * 1024  # 2 MB safety threshold

VOID_HTML_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr", "!doctype",
    "path", "circle", "rect", "line", "polygon", "polyline", "ellipse",
    "use", "stop", "animate", "animatetransform", "set", "keygen", "menuitem",
    "fegaussianblur", "feoffset", "feblend", "fecolormatrix", "fecomponenttransfer",
    "fecomposite", "feconvolvematrix", "fediffuselighting", "fedisplacementmap",
    "fedistantlight", "fedropshadow", "feflood", "fefunca", "fefuncb", "fefuncg",
    "fefuncr", "feimage", "femerge", "femergenode", "femorphology", "fepointlight",
    "fespecularlighting", "fespotlight", "fetile", "feturbulence"
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

    def handle_startendtag(self, tag: str, attrs):
        # Explicit self-closing tags (<tag ... />) do not affect nesting stack
        pass

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
    ".pytest_cache",
    ".hypothesis",
    "coverage",
    ".nyc_output",
    "vendor",
    ".gemini",
    ".agents",
    "bower_components",
}

SOURCE_EXTENSIONS = {
    ".py",
    ".pyi",
    ".ipynb",
    ".json",
    ".jsonc",
    ".json5",
    ".geojson",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".mts",
    ".cts",
    ".mdx",
    ".vue",
    ".svelte",
    ".astro",
    ".rs",
    ".go",
    ".java",
    ".kt",
    ".kts",
    ".scala",
    ".cpp",
    ".cc",
    ".cxx",
    ".c",
    ".h",
    ".hpp",
    ".hxx",
    ".hh",
    ".cs",
    ".swift",
    ".dart",
    ".php",
    ".rb",
    ".lua",
    ".zig",
    ".nim",
    ".ex",
    ".exs",
    ".clj",
    ".cljs",
    ".erl",
    ".jl",
    ".html",
    ".htm",
    ".xml",
    ".svg",
    ".plist",
    ".xaml",
    ".xib",
    ".graphql",
    ".gql",
    ".proto",
    ".toml",
    ".md",
    ".markdown",
    ".css",
    ".scss",
    ".less",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".psm1",
    ".psd1",
    ".sql",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".conf",
    ".properties",
    ".env",
    ".prisma",
    ".sol",
    ".tf",
    ".hcl",
}

ENV_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.test",
    ".env.staging",
    ".env.example",
    ".env.sample",
    ".env.defaults"
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
        raw_args = tool_call.get("args") or tool_call.get("input") or tool_call.get("parameters")
        if isinstance(raw_args, dict):
            args = raw_args
    if not args and isinstance(payload_data.get("toolUse"), dict):
        tool_use = payload_data["toolUse"]
        raw_args = tool_use.get("input") or tool_use.get("args") or tool_use.get("parameters")
        if isinstance(raw_args, dict):
            args = raw_args
    if not args and isinstance(payload_data.get("tool_input"), dict):
        args = payload_data["tool_input"]
    if not args and isinstance(payload_data.get("parameters"), dict):
        args = payload_data["parameters"]
    if not args and isinstance(payload_data.get("params"), dict):
        args = payload_data["params"]
    if not args and isinstance(payload_data.get("arguments"), dict):
        args = payload_data["arguments"]
    if not args and isinstance(payload_data.get("args"), dict):
        args = payload_data["args"]
    if not args and isinstance(payload_data.get("input"), dict):
        args = payload_data["input"]

    if not args:
        args = payload_data

    target = (
        args.get("AbsolutePath")
        or args.get("Path")
        or args.get("path")
        or args.get("FilePath")
        or args.get("filePath")
        or args.get("file_path")
        or args.get("targetPath")
        or args.get("target_path")
        or args.get("target_file")
        or args.get("sourcePath")
        or args.get("source_path")
        or args.get("source_file")
        or args.get("file")
        or args.get("target")
        or args.get("filename")
        or ""
    )
    target_str = str(target).strip()
    if target_str.startswith("file://"):
        target_str = urllib.parse.unquote(target_str[7:])
        if target_str.startswith("localhost/"):
            rest = target_str[10:]
            if re.match(r"^[a-zA-Z]:/", rest):
                target_str = rest
            else:
                target_str = "/" + rest
        elif re.match(r"^/[a-zA-Z]:/", target_str):
            target_str = target_str[1:]
    return target_str

def resolve_target_file(payload_data: dict | str) -> str:
    """Extracts and resolves target file path against payload workspace paths if relative."""
    if isinstance(payload_data, str):
        try:
            payload_data = json.loads(payload_data)
        except Exception:
            return ""

    if not isinstance(payload_data, dict):
        return ""

    target = extract_target_file(payload_data)
    if not target:
        return ""

    try:
        target_path = Path(target).expanduser()
        if target_path.is_file():
            return str(target_path)
    except (OSError, ValueError, RuntimeError):
        target_path = None

    # Collect candidate workspace base paths
    candidates = []
    ws_list = payload_data.get("workspacePaths", [])
    if isinstance(ws_list, list):
        candidates.extend(ws_list)
    elif isinstance(ws_list, str) and ws_list:
        candidates.append(ws_list)

    for key in ["workspacePath", "cwd", "workspace", "rootPath", "projectRoot"]:
        val = payload_data.get(key)
        if isinstance(val, str) and val and val not in candidates:
            candidates.append(val)

    for ws in candidates:
        try:
            candidate_file = (Path(ws).expanduser() / target).resolve()
            if candidate_file.is_file():
                return str(candidate_file)
        except (OSError, ValueError, RuntimeError):
            continue

    # Try resolving relative to current working directory
    try:
        cwd_candidate = (Path.cwd() / target).resolve()
        if cwd_candidate.is_file():
            return str(cwd_candidate)
    except (OSError, RuntimeError, ValueError):
        cwd_candidate = None

    return target

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
    file_name = file_path.name.lower()
    errors: list[str] = []

    try:
        stat = file_path.stat()
        if stat.st_size > MAX_VALIDATION_FILE_SIZE:
            return []  # Gracefully skip massive files
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        return [f"ReadError in {file_path.name}: {str(e)}"]

    # 1. Python AST Validation (.py, .pyi)
    if suffix in [".py", ".pyi"]:
        try:
            ast.parse(content, filename=str(file_path))
        except (SyntaxError, ValueError) as e:
            lineno = getattr(e, 'lineno', None)
            offset = getattr(e, 'offset', None)
            msg = getattr(e, 'msg', str(e))
            line_info = f" (line {lineno}" + (f", col {offset}" if offset else "") + ")" if lineno else ""
            errors.append(f"SyntaxError in {file_path.name}: {msg}{line_info}")

    # 1b. Jupyter Notebook Validation (.ipynb)
    elif suffix == ".ipynb":
        try:
            nb_data = json.loads(content)
            if not isinstance(nb_data, dict):
                errors.append(f"NotebookError in {file_path.name}: notebook root must be a JSON object")
            else:
                cells = nb_data.get("cells", [])
                if isinstance(cells, list):
                    for cell_idx, cell in enumerate(cells, 1):
                        if isinstance(cell, dict) and cell.get("cell_type") == "code":
                            raw_src = cell.get("source", "")
                            src = "".join(raw_src) if isinstance(raw_src, list) else str(raw_src)
                            # Strip IPython magics (% and !) before AST parse
                            clean_src_lines = []
                            for line in src.splitlines():
                                stripped_line = line.strip()
                                if stripped_line.startswith("%") or stripped_line.startswith("!"):
                                    clean_src_lines.append("# " + line)
                                else:
                                    clean_src_lines.append(line)
                            clean_src = "\n".join(clean_src_lines)
                            try:
                                ast.parse(clean_src, filename=f"{file_path.name}:cell_{cell_idx}")
                            except (SyntaxError, ValueError) as e:
                                lineno = getattr(e, 'lineno', None)
                                line_info = f", line {lineno}" if lineno else ""
                                msg = getattr(e, 'msg', str(e))
                                errors.append(f"NotebookSyntaxError in {file_path.name} (cell {cell_idx}{line_info}): {msg}")
        except json.JSONDecodeError as e:
            errors.append(f"JSONDecodeError in {file_path.name}: {e.msg} (line {e.lineno}, col {e.colno})")
        except Exception as e:
            errors.append(f"NotebookError in {file_path.name}: {str(e)}")

    # 2. JSON / JSONC / JSON5 / GeoJSON Validation
    elif suffix in [".json", ".jsonc", ".json5", ".geojson"]:
        if suffix == ".json5":
            # 1. Try native json5 / pyjson5 modules if available
            parsed_json5 = False
            for mod_name in ("json5", "pyjson5"):
                try:
                    mod = __import__(mod_name)
                    try:
                        mod.loads(content)
                        parsed_json5 = True
                        break
                    except Exception as e:
                        errors.append(f"JSON5DecodeError in {file_path.name}: {str(e)}")
                        parsed_json5 = True
                        break
                except ImportError:
                    continue

            if not parsed_json5:
                # 2. Defensive JSON5 normalizer & structural fallback
                try:
                    clean = strip_jsonc_comments(content)
                    # Normalize multiline string escapes: \\\n -> \n
                    clean = re.sub(r'\\(?:\r?\n)', '', clean)
                    # Convert signed hex integers: -0x10 -> -16, +0x10 -> 16, 0xFF -> 255
                    clean = re.sub(
                        r'([+\-]?)0[xX]([0-9a-fA-F]+)\b',
                        lambda m: ('-' if m.group(1) == '-' else '') + str(int(m.group(2), 16)),
                        clean
                    )
                    # Convert single-quoted strings to valid JSON double-quoted strings first
                    # to prevent unquoted key regex from corrupting colons inside single-quoted strings
                    def _replace_squote(m):
                        inner = m.group(1).replace(r"\'", "'").replace(r'\"', '"').replace('"', r'\"')
                        return f'"{inner}"'
                    clean = re.sub(r"'((?:\\.|[^'\\])*)'", _replace_squote, clean)
                    # Quote unquoted property identifiers (e.g. key: "val")
                    clean = re.sub(r'(?<=[{,\s])([a-zA-Z_$][a-zA-Z0-9_$]*)\s*:', r'"\1":', clean)
                    # Normalize leading and trailing decimals with optional sign
                    clean = re.sub(r'(?<=[\[{\s,:\-])([+\-])\.(\d+)', lambda m: ('-0.' if m.group(1) == '-' else '0.') + m.group(2), clean)
                    clean = re.sub(r'(?<=[\[{\s,:\-])\.(\d+)', r'0.\1', clean)
                    clean = re.sub(r'(?<=[\[{\s,:\-])(\d+)\.(?=[\]},\s:]|$)', r'\1.0', clean)
                    # Strip leading + on numeric values
                    clean = re.sub(r'(?<=[\[{\s,:\-])\+(\d+(?:\.\d+)?)', r'\1', clean)
                    # Normalize JSON5 NaN / Infinity
                    clean = re.sub(r'(?<=[\[{\s,:\-])([+\-]?)Infinity\b', r'1e999', clean)
                    clean = re.sub(r'(?<=[\[{\s,:\-])NaN\b', r'0', clean)
                    # Strip trailing commas before closing braces
                    clean = re.sub(r',(\s*[\]}])', r'\1', clean)
                    json.loads(clean)
                except Exception:
                    # Secondary structural delimiter check for complex JSON5 syntax
                    stack: list[tuple[str, int]] = []
                    matching = {'}': '{', ']': '['}
                    in_squote = False
                    in_dquote = False
                    for line_idx, line in enumerate(content.splitlines(), 1):
                        i = 0
                        n = len(line)
                        while i < n:
                            c = line[i]
                            nc = line[i + 1] if i + 1 < n else ''
                            if not in_squote and not in_dquote and c == '/' and nc == '/':
                                break
                            if in_squote:
                                if c == '\\':
                                    i += 2
                                    continue
                                if c == "'":
                                    in_squote = False
                                i += 1
                                continue
                            if in_dquote:
                                if c == '\\':
                                    i += 2
                                    continue
                                if c == '"':
                                    in_dquote = False
                                i += 1
                                continue
                            if c == "'":
                                in_squote = True
                            elif c == '"':
                                in_dquote = True
                            elif c in matching.values():
                                stack.append((c, line_idx))
                            elif c in matching:
                                if not stack:
                                    errors.append(f"BracketMismatch in {file_path.name}: unmatched '{c}' at line {line_idx}")
                                    break
                                top_c, top_line = stack.pop()
                                if top_c != matching[c]:
                                    errors.append(f"BracketMismatch in {file_path.name}: unmatched '{c}' at line {line_idx} (expected pair for '{top_c}' opened at line {top_line})")
                                    break
                            i += 1
                        if errors:
                            break
                    if in_squote or in_dquote:
                        errors.append(f"UnclosedString in {file_path.name}: unclosed string literal in JSON5")
                    elif stack and not errors:
                        top_c, top_line = stack[-1]
                        errors.append(f"UnclosedBracket in {file_path.name}: unclosed '{top_c}' opened at line {top_line}")
        else:
            is_jsonc = (
                suffix in [".jsonc", ".sublime-settings", ".sublime-keymap"]
                or file_name.startswith("tsconfig")
                or file_name.startswith("jsconfig")
                or file_name in [".eslintrc.json", ".prettierrc.json", "settings.json", "launch.json", "tasks.json", "extensions.json", "keybindings.json"]
            )
            try:
                if is_jsonc:
                    clean_content = strip_jsonc_comments(content)
                    json.loads(clean_content)
                else:
                    json.loads(content)
            except json.JSONDecodeError as e:
                errors.append(f"JSONDecodeError in {file_path.name}: {e.msg} (line {e.lineno}, col {e.colno})")
            except Exception as e:
                errors.append(f"JSONError in {file_path.name}: {str(e)}")

    # 3. HTML / XHTML Document Validation
    elif suffix in [".html", ".htm", ".xhtml"]:
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

    # 3b. XML / SVG / Plist / XAML / XIB Validation
    elif suffix in [".xml", ".svg", ".plist", ".xaml", ".xib"]:
        try:
            import xml.etree.ElementTree as ET
            ET.fromstring(content)
        except ET.ParseError as e:
            # Check with DefensiveHTMLValidator as fallback for DOCTYPE or entity tolerance
            validator = DefensiveHTMLValidator(file_path.name)
            try:
                validator.feed(content)
                validator.close()
                if validator.errors:
                    errors.append(f"XMLSyntaxError in {file_path.name}: {str(e)}")
                elif validator.tag_stack:
                    last_tag, line_num = validator.tag_stack[-1]
                    errors.append(f"UnclosedTag in {file_path.name}: unclosed <{last_tag}> opened at line {line_num}")
            except Exception:
                errors.append(f"XMLSyntaxError in {file_path.name}: {str(e)}")
        except Exception as e:
            errors.append(f"XMLError in {file_path.name}: {str(e)}")

    # 3c. Vue / Svelte / Astro SFC Component Validation
    elif suffix in [".vue", ".svelte", ".astro"]:
        html_content = content
        if suffix == ".astro" and html_content.startswith("---"):
            # Strip Astro frontmatter (--- ... ---) to prevent TypeScript generics (e.g. Array<string>) from triggering HTML tag errors
            end_fm = html_content.find("\n---", 3)
            if end_fm != -1:
                fm_lines = html_content[:end_fm + 4].count("\n")
                html_content = ("\n" * fm_lines) + html_content[end_fm + 4:]
        validator = DefensiveHTMLValidator(file_path.name)
        try:
            validator.feed(html_content)
            validator.close()
            if validator.errors:
                errors.extend(validator.errors)
            elif validator.tag_stack:
                last_tag, line_num = validator.tag_stack[-1]
                errors.append(f"UnclosedTag in {file_path.name}: unclosed <{last_tag}> opened at line {line_num}")
        except Exception as e:
            errors.append(f"ComponentError in {file_path.name}: {str(e)}")

    # 4. Delimiter & String Balancer for Polyglot Languages (TS/JS/Rust/Go/Java/Kotlin/Scala/C++/C#/Swift/Dart/PHP/Ruby/Lua/Zig/Nim/Elixir/Clojure/Julia/Prisma/Solidity/Terraform)
    elif suffix in [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts", ".rs", ".go", ".java", ".kt", ".kts", ".scala", ".cpp", ".cc", ".cxx", ".c", ".h", ".hpp", ".hxx", ".hh", ".cs", ".swift", ".dart", ".php", ".rb", ".lua", ".zig", ".nim", ".ex", ".exs", ".clj", ".cljs", ".erl", ".jl", ".prisma", ".sol", ".tf", ".hcl"]:
        stack: list[tuple[str, int]] = []
        matching = {')': '(', '}': '{', ']': '['}
        is_js_ts = suffix in [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"]
        
        string_mode: str | None = None  # None, '"', "'", or '`'
        in_single_comment = False
        in_multi_comment = False
        in_ruby_block_comment = False
        swift_comment_depth = 0
        in_regex = False
        in_regex_class = False
        last_token = ''
        
        i = 0
        n = len(content)

        while i < n:
            char = content[i]
            next_char = content[i + 1] if i + 1 < n else ''

            # Ruby =begin ... =end block comments at line start
            if suffix == ".rb":
                if in_ruby_block_comment:
                    if (i == 0 or content[i - 1] == '\n') and content.startswith("=end", i):
                        in_ruby_block_comment = False
                        i += 4
                        continue
                    i += 1
                    continue
                elif (i == 0 or content[i - 1] == '\n') and content.startswith("=begin", i):
                    in_ruby_block_comment = True
                    i += 6
                    continue

            # Comment handling
            if in_single_comment:
                if char == '\n':
                    in_single_comment = False
                i += 1
                continue

            # Swift nested block comments
            if suffix == ".swift" and swift_comment_depth > 0:
                if char == '/' and next_char == '*':
                    swift_comment_depth += 1
                    i += 2
                    continue
                elif char == '*' and next_char == '/':
                    swift_comment_depth -= 1
                    i += 2
                    continue
                i += 1
                continue

            if in_multi_comment:
                if suffix == ".lua":
                    if char == ']' and next_char == ']':
                        in_multi_comment = False
                        i += 2
                        continue
                elif suffix == ".jl":
                    if char == '=' and next_char == '#':
                        in_multi_comment = False
                        i += 2
                        continue
                elif suffix == ".nim":
                    if char == ']' and next_char == '#':
                        in_multi_comment = False
                        i += 2
                        continue
                else:
                    if char == '*' and next_char == '/':
                        in_multi_comment = False
                        i += 2
                        continue
                i += 1
                continue

            # Start comments if outside strings and regex
            if string_mode is None and not in_regex:
                # Zig multiline string literals (\\...)
                if suffix == ".zig" and char == '\\' and next_char == '\\':
                    nl_idx = content.find('\n', i + 2)
                    if nl_idx != -1:
                        i = nl_idx + 1
                    else:
                        i = n
                    continue

                # Clojure character escapes outside strings (\(, \), \[, \], \{, \}, etc.)
                if suffix in [".clj", ".cljs"] and char == '\\':
                    if next_char in "()[]{}\"':;,":
                        i += 2
                        continue
                    clj_char_match = re.match(r"^\\([a-zA-Z0-9]+)", content[i:])
                    if clj_char_match:
                        i += clj_char_match.end()
                        continue

                # Lua comments
                if suffix == ".lua":
                    if content.startswith("--[[", i):
                        in_multi_comment = True
                        i += 4
                        continue
                    elif char == '-' and next_char == '-':
                        in_single_comment = True
                        i += 2
                        continue
                # Julia comments
                elif suffix == ".jl":
                    if content.startswith("#=", i):
                        in_multi_comment = True
                        i += 2
                        continue
                    elif char == '#':
                        in_single_comment = True
                        i += 1
                        continue
                # Nim comments
                elif suffix == ".nim":
                    if content.startswith("#[", i):
                        in_multi_comment = True
                        i += 2
                        continue
                    elif char == '#':
                        in_single_comment = True
                        i += 1
                        continue
                # Swift comments
                elif suffix == ".swift":
                    if char == '/' and next_char == '*':
                        swift_comment_depth = 1
                        i += 2
                        continue
                    elif char == '/' and next_char == '/':
                        in_single_comment = True
                        i += 2
                        continue
                # Ruby / PHP / Elixir / Terraform hash line comments
                elif suffix in [".rb", ".php", ".ex", ".exs", ".tf", ".hcl"] and char == '#':
                    in_single_comment = True
                    i += 1
                    continue
                # Clojure semicolon line comments
                elif suffix in [".clj", ".cljs"] and char == ';':
                    in_single_comment = True
                    i += 1
                    continue
                # Erlang percent line comments
                elif suffix == ".erl" and char == '%':
                    in_single_comment = True
                    i += 1
                    continue
                # Standard C-family comments
                elif char == '/' and next_char == '/':
                    in_single_comment = True
                    i += 2
                    continue
                elif char == '/' and next_char == '*':
                    in_multi_comment = True
                    i += 2
                    continue

            # JS/TS Regex Literal handling
            if is_js_ts:
                if in_regex:
                    if char == '\n':
                        # Unescaped newline terminates regex literal in ECMAScript
                        line_num = content.count('\n', 0, i) + 1
                        errors.append(f"UnclosedRegex in {file_path.name}: unclosed regular expression literal at line {line_num}")
                        in_regex = False
                        in_regex_class = False
                        i += 1
                        continue
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
                    # Match preceding token in bounded lookback window
                    pre_slice = content[max(0, i - 200):i].rstrip()
                    if not pre_slice:
                        # At start of file: '/' starts regex
                        in_regex = True
                        in_regex_class = False
                        i += 1
                        continue

                    # Match preceding token: word/identifier/number, multi-char operator, spread, or single punctuation
                    prev_token_match = re.search(r'([a-zA-Z_$][a-zA-Z0-9_$]*|\d+(?:\.\d+)?|\.\.\.|\.|=>|\+\+|--|===|!==|==|!=|<=|>=|&&|\|\||\?\?|<<|>>|[=([{},;:!?&|^~+*%/<> -])$', pre_slice)
                    prev_token = prev_token_match.group(1) if prev_token_match else None

                    REGEX_STARTERS = {
                        '=', '+=', '-=', '*=', '/=', '%=', '&=', '|=', '^=', '&&=', '||=', '??=',
                        '(', '[', '{', ',', ';', ':', '?',
                        '!', '~', '&', '|', '^', '+', '-', '*', '%', '<', '>',
                        '==', '!=', '===', '!==', '<=', '>=', '&&', '||', '??',
                        '=>', '...', 'return', 'case', 'typeof', 'yield', 'await', 'throw', 'delete', 'void', 'default',
                        'in', 'of', 'instanceof', 'do', 'else'
                    }
                    if prev_token in REGEX_STARTERS:
                        in_regex = True
                        in_regex_class = False
                        i += 1
                        continue

            # Lua Multiline Raw String: [[ ... ]]
            if suffix == ".lua" and string_mode is None:
                if content.startswith("[[", i):
                    end_idx = content.find("]]", i + 2)
                    if end_idx != -1:
                        i = end_idx + 2
                        last_token = ']'
                        continue
                    else:
                        line_num = content.count('\n', 0, i) + 1
                        errors.append(f"UnclosedRawString in {file_path.name}: unclosed Lua multiline string literal at line {line_num}")
                        break

            # C++ Raw String Literal handling (e.g. R"(...)" or R"delim(...)delim")
            if suffix in [".cpp", ".cc", ".cxx", ".c", ".h", ".hpp", ".hxx", ".hh"] and string_mode is None:
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

            # C# 11+ Multiline Raw String Literal handling: """...""" (at least 3 double quotes)
            if suffix == ".cs" and string_mode is None:
                raw_cs_match = re.match(r'^("{3,})', content[i:])
                if raw_cs_match:
                    quote_seq = raw_cs_match.group(1)
                    end_idx = content.find(quote_seq, i + len(quote_seq))
                    if end_idx != -1:
                        i = end_idx + len(quote_seq)
                        last_token = '"'
                        continue
                    else:
                        line_num = content.count('\n', 0, i) + 1
                        errors.append(f"UnclosedRawString in {file_path.name}: unclosed C# raw string literal at line {line_num}")
                        break

            # C# Verbatim String Literal handling: @"...", $@"... ", or @$"..." (escaped with "")
            if suffix == ".cs" and string_mode is None and (content.startswith('@"', i) or content.startswith('$@"', i) or content.startswith('@$"', i)):
                skip_len = 3 if (content.startswith('$@"', i) or content.startswith('@$"', i)) else 2
                i += skip_len
                closed = False
                while i < n:
                    if content[i] == '"':
                        if i + 1 < n and content[i + 1] == '"':
                            i += 2
                            continue
                        closed = True
                        i += 1
                        break
                    i += 1
                if not closed:
                    line_num = content.count('\n', 0, i) + 1
                    errors.append(f"UnclosedString in {file_path.name}: unclosed C# verbatim string literal at line {line_num}")
                    break
                last_token = '"'
                continue

            # Dart Raw String Literal handling (e.g. r"...", r'...', r"""...""", r'''...''')
            if suffix == ".dart" and string_mode is None:
                dart_raw_triple = re.match(r'^r("""|\'\'\')', content[i:])
                if dart_raw_triple:
                    quote_seq = dart_raw_triple.group(1)
                    end_idx = content.find(quote_seq, i + len(dart_raw_triple.group(0)))
                    if end_idx != -1:
                        i = end_idx + len(quote_seq)
                        last_token = quote_seq[0]
                        continue
                    else:
                        line_num = content.count('\n', 0, i) + 1
                        errors.append(f"UnclosedString in {file_path.name}: unclosed Dart multiline raw string literal at line {line_num}")
                        break

                dart_raw_single = re.match(r'^r(["\'])', content[i:])
                if dart_raw_single:
                    quote_char = dart_raw_single.group(1)
                    end_idx = content.find(quote_char, i + 2)
                    nl_idx = content.find('\n', i + 2)
                    if end_idx != -1 and (nl_idx == -1 or end_idx < nl_idx):
                        i = end_idx + 1
                        last_token = quote_char
                        continue

            # PHP Heredoc & Nowdoc handling (e.g. <<<EOF ... EOF; or <<<'NOWDOC' ... NOWDOC;)
            if suffix == ".php" and string_mode is None and not in_regex:
                php_hd_match = re.match(r'^<<<\s*([\'"]?)([a-zA-Z_][a-zA-Z0-9_]*)\1', content[i:])
                if php_hd_match:
                    delim = php_hd_match.group(2)
                    end_hd = re.search(r'\n[ \t]*' + re.escape(delim) + r'(?:;|\n|,|\))', content[i + php_hd_match.end():])
                    if end_hd:
                        i = i + php_hd_match.end() + end_hd.end()
                        last_token = delim
                        continue
                    else:
                        line_num = content.count('\n', 0, i) + 1
                        errors.append(f"UnclosedHeredoc in {file_path.name}: unclosed PHP heredoc/nowdoc '{delim}' opened at line {line_num}")
                        break

            # Ruby Heredoc handling (e.g. <<~SQL ... SQL, <<-EOF ... EOF, <<'DELIM' ... DELIM, <<EOF ... EOF)
            if suffix == ".rb" and string_mode is None and not in_regex:
                rb_hd_match = re.match(r'^<<([-~]?)\s*([\'"`]?)([a-zA-Z_][a-zA-Z0-9_]*)\2', content[i:])
                if rb_hd_match:
                    has_modifier = rb_hd_match.group(1) != "" or rb_hd_match.group(2) != ""
                    is_heredoc = has_modifier
                    if not is_heredoc:
                        pre = content[max(0, i - 50):i].rstrip()
                        if not pre or pre[-1] in "=([,{":
                            is_heredoc = True
                    if is_heredoc:
                        delim = rb_hd_match.group(3)
                        end_hd = re.search(r'\n[ \t]*' + re.escape(delim) + r'(?:\n|$)', content[i + rb_hd_match.end():])
                        if end_hd:
                            i = i + rb_hd_match.end() + end_hd.end()
                            last_token = delim
                            continue
                        else:
                            line_num = content.count('\n', 0, i) + 1
                            errors.append(f"UnclosedHeredoc in {file_path.name}: unclosed Ruby heredoc '{delim}' opened at line {line_num}")
                            break

            # Triple-Quoted Multiline Strings in Java / Kotlin / Scala / Swift / Dart / C# / Nim / Elixir: """...""" or '''...'''
            if suffix in [".java", ".kt", ".kts", ".scala", ".swift", ".dart", ".cs", ".nim", ".ex", ".exs"] and string_mode is None:
                if content.startswith('"""', i) or (suffix in [".dart", ".nim", ".ex", ".exs"] and content.startswith("'''", i)):
                    quote_seq = '"""' if content.startswith('"""', i) else "'''"
                    end_idx = content.find(quote_seq, i + 3)
                    if end_idx != -1:
                        i = end_idx + 3
                        last_token = quote_seq[0]
                        continue
                    else:
                        line_num = content.count('\n', 0, i) + 1
                        errors.append(f"UnclosedString in {file_path.name}: unclosed multiline string literal at line {line_num}")
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
                        errors.append(f"BracketMismatch in {file_path.name}: unmatched '{char}' at line {line_num} (expected pair for '{top_char}' opened at line {top_line})")
                        break
                    else:
                        stack.pop()

            i += 1

        if not errors and swift_comment_depth > 0:
            errors.append(f"UnclosedComment in {file_path.name}: unclosed Swift nested block comment")

        if not errors and in_multi_comment:
            errors.append(f"UnclosedComment in {file_path.name}: unclosed multi-line block comment")

        if not errors and in_ruby_block_comment:
            errors.append(f"UnclosedComment in {file_path.name}: unclosed Ruby =begin block comment")

        if not errors and string_mode is not None:
            errors.append(f"UnclosedString in {file_path.name}: unclosed string literal ({string_mode})")

        if not errors and is_js_ts and in_regex:
            errors.append(f"UnclosedRegex in {file_path.name}: unclosed regular expression literal")

        if not errors and stack:
            unclosed_char, line_num = stack[-1]
            errors.append(f"UnclosedBracket in {file_path.name}: unclosed '{unclosed_char}' opened at line {line_num}")

    # 5. TOML Configuration Validation
    elif suffix == ".toml":
        tomllib_mod = None
        try:
            import tomllib as tomllib_mod
        except ImportError:
            try:
                import tomli as tomllib_mod
            except ImportError:
                tomllib_mod = None

        if tomllib_mod is not None:
            try:
                tomllib_mod.loads(content)
            except Exception as e:
                errors.append(f"TOMLDecodeError in {file_path.name}: {str(e)}")
        else:
            # Dependency-free structural fallback for TOML: validate brackets and multiline/single-line strings
            stack: list[tuple[str, int]] = []
            matching = {')': '(', '}': '{', ']': '['}
            i = 0
            n = len(content)
            string_mode: str | None = None
            in_comment = False

            while i < n:
                char = content[i]
                next_char = content[i + 1] if i + 1 < n else ''

                if in_comment:
                    if char == '\n':
                        in_comment = False
                    i += 1
                    continue

                if string_mode is None:
                    if char == '#':
                        in_comment = True
                        i += 1
                        continue

                    # Multiline Basic / Literal Strings: """...""" or '''...'''
                    if content.startswith('"""', i):
                        end_idx = content.find('"""', i + 3)
                        if end_idx != -1:
                            i = end_idx + 3
                            continue
                        else:
                            line_num = content.count('\n', 0, i) + 1
                            errors.append(f"UnclosedString in {file_path.name}: unclosed multiline basic string literal at line {line_num}")
                            break
                    elif content.startswith("'''", i):
                        end_idx = content.find("'''", i + 3)
                        if end_idx != -1:
                            i = end_idx + 3
                            continue
                        else:
                            line_num = content.count('\n', 0, i) + 1
                            errors.append(f"UnclosedString in {file_path.name}: unclosed multiline literal string at line {line_num}")
                            break
                    elif char in ['"', "'"]:
                        string_mode = char
                        i += 1
                        continue

                    if char in matching.values():
                        line_num = content.count('\n', 0, i) + 1
                        stack.append((char, line_num))
                    elif char in matching:
                        line_num = content.count('\n', 0, i) + 1
                        expected = matching[char]
                        if not stack:
                            errors.append(f"BracketMismatch in {file_path.name}: unmatched '{char}' at line {line_num} (expected pair for 'none')")
                            break
                        top_char, top_line = stack.pop()
                        if top_char != expected:
                            errors.append(f"BracketMismatch in {file_path.name}: unmatched '{char}' at line {line_num} (expected pair for '{top_char}' opened at line {top_line})")
                            break
                else:
                    if char == '\n':
                        line_num = content.count('\n', 0, i)
                        errors.append(f"UnclosedString in {file_path.name}: unclosed string literal ({string_mode}) at line {line_num}")
                        break
                    if string_mode == '"' and char == '\\':
                        i += 2
                        continue
                    if char == string_mode:
                        string_mode = None
                i += 1

            if not errors and string_mode is not None:
                errors.append(f"UnclosedString in {file_path.name}: unclosed string literal ({string_mode})")
            if not errors and stack:
                top_char, top_line = stack[-1]
                errors.append(f"UnclosedBracket in {file_path.name}: unclosed '{top_char}' opened at line {top_line}")

    # 6. YAML Configuration Validation
    elif suffix in [".yaml", ".yml"]:
        try:
            import yaml
            # Support both single-document and multi-document YAML files
            for _ in yaml.safe_load_all(content):
                pass
        except ImportError:
            stack: list[tuple[str, int]] = []
            matching = {')': '(', '}': '{', ']': '['}
            in_dquote = False
            in_squote = False
            in_block_scalar = False
            block_scalar_indent = 0

            for line_idx, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue

                line_indent = len(line) - len(line.lstrip())

                if in_block_scalar:
                    if line_indent > block_scalar_indent:
                        # Inside multiline block scalar literal/folded text: skip bracket balancing
                        continue
                    else:
                        in_block_scalar = False

                # Check if current line initiates a multiline block scalar (e.g. description: | or notes: >)
                if re.search(r':\s*[|>][+-]?\s*(?:#.*)?$', line):
                    in_block_scalar = True
                    block_scalar_indent = line_indent

                i = 0
                n = len(line)
                while i < n:
                    char = line[i]
                    prev_char = line[i - 1] if i > 0 else ' '
                    next_char = line[i + 1] if i + 1 < n else ' '

                    if in_dquote:
                        if char == '\\':
                            i += 2
                            continue
                        if char == '"':
                            in_dquote = False
                        i += 1
                        continue

                    if in_squote:
                        # In YAML single-quoted strings, '' escapes a single quote
                        if char == "'" and next_char == "'":
                            i += 2
                            continue
                        if char == "'":
                            in_squote = False
                        i += 1
                        continue

                    # Outside quotes:
                    if char == "#" and (i == 0 or prev_char.isspace()):
                        break

                    if char == '"':
                        in_dquote = True
                        i += 1
                        continue

                    if char == "'":
                        # In YAML, a single quote starts a quoted scalar if at start of value or after delimiters
                        if prev_char in " \t:,-[{(|>\n":
                            in_squote = True
                            i += 1
                            continue
                        # Otherwise it is a plain unquoted apostrophe (e.g. It's)

                    if char in matching.values():
                        stack.append((char, line_idx))
                    elif char in matching:
                        if not stack:
                            errors.append(f"BracketMismatch in {file_path.name}: unmatched '{char}' at line {line_idx} (expected pair for 'none')")
                            break
                        top_char, top_line = stack.pop()
                        if top_char != matching[char]:
                            errors.append(f"BracketMismatch in {file_path.name}: unmatched '{char}' at line {line_idx} (expected pair for '{top_char}' opened at line {top_line})")
                            break
                    i += 1
                if errors:
                    break
            if not errors and stack:
                top_char, top_line = stack[-1]
                errors.append(f"UnclosedBracket in {file_path.name}: unclosed '{top_char}' opened at line {top_line}")
        except Exception as e:
            errors.append(f"YAMLError in {file_path.name}: {str(e)}")

    # 7. Markdown Document Validation (Fenced Code Blocks & Frontmatter)
    elif suffix in [".md", ".markdown", ".mdx"]:
        lines = content.splitlines()
        in_fence = None
        fence_line = 0
        in_frontmatter = False
        frontmatter_line = 0

        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if idx == 1 and stripped == "---":
                in_frontmatter = True
                frontmatter_line = idx
                continue
            elif in_frontmatter and stripped == "---":
                in_frontmatter = False
                continue

            # Fenced code block check (CommonMark compliant: closing fence must match opening fence char and length)
            if stripped.startswith("```") or stripped.startswith("~~~~"):
                fence_char = stripped[0]
                fence_len = len(stripped) - len(stripped.lstrip(fence_char))
                current_fence = fence_char * fence_len
                if in_fence is None:
                    in_fence = current_fence
                    fence_line = idx
                elif fence_char == in_fence[0]:
                    closing_tail = stripped[fence_len:].strip()
                    if not closing_tail and fence_len >= len(in_fence):
                        in_fence = None

        if in_frontmatter:
            errors.append(f"UnclosedFrontmatter in {file_path.name}: unclosed '---' frontmatter opened at line {frontmatter_line}")
        if in_fence is not None:
            errors.append(f"UnclosedCodeBlock in {file_path.name}: unclosed code block fence '{in_fence}' opened at line {fence_line}")

    # 8. CSS / SCSS / LESS Stylesheet Validation
    elif suffix in [".css", ".scss", ".less"]:
        stack: list[tuple[str, int]] = []
        matching = {')': '(', '}': '{', ']': '['}
        in_multi_comment = False
        string_mode: str | None = None
        i = 0
        n = len(content)

        while i < n:
            char = content[i]
            next_char = content[i + 1] if i + 1 < n else ''

            if in_multi_comment:
                if char == '*' and next_char == '/':
                    in_multi_comment = False
                    i += 2
                    continue
                i += 1
                continue

            if string_mode is None:
                if char == '/' and next_char == '*':
                    in_multi_comment = True
                    i += 2
                    continue
                if suffix in [".scss", ".less"] and char == '/' and next_char == '/':
                    i += 2
                    while i < n and content[i] != '\n':
                        i += 1
                    continue

            if char in ['"', "'"]:
                bs_count = 0
                k = i - 1
                while k >= 0 and content[k] == '\\':
                    bs_count += 1
                    k -= 1
                if bs_count % 2 == 0:
                    if string_mode is None:
                        string_mode = char
                    elif string_mode == char:
                        string_mode = None
                i += 1
                continue

            if string_mode is None and not in_multi_comment:
                if char in matching.values():
                    line_num = content.count('\n', 0, i) + 1
                    stack.append((char, line_num))
                elif char in matching:
                    line_num = content.count('\n', 0, i) + 1
                    expected = matching[char]
                    if not stack:
                        errors.append(f"BracketMismatch in {file_path.name}: unmatched '{char}' at line {line_num} (expected pair for 'none')")
                        break
                    top_char, top_line = stack.pop()
                    if top_char != expected:
                        errors.append(f"BracketMismatch in {file_path.name}: unmatched '{char}' at line {line_num} (expected pair for '{top_char}' opened at line {top_line})")
                        break

            i += 1

        if not errors and in_multi_comment:
            errors.append(f"UnclosedComment in {file_path.name}: unclosed CSS block comment")
        if not errors and string_mode is not None:
            errors.append(f"UnclosedString in {file_path.name}: unclosed string literal ({string_mode})")
        if not errors and stack:
            top_char, top_line = stack[-1]
            errors.append(f"UnclosedBracket in {file_path.name}: unclosed '{top_char}' opened at line {top_line}")

    # 9. Shell Script Validation (.sh, .bash, .zsh)
    elif suffix in [".sh", ".bash", ".zsh"]:
        # Try native dry-run syntax check if bash/sh is available
        try:
            import subprocess
            shell_bin = "bash" if suffix in [".sh", ".bash"] else ("zsh" if suffix == ".zsh" else "sh")
            res = subprocess.run([shell_bin, "-n", str(file_path)], capture_output=True, text=True, timeout=5)
            if res.returncode != 0:
                err_msg = res.stderr.strip() or f"Shell syntax error (exit code {res.returncode})"
                errors.append(f"ShellSyntaxError in {file_path.name}: {err_msg}")
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            res = None

        if not errors:
            # Enhanced fallback parser for shell scripts supporting heredocs and case branches
            stack: list[tuple[str, int]] = []
            matching = {')': '(', '}': '{', ']': '['}
            string_mode: str | None = None
            in_comment = False
            in_heredoc: str | None = None
            in_case_block = 0

            lines = content.splitlines()
            for line_idx, line in enumerate(lines, 1):
                if in_heredoc is not None:
                    if line.strip() == in_heredoc:
                        in_heredoc = None
                    continue

                # Check heredoc start (e.g. << 'EOF' or <<EOF or <<- "DELIM") - identifier must start with alpha/underscore
                heredoc_match = re.search(r'(?<!<)<<-?\s*[\'"]?([a-zA-Z_][a-zA-Z0-9_]*)[\'"]?', line)
                if heredoc_match:
                    in_heredoc = heredoc_match.group(1)

                # Check case block entry / exit
                stripped = line.strip()
                if re.match(r'^case\b.*?\bin\b', stripped):
                    in_case_block += 1
                elif stripped == "esac" or stripped.startswith("esac ") or stripped.startswith("esac;"):
                    if in_case_block > 0:
                        in_case_block -= 1

                i = 0
                n = len(line)
                while i < n:
                    char = line[i]
                    if in_comment:
                        if char == '\n':
                            in_comment = False
                        i += 1
                        continue

                    if string_mode is None and char == '#':
                        # In shell, $# is parameter count and ${#var} is string length
                        if i > 0 and (line[i - 1] == '$' or (line[i - 1] == '{' and i > 1 and line[i - 2] == '$')):
                            i += 1
                            continue
                        if i == 0 or line[i - 1].isspace() or line[i - 1] in [';', '&', '|', '(', '{', '`']:
                            break

                    if char in ['"', "'"]:
                        bs_count = 0
                        k = i - 1
                        while k >= 0 and line[k] == '\\':
                            bs_count += 1
                            k -= 1
                        if bs_count % 2 == 0:
                            if string_mode is None:
                                string_mode = char
                            elif string_mode == char:
                                string_mode = None
                        i += 1
                        continue

                    if string_mode is None:
                        if char in matching.values():
                            stack.append((char, line_idx))
                        elif char in matching:
                            expected = matching[char]
                            if not stack:
                                if in_case_block > 0 and char == ')':
                                    i += 1
                                    continue
                                errors.append(f"BracketMismatch in {file_path.name}: unmatched '{char}' at line {line_idx} (expected pair for 'none')")
                                break
                            top_char, top_line = stack.pop()
                            if top_char != expected:
                                if in_case_block > 0 and char == ')':
                                    stack.append((top_char, top_line))
                                    i += 1
                                    continue
                                errors.append(f"BracketMismatch in {file_path.name}: unmatched '{char}' at line {line_idx} (expected pair for '{top_char}' opened at line {top_line})")
                                break
                    i += 1
                if errors:
                    break

            if not errors and string_mode is not None:
                errors.append(f"UnclosedString in {file_path.name}: unclosed string literal ({string_mode})")
            if not errors and stack:
                top_char, top_line = stack[-1]
                errors.append(f"UnclosedBracket in {file_path.name}: unclosed '{top_char}' opened at line {top_line}")

    # 10. SQL Script Validation (.sql)
    elif suffix == ".sql":
        stack: list[tuple[str, int]] = []
        matching = {')': '(', ']': '[', '}': '{'}
        in_line_comment = False
        in_multi_comment = False
        in_string = False
        in_backtick = False
        in_double_quote = False
        dollar_tag: str | None = None
        i = 0
        n = len(content)

        while i < n:
            char = content[i]
            next_char = content[i + 1] if i + 1 < n else ''

            if in_line_comment:
                if char == '\n':
                    in_line_comment = False
                i += 1
                continue

            if in_multi_comment:
                if char == '*' and next_char == '/':
                    in_multi_comment = False
                    i += 2
                    continue
                i += 1
                continue

            # PostgreSQL Dollar-Quoted String handling: $tag$...$tag$ or $$...$$
            if dollar_tag is not None:
                if content.startswith(dollar_tag, i):
                    i += len(dollar_tag)
                    dollar_tag = None
                    continue
                i += 1
                continue

            if not in_string and not in_backtick and not in_double_quote:
                if char == '-' and next_char == '-':
                    in_line_comment = True
                    i += 2
                    continue
                if char == '#':
                    in_line_comment = True
                    i += 1
                    continue
                if char == '/' and next_char == '*':
                    in_multi_comment = True
                    i += 2
                    continue

                # Check PostgreSQL dollar quote start: $[a-zA-Z0-9_]*$
                if char == '$':
                    dollar_match = re.match(r'^\$([a-zA-Z0-9_]*)\$', content[i:])
                    if dollar_match:
                        dollar_tag = dollar_match.group(0)
                        i += len(dollar_tag)
                        continue

            if char == "'" and not in_backtick and not in_double_quote:
                bs_count = 0
                k = i - 1
                while k >= 0 and content[k] == '\\':
                    bs_count += 1
                    k -= 1
                if bs_count % 2 == 0:
                    # In SQL, '' inside a string represents an escaped single quote
                    if in_string and next_char == "'":
                        i += 2
                        continue
                    in_string = not in_string
                i += 1
                continue

            if char == '`' and not in_string and not in_double_quote:
                bs_count = 0
                k = i - 1
                while k >= 0 and content[k] == '\\':
                    bs_count += 1
                    k -= 1
                if bs_count % 2 == 0:
                    if in_backtick and next_char == '`':
                        i += 2
                        continue
                    in_backtick = not in_backtick
                i += 1
                continue

            if char == '"' and not in_string and not in_backtick:
                bs_count = 0
                k = i - 1
                while k >= 0 and content[k] == '\\':
                    bs_count += 1
                    k -= 1
                if bs_count % 2 == 0:
                    if in_double_quote and next_char == '"':
                        i += 2
                        continue
                    in_double_quote = not in_double_quote
                i += 1
                continue

            if not in_string and not in_backtick and not in_double_quote and not in_line_comment and not in_multi_comment and dollar_tag is None:
                if char in matching.values():
                    line_num = content.count('\n', 0, i) + 1
                    stack.append((char, line_num))
                elif char in matching:
                    line_num = content.count('\n', 0, i) + 1
                    expected = matching[char]
                    if not stack:
                        errors.append(f"BracketMismatch in {file_path.name}: unmatched '{char}' at line {line_num} (expected pair for 'none')")
                        break
                    top_char, top_line = stack.pop()
                    if top_char != expected:
                        errors.append(f"BracketMismatch in {file_path.name}: unmatched '{char}' at line {line_num} (expected pair for '{top_char}' opened at line {top_line})")
                        break

            i += 1

        if not errors and dollar_tag is not None:
            errors.append(f"UnclosedDollarQuote in {file_path.name}: unclosed PostgreSQL dollar-quoted string ({dollar_tag})")
        if not errors and in_multi_comment:
            errors.append(f"UnclosedComment in {file_path.name}: unclosed SQL block comment")
        if not errors and in_string:
            errors.append(f"UnclosedString in {file_path.name}: unclosed string literal (')")
        if not errors and in_backtick:
            errors.append(f"UnclosedString in {file_path.name}: unclosed identifier (`)")
        if not errors and in_double_quote:
            errors.append(f"UnclosedString in {file_path.name}: unclosed identifier (\")")
        if not errors and stack:
            top_char, top_line = stack[-1]
            errors.append(f"UnclosedBracket in {file_path.name}: unclosed '{top_char}' opened at line {top_line}")

    # 11. PowerShell Script Validation (.ps1, .psm1, .psd1)
    elif suffix in [".ps1", ".psm1", ".psd1"]:
        stack: list[tuple[str, int]] = []
        matching = {')': '(', '}': '{', ']': '['}
        in_block_comment = False
        in_line_comment = False
        in_here_string: str | None = None
        string_mode: str | None = None
        i = 0
        n = len(content)

        while i < n:
            char = content[i]
            next_char = content[i + 1] if i + 1 < n else ''

            if in_block_comment:
                if char == '#' and next_char == '>':
                    in_block_comment = False
                    i += 2
                    continue
                i += 1
                continue

            if in_line_comment:
                if char == '\n':
                    in_line_comment = False
                i += 1
                continue

            if in_here_string is not None:
                if (i == 0 or content[i - 1] == '\n') and content.startswith(in_here_string, i):
                    in_here_string = None
                    i += 2
                    continue
                i += 1
                continue

            if string_mode is not None:
                if string_mode == '"' and char == '`':
                    i += 2
                    continue
                if string_mode == "'" and char == "'" and next_char == "'":
                    i += 2
                    continue
                if string_mode == '"' and char == '"' and next_char == '"':
                    i += 2
                    continue
                if char == string_mode:
                    string_mode = None
                i += 1
                continue

            # Outside comments and strings:
            if content.startswith("@'", i) or content.startswith('@"', i):
                quote_type = content[i + 1]
                closing_tag = "'" + "@" if quote_type == "'" else '"' + "@"
                in_here_string = closing_tag
                i += 2
                continue

            if char == '<' and next_char == '#':
                in_block_comment = True
                i += 2
                continue

            if char == '#':
                in_line_comment = True
                i += 1
                continue

            if char in ["'", '"']:
                string_mode = char
                i += 1
                continue

            if char in matching.values():
                line_num = content.count('\n', 0, i) + 1
                stack.append((char, line_num))
            elif char in matching:
                line_num = content.count('\n', 0, i) + 1
                expected = matching[char]
                if not stack:
                    errors.append(f"BracketMismatch in {file_path.name}: unmatched '{char}' at line {line_num} (expected pair for 'none')")
                    break
                top_char, top_line = stack.pop()
                if top_char != expected:
                    errors.append(f"BracketMismatch in {file_path.name}: unmatched '{char}' at line {line_num} (expected pair for '{top_char}' opened at line {top_line})")
                    break

            i += 1

        if not errors and in_block_comment:
            errors.append(f"UnclosedComment in {file_path.name}: unclosed PowerShell block comment (<#)")
        if not errors and in_here_string is not None:
            errors.append(f"UnclosedString in {file_path.name}: unclosed PowerShell here-string")
        if not errors and string_mode is not None:
            errors.append(f"UnclosedString in {file_path.name}: unclosed string literal ({string_mode})")
        if not errors and stack:
            top_char, top_line = stack[-1]
            errors.append(f"UnclosedBracket in {file_path.name}: unclosed '{top_char}' opened at line {top_line}")

    # 12. GraphQL & Protobuf Validation (.graphql, .gql, .proto)
    elif suffix in [".graphql", ".gql", ".proto"]:
        stack: list[tuple[str, int]] = []
        matching = {')': '(', '}': '{', ']': '['}
        in_line_comment = False
        in_block_comment = False
        string_mode: str | None = None
        i = 0
        n = len(content)

        while i < n:
            char = content[i]
            next_char = content[i + 1] if i + 1 < n else ''

            if in_block_comment:
                if char == '*' and next_char == '/':
                    in_block_comment = False
                    i += 2
                    continue
                i += 1
                continue

            if in_line_comment:
                if char == '\n':
                    in_line_comment = False
                i += 1
                continue

            if string_mode is None:
                if suffix in [".graphql", ".gql"] and char == '#':
                    in_line_comment = True
                    i += 1
                    continue
                if suffix == ".proto":
                    if char == '/' and next_char == '/':
                        in_line_comment = True
                        i += 2
                        continue
                    if char == '/' and next_char == '*':
                        in_block_comment = True
                        i += 2
                        continue

                if suffix in [".graphql", ".gql"] and content.startswith('"""', i):
                    end_idx = content.find('"""', i + 3)
                    if end_idx != -1:
                        i = end_idx + 3
                        continue
                    else:
                        line_num = content.count('\n', 0, i) + 1
                        errors.append(f"UnclosedString in {file_path.name}: unclosed GraphQL block string literal at line {line_num}")
                        break

                if char in ['"', "'"]:
                    string_mode = char
                    i += 1
                    continue

                if char in matching.values():
                    line_num = content.count('\n', 0, i) + 1
                    stack.append((char, line_num))
                elif char in matching:
                    line_num = content.count('\n', 0, i) + 1
                    expected = matching[char]
                    if not stack:
                        errors.append(f"BracketMismatch in {file_path.name}: unmatched '{char}' at line {line_num} (expected pair for 'none')")
                        break
                    top_char, top_line = stack.pop()
                    if top_char != expected:
                        errors.append(f"BracketMismatch in {file_path.name}: unmatched '{char}' at line {line_num} (expected pair for '{top_char}' opened at line {top_line})")
                        break
            else:
                if char == '\\':
                    i += 2
                    continue
                if char == string_mode:
                    string_mode = None
                i += 1
                continue

            i += 1

        if not errors and in_block_comment:
            errors.append(f"UnclosedComment in {file_path.name}: unclosed block comment (/*)")
        if not errors and string_mode is not None:
            errors.append(f"UnclosedString in {file_path.name}: unclosed string literal ({string_mode})")
        if not errors and stack:
            top_char, top_line = stack[-1]
            errors.append(f"UnclosedBracket in {file_path.name}: unclosed '{top_char}' opened at line {top_line}")

    # 13. INI / Config / Properties / Dotenv Validation (.ini, .cfg, .conf, .properties, .env, .env.local, etc.)
    elif suffix in [".ini", ".cfg", ".conf", ".properties", ".env"] or file_name in ENV_FILENAMES or file_name.startswith(".env."):
        if suffix in [".ini", ".cfg"]:
            try:
                import configparser
                cfg = configparser.ConfigParser(interpolation=None)
                cfg.read_string(content, source=str(file_path))
            except Exception as e:
                if "MissingSectionHeaderError" in type(e).__name__:
                    pass
                else:
                    errors.append(f"ConfigError in {file_path.name}: {str(e)}")

        if not errors:
            for line_idx, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or stripped.startswith(";"):
                    continue
                in_squote = False
                in_dquote = False
                escaped = False
                for c in stripped:
                    if escaped:
                        escaped = False
                        continue
                    if c == '\\':
                        escaped = True
                        continue
                    if not in_squote and not in_dquote and (c == '#' or c == ';'):
                        break
                    if c == "'" and not in_dquote:
                        in_squote = not in_squote
                    elif c == '"' and not in_squote:
                        in_dquote = not in_dquote
                if in_squote or in_dquote:
                    q_char = "'" if in_squote else '"'
                    errors.append(f"UnclosedString in {file_path.name}: unclosed string literal ({q_char}) at line {line_idx}")
                    break

    return errors

def find_source_files(target_dir: Path, max_files: int = 500) -> list[Path]:
    """Recursively collects source files while skipping ignored directories and enforcing safety bounds."""
    files: list[Path] = []
    
    for root, dirs, filenames in os.walk(target_dir):
        # Prune ignored directories in-place
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
        for f in filenames:
            p = Path(root) / f
            f_lower = f.lower()
            if p.suffix.lower() in SOURCE_EXTENSIONS or f_lower in ENV_FILENAMES or f_lower.startswith(".env."):
                files.append(p)
                if len(files) >= max_files:
                    return files
    return files
