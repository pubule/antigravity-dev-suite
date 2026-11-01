#!/usr/bin/env python3
"""
Antigravity Cross-File Call-Graph & Symbol Impact Tracer (Cross-Platform)
Traces symbol definitions, callers, and cross-file references across a workspace.
Ensures zero-regression refactoring under Claude Opus 5.5 architectural directives.
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "vendor", ".venv", "venv",
    "env", "__pycache__", ".pytest_cache", ".mypy_cache", "target",
    "dist", "build", ".next", ".nuxt", "coverage", ".turbo", ".gemini"
}

CODE_EXTENSIONS = {
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs",
    ".cs", ".java", ".swift", ".rb", ".php", ".c", ".cpp", ".h", ".hpp"
}

# Regex for non-Python symbol definitions
DEF_PATTERNS = {
    "typescript": re.compile(
        r'^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class|interface|type|enum|const|let|var)\s+\b',
        re.MULTILINE
    ),
    "go": re.compile(
        r'^(?:func(?:\s+\([^)]+\))?\s+|type\s+)\b',
        re.MULTILINE
    ),
    "rust": re.compile(
        r'^\s*(?:pub\s+)?(?:async\s+)?(?:fn|struct|enum|trait|type)\s+\b',
        re.MULTILINE
    ),
    "general": re.compile(
        r'^\s*(?:public|protected|private|static|class|interface|record|enum|def|function|fn|func)\s+\b',
        re.MULTILINE
    )
}


def analyze_python_file(
    file_path: Path,
    symbol: str,
    content: str
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Analyzes a Python file for symbol definitions and usages using AST and line scans."""
    definitions: List[Dict[str, Any]] = []
    usages: List[Dict[str, Any]] = []
    def_lines: Set[int] = set()

    # Parse AST for precise definitions
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol:
                def_lines.add(node.lineno)
                definitions.append({
                    "line": node.lineno,
                    "kind": "function",
                    "code": content.splitlines()[node.lineno - 1].strip() if node.lineno <= len(content.splitlines()) else ""
                })
            elif isinstance(node, ast.ClassDef) and node.name == symbol:
                def_lines.add(node.lineno)
                definitions.append({
                    "line": node.lineno,
                    "kind": "class",
                    "code": content.splitlines()[node.lineno - 1].strip() if node.lineno <= len(content.splitlines()) else ""
                })
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == symbol:
                        def_lines.add(node.lineno)
                        definitions.append({
                            "line": node.lineno,
                            "kind": "variable",
                            "code": content.splitlines()[node.lineno - 1].strip() if node.lineno <= len(content.splitlines()) else ""
                        })
    except SyntaxError as parse_err:
        logging.getLogger(__name__).debug("AST parse skipped for %s: %s", file_path, parse_err)

    # Line scan for usages and regex fallback
    word_pattern = re.compile(rf'\b{re.escape(symbol)}\b')
    lines = content.splitlines()

    for i, line in enumerate(lines, 1):
        if not word_pattern.search(line):
            continue

        stripped = line.strip()
        # Ignore comments
        if stripped.startswith("#"):
            continue

        if i in def_lines:
            continue

        usages.append({
            "line": i,
            "kind": "usage",
            "code": stripped
        })

    return definitions, usages


def analyze_generic_file(
    file_path: Path,
    symbol: str,
    content: str,
    ext: str
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Analyzes non-Python files for symbol definitions and usages using regex patterns."""
    definitions: List[Dict[str, Any]] = []
    usages: List[Dict[str, Any]] = []
    word_pattern = re.compile(rf'\b{re.escape(symbol)}\b')

    lines = content.splitlines()
    for i, line in enumerate(lines, 1):
        if not word_pattern.search(line):
            continue

        stripped = line.strip()
        # Ignore common comment prefixes
        if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
            continue

        # Check definition heuristics
        is_def = False
        kind = "usage"

        if ext in (".ts", ".tsx", ".js", ".jsx"):
            if re.search(rf'(?:function|class|interface|type|enum|const|let|var)\s+{re.escape(symbol)}\b', stripped):
                is_def = True
                kind = "declaration"
        elif ext == ".go":
            if re.search(rf'(?:func(?:\s+\([^)]+\))?\s+|type\s+){re.escape(symbol)}\b', stripped):
                is_def = True
                kind = "declaration"
        elif ext == ".rs":
            if re.search(rf'(?:fn|struct|enum|trait|type)\s+{re.escape(symbol)}\b', stripped):
                is_def = True
                kind = "declaration"
        else:
            if re.search(rf'(?:class|interface|record|enum|def|func|fn)\s+{re.escape(symbol)}\b', stripped):
                is_def = True
                kind = "declaration"

        if is_def:
            definitions.append({
                "line": i,
                "kind": kind,
                "code": stripped
            })
        else:
            usages.append({
                "line": i,
                "kind": "usage",
                "code": stripped
            })

    return definitions, usages


def trace_symbol_impact(
    workspace_dir: Path,
    symbol: str,
    max_results: int = 100
) -> Dict[str, Any]:
    """Scans workspace and traces all definitions and call-sites for the specified symbol."""
    ws = workspace_dir.resolve()
    all_definitions: List[Dict[str, Any]] = []
    all_usages: List[Dict[str, Any]] = []
    impacted_files: Set[str] = set()

    for root, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]

        for file_name in sorted(files):
            file_path = Path(root) / file_name
            ext = file_path.suffix.lower()
            if ext not in CODE_EXTENSIONS:
                continue

            try:
                rel_path = str(file_path.relative_to(ws)).replace("\\", "/")
            except ValueError:
                rel_path = str(file_path)

            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except OSError:
                continue

            # Microsecond pre-check
            if symbol not in content:
                continue

            if ext in (".py", ".pyi"):
                defs, uses = analyze_python_file(file_path, symbol, content)
            else:
                defs, uses = analyze_generic_file(file_path, symbol, content, ext)

            if defs or uses:
                impacted_files.add(rel_path)

            for d in defs:
                all_definitions.append({
                    "file": rel_path,
                    "abs_path": str(file_path.resolve()),
                    **d
                })

            for u in uses:
                if len(all_usages) < max_results:
                    all_usages.append({
                        "file": rel_path,
                        "abs_path": str(file_path.resolve()),
                        **u
                    })

    return {
        "symbol": symbol,
        "total_definitions": len(all_definitions),
        "total_usages": len(all_usages),
        "files_impacted_count": len(impacted_files),
        "files_impacted": sorted(impacted_files),
        "definitions": all_definitions,
        "usages": all_usages
    }


def format_impact_markdown(result: Dict[str, Any]) -> str:
    """Formats symbol impact results into concise ASD-STE100 Markdown."""
    lines: List[str] = [
        f"# Symbol Impact Report: `{result['symbol']}`",
        f"- **Definitions Found**: {result['total_definitions']}",
        f"- **Usages / Call-sites Found**: {result['total_usages']}",
        f"- **Impacted Files**: {result['files_impacted_count']}",
        ""
    ]

    if result["definitions"]:
        lines.append("## Definitions")
        for d in result["definitions"]:
            lines.append(f"- [`{d['file']}:{d['line']}`](file://{d['abs_path']}#L{d['line']}) [{d['kind']}]: `{d['code']}`")
        lines.append("")

    if result["usages"]:
        lines.append("## Usages & Callers")
        for u in result["usages"]:
            lines.append(f"- [`{u['file']}:{u['line']}`](file://{u['abs_path']}#L{u['line']}): `{u['code']}`")
        lines.append("")
    elif not result["definitions"]:
        lines.append("No definitions or usages found in workspace.")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Antigravity Cross-File Symbol Impact Tracer")
    parser.add_argument("symbol", help="Identifier or symbol name to trace")
    parser.add_argument("--workspace", default=".", help="Root workspace directory (default: .)")
    parser.add_argument("--limit", type=int, default=100, help="Maximum usages to collect (default: 100)")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON format")

    args = parser.parse_args()
    ws_dir = Path(args.workspace).resolve()

    if not ws_dir.is_dir():
        sys.stderr.write(f"Error: Workspace directory does not exist: {ws_dir}\n")
        sys.exit(1)

    result = trace_symbol_impact(ws_dir, args.symbol, max_results=args.limit)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_impact_markdown(result))


if __name__ == "__main__":
    main()
