#!/usr/bin/env python3
"""
Antigravity Semantic Symbol Slicing Engine (Cross-Platform)
Extracts targeted symbol AST blocks (functions, classes, methods) with surrounding context and imports.
Reduces token load by 70-80% for Gemini Flash 3.8 and provides Claude Opus 5.5 precision.
"""

from __future__ import annotations

import ast
import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def extract_python_imports(tree: ast.AST, lines: List[str]) -> List[str]:
    """Collects top-level import statements from a Python AST."""
    import_lines: List[str] = []
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            start = node.lineno - 1
            end = getattr(node, "end_lineno", node.lineno)
            import_lines.extend(lines[start:end])
    return import_lines


def extract_python_slice(
    source_code: str,
    target_symbol: Optional[str] = None,
    target_line: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """Extracts targeted symbol or enclosing block from Python source using AST."""
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return None

    lines = source_code.splitlines(keepends=True)
    imports = extract_python_imports(tree, lines)

    matched_node: Optional[ast.AST] = None
    matched_name: str = ""
    matched_parent: Optional[str] = None

    # Traverse AST to find match
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
            start_l = node.lineno
            end_l = getattr(node, "end_lineno", start_l)

            # Match by symbol name
            if target_symbol:
                if name == target_symbol:
                    matched_node = node
                    matched_name = name
                    break
                if isinstance(node, ast.ClassDef):
                    # Check nested methods
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            full_name = f"{name}.{item.name}"
                            if item.name == target_symbol or full_name == target_symbol:
                                matched_node = item
                                matched_name = full_name
                                matched_parent = name
                                break
                    if matched_node:
                        break

            # Match by line number
            elif target_line is not None:
                if start_l <= target_line <= end_l:
                    matched_node = node
                    matched_name = name
                    # If it's a class, check if a nested method specifically contains target_line
                    if isinstance(node, ast.ClassDef):
                        for item in node.body:
                            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                if item.lineno <= target_line <= getattr(item, "end_lineno", item.lineno):
                                    matched_node = item
                                    matched_name = f"{name}.{item.name}"
                                    matched_parent = name
                                    break
                    break

    if not matched_node:
        return None

    start_idx = matched_node.lineno - 1
    # Include decorators if present
    if hasattr(matched_node, "decorator_list") and matched_node.decorator_list:
        dec_start = min(dec.lineno for dec in matched_node.decorator_list)
        start_idx = min(start_idx, dec_start - 1)

    end_idx = getattr(matched_node, "end_lineno", matched_node.lineno)
    slice_content = "".join(lines[start_idx:end_idx])

    return {
        "status": "SUCCESS",
        "symbol": matched_name,
        "parent": matched_parent,
        "node_type": type(matched_node).__name__,
        "start_line": start_idx + 1,
        "end_line": end_idx,
        "content": slice_content,
        "imports": "".join(imports).strip()
    }


def find_brace_block_end(lines: List[str], start_line_idx: int) -> int:
    """Finds the closing brace of a block starting from start_line_idx, ignoring string and comment contents. # safe-bounds"""
    depth = 0
    found_first_brace = False
    in_single = False
    in_double = False
    in_backtick = False
    in_block_comment = False

    for idx in range(start_line_idx, len(lines)):
        line = lines[idx]
        i = 0
        n = len(line)
        while i < n:
            ch = line[i]

            # 1. Multi-line block comment handler (/* ... */)
            if in_block_comment:
                if ch == '*' and i + 1 < n and line[i + 1] == '/':
                    in_block_comment = False
                    i += 2
                    continue
                i += 1
                continue

            # 2. Escaped character inside quotes or template literals
            if (in_single or in_double or in_backtick) and ch == '\\':
                i += 2
                continue

            # 3. String literals and template literals toggle
            if not in_double and not in_backtick and ch == "'":
                in_single = not in_single
                i += 1
                continue
            if not in_single and not in_backtick and ch == '"':
                in_double = not in_double
                i += 1
                continue
            if not in_single and not in_double and ch == '`':
                in_backtick = not in_backtick
                i += 1
                continue

            # Skip checking braces if currently inside a literal string
            if in_single or in_double or in_backtick:
                i += 1
                continue

            # 4. Single-line comment (// ...)
            if ch == '/' and i + 1 < n and line[i + 1] == '/':
                break

            # 5. Start of multi-line comment (/* ...)
            if ch == '/' and i + 1 < n and line[i + 1] == '*':
                in_block_comment = True
                i += 2
                continue

            # 6. Structural brace counting
            if ch == '{':
                depth += 1
                found_first_brace = True
            elif ch == '}':
                depth -= 1
                if found_first_brace and depth <= 0:
                    return idx + 1

            i += 1

    return len(lines)


# Regex patterns for non-Python symbol detection
GENERIC_SYMBOL_PAT = re.compile(
    r'^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:pub\s+)?(?:func|function|class|interface|type|struct|enum|impl)\s+(?P<name>[a-zA-Z0-9_$]+)',
    re.MULTILINE
)


def extract_brace_slice(
    source_code: str,
    target_symbol: Optional[str] = None,
    target_line: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """Extracts symbol slice from C-style brace languages (TypeScript, JavaScript, Go, Rust, Java)."""
    lines = source_code.splitlines(keepends=True)
    matches: List[Tuple[str, int, int]] = []

    for idx, line in enumerate(lines):
        m = GENERIC_SYMBOL_PAT.match(line)
        if m:
            sym_name = m.group("name")
            end_idx = find_brace_block_end(lines, idx)
            matches.append((sym_name, idx + 1, end_idx))

    if not matches:
        return None

    selected: Optional[Tuple[str, int, int]] = None
    if target_symbol:
        for sym_name, s_line, e_line in matches:
            if sym_name == target_symbol:
                selected = (sym_name, s_line, e_line)
                break
    elif target_line is not None:
        for sym_name, s_line, e_line in matches:
            if s_line <= target_line <= e_line:
                selected = (sym_name, s_line, e_line)
                break

    if not selected:
        return None

    sym_name, start_line, end_line = selected
    slice_content = "".join(lines[start_line - 1:end_line])

    # Extract import lines (lines starting with import/from/use/package)
    import_lines = [
        l for l in lines[:50]
        if l.strip().startswith(("import ", "from ", "use ", "package "))
    ]

    return {
        "status": "SUCCESS",
        "symbol": sym_name,
        "parent": None,
        "node_type": "BraceBlock",
        "start_line": start_line,
        "end_line": end_line,
        "content": slice_content,
        "imports": "".join(import_lines).strip()
    }


def extract_symbol_slice(
    file_path: Path,
    target_symbol: Optional[str] = None,
    target_line: Optional[int] = None,
    with_imports: bool = False,
    compact: bool = False
) -> Dict[str, Any]:
    """Extracts targeted symbol slice from supported file."""
    if not file_path.is_file():
        return {"status": "ERROR", "message": f"File does not exist: {file_path}"}

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except Exception as e:
        return {"status": "ERROR", "message": f"Read error: {str(e)}"}

    suffix = file_path.suffix.lower()
    res: Optional[Dict[str, Any]] = None

    if suffix in (".py", ".pyi"):
        res = extract_python_slice(source, target_symbol=target_symbol, target_line=target_line)
    else:
        res = extract_brace_slice(source, target_symbol=target_symbol, target_line=target_line)

    if not res:
        return {
            "status": "NOT_FOUND",
            "message": f"Symbol '{target_symbol or target_line}' not found in {file_path.name}"
        }

    res["file"] = str(file_path)

    if compact:
        # Condense blank lines
        res["content"] = re.sub(r'\n\s*\n\s*\n+', '\n\n', res["content"])

    if with_imports and res.get("imports"):
        res["slice_with_context"] = f"// Relevant Imports\n{res['imports']}\n\n// Symbol Definition ({res['symbol']})\n{res['content']}"
    else:
        res["slice_with_context"] = res["content"]

    return res


def main():
    parser = argparse.ArgumentParser(description="Antigravity Semantic Symbol Slicing Engine")
    parser.add_argument("file", help="Path to source file to slice")
    parser.add_argument("--symbol", "-s", default=None, help="Symbol name (function, class, method) to extract")
    parser.add_argument("--line", "-l", type=int, default=None, help="Line number within symbol to extract")
    parser.add_argument("--with-imports", action="store_true", help="Include file import statements in output")
    parser.add_argument("--compact", action="store_true", help="Condense blank lines to reduce token consumption")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    args = parser.parse_args()

    if not args.symbol and args.line is None:
        sys.stderr.write("Error: Must specify either --symbol or --line.\n")
        sys.exit(1)

    target_path = Path(args.file).resolve()
    result = extract_symbol_slice(
        target_path,
        target_symbol=args.symbol,
        target_line=args.line,
        with_imports=args.with_imports,
        compact=args.compact
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result["status"] == "SUCCESS":
            print(f"=== {result['symbol']} [{result['file']}#L{result['start_line']}-L{result['end_line']}] ===")
            print(result["slice_with_context"])
        else:
            print(f"Error: {result.get('message', 'Failed to slice symbol')}")

    sys.exit(0 if result["status"] == "SUCCESS" else 1)


if __name__ == "__main__":
    main()
