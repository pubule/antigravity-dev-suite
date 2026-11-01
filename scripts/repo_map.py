#!/usr/bin/env python3
"""
Antigravity Dynamic Repository Mapping Engine (Cross-Platform)
Generates high-density, token-efficient repository symbol maps for LLM context injection.
Preserves context window hygiene according to Claude Opus 5.5 architectural directives.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Supported file extensions and their language families
EXT_TO_LANG = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".cs": "csharp",
    ".java": "java",
    ".swift": "swift"
}

# Directories to exclude from repository mapping
EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "vendor", ".venv", "venv",
    "env", "__pycache__", ".pytest_cache", ".mypy_cache", "target",
    "dist", "build", ".next", ".nuxt", "coverage", ".turbo"
}

# Regex patterns for non-Python symbol extraction
TS_SYMBOL_PAT = re.compile(
    r'^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class|interface|type|enum)\s+(?P<name>[a-zA-Z0-9_$]+)',
    re.MULTILINE
)
GO_SYMBOL_PAT = re.compile(
    r'^(?:func(?:\s+\([^)]+\))?\s+|type\s+)(?P<name>[a-zA-Z0-9_]+)',
    re.MULTILINE
)
RUST_SYMBOL_PAT = re.compile(
    r'^\s*(?:pub\s+)?(?:async\s+)?(?:fn|struct|enum|trait|type|impl)\s+(?P<name>[a-zA-Z0-9_]+)',
    re.MULTILINE
)
CS_JAVA_SYMBOL_PAT = re.compile(
    r'^\s*(?:public|protected|private|internal)?\s*(?:static\s+)?(?:class|interface|record|enum)\s+(?P<name>[a-zA-Z0-9_]+)',
    re.MULTILINE
)


def extract_python_symbols(content: str) -> List[Dict[str, Any]]:
    """Extracts classes, methods, and functions from Python code using AST."""
    symbols: List[Dict[str, Any]] = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return symbols

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_") or node.name in ("__init__", "__call__"):
                args_list = [a.arg for a in node.args.args if a.arg not in ("self", "cls")]
                sig = f"def {node.name}({', '.join(args_list[:4])})"
                symbols.append({"kind": "function", "name": node.name, "sig": sig, "line": node.lineno})
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                class_item = {
                    "kind": "class",
                    "name": node.name,
                    "sig": f"class {node.name}",
                    "line": node.lineno,
                    "methods": []
                }
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not child.name.startswith("_") or child.name in ("__init__", "__call__"):
                            m_args = [a.arg for a in child.args.args if a.arg not in ("self", "cls")]
                            class_item["methods"].append(f"def {child.name}({', '.join(m_args[:3])})")
                symbols.append(class_item)
    return symbols


def extract_text_symbols(content: str, lang: str) -> List[Dict[str, Any]]:
    """Extracts symbols using structural regex for compiled and web languages."""
    symbols: List[Dict[str, Any]] = []
    pat = None
    if lang in ("typescript", "javascript"):
        pat = TS_SYMBOL_PAT
    elif lang == "go":
        pat = GO_SYMBOL_PAT
    elif lang == "rust":
        pat = RUST_SYMBOL_PAT
    elif lang in ("csharp", "java", "swift"):
        pat = CS_JAVA_SYMBOL_PAT

    if not pat:
        return symbols

    for match in pat.finditer(content):
        name = match.group("name")
        line_num = content[:match.start()].count("\n") + 1
        raw_line = match.group(0).strip()
        symbols.append({"kind": "symbol", "name": name, "sig": raw_line, "line": line_num})

    return symbols


def scan_repository(workspace_dir: Path, max_files: int = 200) -> Dict[str, List[Dict[str, Any]]]:
    """Scans workspace directory and extracts symbols grouped by relative path."""
    repo_map: Dict[str, List[Dict[str, Any]]] = {}
    ws = workspace_dir.resolve()
    scanned_count = 0

    for root, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
        for file_name in sorted(files):
            file_path = Path(root) / file_name
            ext = file_path.suffix.lower()
            if ext not in EXT_TO_LANG:
                continue

            try:
                rel_path = str(file_path.relative_to(ws)).replace("\\", "/")
            except ValueError:
                continue

            # Read source content
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except OSError:
                continue

            lang = EXT_TO_LANG[ext]
            if lang == "python":
                syms = extract_python_symbols(content)
            else:
                syms = extract_text_symbols(content, lang)

            if syms:
                repo_map[rel_path] = syms
                scanned_count += 1
                if scanned_count >= max_files:
                    return repo_map

    return repo_map


def format_repo_map(repo_map: Dict[str, List[Dict[str, Any]]], max_lines: int = 150) -> str:
    """Formats symbol map into high-density ASCII hierarchy with strict line budgeting."""
    lines: List[str] = ["# Repository Symbol Map"]
    current_lines = 1

    for file_path, symbols in sorted(repo_map.items()):
        if current_lines >= max_lines - 5:
            remaining = len(repo_map) - len(lines)
            lines.append(f"\n[... Truncated {max(0, remaining)} additional files for token hygiene ...]")
            break

        lines.append(f"\n📄 {file_path}")
        current_lines += 2

        for sym in symbols:
            if current_lines >= max_lines - 2:
                lines.append("  └── [... symbols truncated ...]")
                current_lines += 1
                break

            if sym.get("kind") == "class":
                lines.append(f"  ├── {sym['sig']}")
                current_lines += 1
                for m in sym.get("methods", [])[:5]:
                    if current_lines >= max_lines - 2:
                        break
                    lines.append(f"  │     {m}")
                    current_lines += 1
            else:
                lines.append(f"  ├── {sym.get('sig', sym['name'])}")
                current_lines += 1

    return "\n".join(lines)


def generate_repo_map(
    target_dir: Path,
    max_tokens: int = 2048,
    max_files: int = 150
) -> Dict[str, Any]:
    """Generates structured repository map and token-budgeted representation."""
    # Approximate ~4 characters per token
    budgeted_lines = max(30, (max_tokens * 4) // 60)
    raw_map = scan_repository(target_dir, max_files=max_files)
    formatted = format_repo_map(raw_map, max_lines=budgeted_lines)

    return {
        "status": "SUCCESS",
        "file_count": len(raw_map),
        "total_symbols": sum(len(s) for s in raw_map.values()),
        "max_tokens": max_tokens,
        "formatted_map": formatted,
        "raw_map": raw_map
    }


def main():
    parser = argparse.ArgumentParser(description="Antigravity Dynamic Repository Mapping Engine")
    parser.add_argument("target", nargs="?", default=".", help="Root directory of workspace to map")
    parser.add_argument("--max-tokens", type=int, default=2048, help="Token budget for map output (default: 2048)")
    parser.add_argument("--max-files", type=int, default=150, help="Maximum files to scan")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON format")

    args = parser.parse_args()
    target_dir = Path(args.target).resolve()

    if not target_dir.is_dir():
        sys.stderr.write(f"Error: Target directory does not exist: {target_dir}\n")
        sys.exit(1)

    result = generate_repo_map(target_dir, max_tokens=args.max_tokens, max_files=args.max_files)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(result["formatted_map"])


if __name__ == "__main__":
    main()
