#!/usr/bin/env python3
"""
Antigravity Public API Contract Guard (Cross-Platform)
Detects breaking changes in public API signatures across Python, TypeScript/JS, Go, and Rust.
Preserves backwards compatibility according to Rule 13 (Non-Breaking API Evolution).
"""

from __future__ import annotations

import ast
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# TypeScript / JavaScript export patterns
TS_EXPORT_FUNC = re.compile(r'^\s*export\s+(?:async\s+)?function\s+(?P<name>[a-zA-Z0-9_$]+)\s*\((?P<params>[^)]*)\)', re.MULTILINE)
TS_EXPORT_CONST_FN = re.compile(r'^\s*export\s+(?:const|let)\s+(?P<name>[a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?\((?P<params>[^)]*)\)\s*=>', re.MULTILINE)
TS_EXPORT_CLASS = re.compile(r'^\s*export\s+(?:abstract\s+)?class\s+(?P<name>[a-zA-Z0-9_$]+)', re.MULTILINE)
TS_EXPORT_TYPE = re.compile(r'^\s*export\s+type\s+(?P<name>[a-zA-Z0-9_$]+)', re.MULTILINE)
TS_EXPORT_INTERFACE = re.compile(r'^\s*export\s+interface\s+(?P<name>[a-zA-Z0-9_$]+)', re.MULTILINE)

# Go exported identifier pattern (Capital initial letter at top-level)
GO_EXPORT_FUNC = re.compile(r'^func\s+(?:\([^)]+\)\s+)?(?P<name>[A-Z][a-zA-Z0-9_]*)\s*\((?P<params>[^)]*)\)', re.MULTILINE)
GO_EXPORT_TYPE = re.compile(r'^type\s+(?P<name>[A-Z][a-zA-Z0-9_]*)\s+(?:struct|interface|[a-zA-Z0-9_]+)', re.MULTILINE)

# Rust public identifier pattern
RUST_PUB_FN = re.compile(r'^\s*pub\s+(?:async\s+)?(?:unsafe\s+)?fn\s+(?P<name>[a-zA-Z0-9_]+)\s*(?:<[^>]*>)?\s*\((?P<params>[^)]*)\)', re.MULTILINE)
RUST_PUB_STRUCT = re.compile(r'^\s*pub\s+struct\s+(?P<name>[a-zA-Z0-9_]+)', re.MULTILINE)
RUST_PUB_ENUM = re.compile(r'^\s*pub\s+enum\s+(?P<name>[a-zA-Z0-9_]+)', re.MULTILINE)
RUST_PUB_TRAIT = re.compile(r'^\s*pub\s+trait\s+(?P<name>[a-zA-Z0-9_]+)', re.MULTILINE)


def extract_python_exports(source_code: str) -> Dict[str, Dict[str, Any]]:
    """Extracts public symbols and parameter signatures from Python source using AST."""
    symbols: Dict[str, Dict[str, Any]] = {}
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return symbols

    # Check for __all__ declaration
    explicit_all: Optional[Set[str]] = None
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(stmt.value, (ast.List, ast.Tuple, ast.Set)):
                        items = set()
                        for el in stmt.value.elts:
                            if isinstance(el, ast.Constant) and isinstance(el.value, str):
                                items.add(el.value)
                        explicit_all = items

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
            if explicit_all is not None:
                if name not in explicit_all:
                    continue
            elif name.startswith("_"):
                continue

            params = []
            num_pos = len(node.args.args)
            num_defaults = len(node.args.defaults)
            first_default_idx = num_pos - num_defaults

            for idx, arg in enumerate(node.args.args):
                p_name = arg.arg
                if p_name in ("self", "cls"):
                    continue
                has_default = idx >= first_default_idx
                params.append({"name": p_name, "required": not has_default})

            # Keyword-only arguments
            for idx, arg in enumerate(node.args.kwonlyargs):
                p_name = arg.arg
                default_val = node.args.kw_defaults[idx] if idx < len(node.args.kw_defaults) else None
                params.append({"name": p_name, "required": default_val is None})

            symbols[name] = {
                "kind": "function",
                "params": params,
                "lineno": node.lineno
            }

        elif isinstance(node, ast.ClassDef):
            name = node.name
            if explicit_all is not None:
                if name not in explicit_all:
                    continue
            elif name.startswith("_"):
                continue

            methods = {}
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    m_name = item.name
                    if m_name.startswith("_") and not (m_name.startswith("__") and m_name.endswith("__")):
                        continue
                    m_params = []
                    num_pos = len(item.args.args)
                    num_defaults = len(item.args.defaults)
                    first_default_idx = num_pos - num_defaults
                    for idx, arg in enumerate(item.args.args):
                        if arg.arg in ("self", "cls"):
                            continue
                        m_params.append({"name": arg.arg, "required": idx < first_default_idx})
                    methods[m_name] = {"params": m_params}

            symbols[name] = {
                "kind": "class",
                "methods": methods,
                "lineno": node.lineno
            }

    return symbols


def extract_ts_exports(source_code: str) -> Dict[str, Dict[str, Any]]:
    """Extracts exported functions, classes, and types from TypeScript / JavaScript source."""
    symbols: Dict[str, Dict[str, Any]] = {}

    for pat, kind in [
        (TS_EXPORT_FUNC, "function"),
        (TS_EXPORT_CONST_FN, "function"),
        (TS_EXPORT_CLASS, "class"),
        (TS_EXPORT_TYPE, "type"),
        (TS_EXPORT_INTERFACE, "interface")
    ]:
        for match in pat.finditer(source_code):
            name = match.group("name")
            params = []
            if kind == "function" and "params" in match.groupdict():
                raw_params = match.group("params")
                for p in raw_params.split(","):
                    p_clean = p.strip()
                    if not p_clean or p_clean.startswith("//"):
                        continue
                    p_name = p_clean.split(":")[0].split("=")[0].strip()
                    is_optional = "?" in p_clean or "=" in p_clean or p_clean.startswith("...")
                    params.append({"name": p_name, "required": not is_optional})
            symbols[name] = {"kind": kind, "params": params}

    return symbols


def extract_go_exports(source_code: str) -> Dict[str, Dict[str, Any]]:
    """Extracts exported functions and types from Go source."""
    symbols: Dict[str, Dict[str, Any]] = {}

    for match in GO_EXPORT_FUNC.finditer(source_code):
        name = match.group("name")
        raw_params = match.group("params").strip()
        params = [p.strip() for p in raw_params.split(",") if p.strip()]
        symbols[name] = {"kind": "function", "params": [{"name": p, "required": True} for p in params]}

    for match in GO_EXPORT_TYPE.finditer(source_code):
        name = match.group("name")
        symbols[name] = {"kind": "type", "params": []}

    return symbols


def extract_rust_exports(source_code: str) -> Dict[str, Dict[str, Any]]:
    """Extracts public functions and structs from Rust source."""
    symbols: Dict[str, Dict[str, Any]] = {}

    for match in RUST_PUB_FN.finditer(source_code):
        name = match.group("name")
        raw_params = match.group("params").strip()
        params = [p.strip() for p in raw_params.split(",") if p.strip() and not p.strip().startswith("&self") and p.strip() != "self"]
        symbols[name] = {"kind": "function", "params": [{"name": p, "required": True} for p in params]}

    for pat, kind in [
        (RUST_PUB_STRUCT, "struct"),
        (RUST_PUB_ENUM, "enum"),
        (RUST_PUB_TRAIT, "trait")
    ]:
        for match in pat.finditer(source_code):
            symbols[match.group("name")] = {"kind": kind, "params": []}

    return symbols


def extract_public_symbols(source_code: str, file_path: Path) -> Dict[str, Dict[str, Any]]:
    """Dispatches to the appropriate language symbol extractor based on file extension."""
    suffix = file_path.suffix.lower()
    if suffix in (".py", ".pyi"):
        return extract_python_exports(source_code)
    if suffix in (".ts", ".tsx", ".js", ".jsx", ".d.ts"):
        return extract_ts_exports(source_code)
    if suffix == ".go":
        return extract_go_exports(source_code)
    if suffix == ".rs":
        return extract_rust_exports(source_code)
    return {}


def compare_symbol_contracts(
    base_symbols: Dict[str, Dict[str, Any]],
    cand_symbols: Dict[str, Dict[str, Any]],
    file_label: str
) -> Tuple[List[str], List[str], List[str]]:
    """
    Compares base and candidate symbol tables.
    Returns (violations, warnings, additions).
    """
    violations: List[str] = []
    warnings: List[str] = []
    additions: List[str] = []

    # 1. Check for removed symbols
    for name, base_info in base_symbols.items():
        if name not in cand_symbols:
            violations.append(
                f"BreakingChange in {file_label}: exported {base_info['kind']} '{name}' was removed"
            )
            continue

        cand_info = cand_symbols[name]

        # Check function parameters
        if base_info["kind"] == "function" and cand_info["kind"] == "function":
            base_params = base_info.get("params", [])
            cand_params = cand_info.get("params", [])

            # Check if any previously existing parameter was removed
            base_p_names = {p["name"] for p in base_params}
            cand_p_names = {p["name"] for p in cand_params}

            for p_name in base_p_names:
                if p_name not in cand_p_names:
                    violations.append(
                        f"BreakingChange in {file_label}: parameter '{p_name}' was removed from function '{name}'"
                    )

            # Check if any new required parameter was added
            base_required = {p["name"] for p in base_params if p.get("required", True)}
            for cand_p in cand_params:
                p_name = cand_p["name"]
                if cand_p.get("required", True) and p_name not in base_required and p_name not in base_p_names:
                    violations.append(
                        f"BreakingChange in {file_label}: new required parameter '{p_name}' added to function '{name}' without default"
                    )

        # Check class methods if applicable
        if base_info["kind"] == "class" and cand_info["kind"] == "class":
            base_methods = base_info.get("methods", {})
            cand_methods = cand_info.get("methods", {})
            for m_name in base_methods:
                if m_name not in cand_methods:
                    violations.append(
                        f"BreakingChange in {file_label}: public method '{m_name}' was removed from class '{name}'"
                    )

    # 2. Track additions (Safe Evolution)
    for name, cand_info in cand_symbols.items():
        if name not in base_symbols:
            additions.append(f"Added {cand_info['kind']} '{name}' in {file_label}")

    return violations, warnings, additions


def get_git_base_content(git_ref: str, relative_path: str, repo_root: Path) -> Optional[str]:
    """Retrieves file content at a specific git reference."""
    try:
        # Use forward slashes for git paths
        norm_rel = str(relative_path).replace("\\", "/")
        res = subprocess.run(
            ["git", "show", f"{git_ref}:{norm_rel}"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False
        )
        if res.returncode == 0:
            return res.stdout
    except (subprocess.SubprocessError, OSError):
        return None
    return None


def audit_api_contract_drift(
    target_dir: Path,
    base_ref: str = "HEAD",
    specific_files: Optional[List[Path]] = None
) -> Dict[str, Any]:
    """Inspects changed files against base git reference for public contract drift."""
    report: Dict[str, Any] = {
        "status": "PASS",
        "violations": [],
        "warnings": [],
        "additions": [],
        "suggested_fixes": [],
        "files_checked": 0
    }

    try:
        res = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(target_dir),
            capture_output=True,
            text=True,
            check=False
        )
        if res.returncode != 0:
            report["warnings"].append("Not a git repository; contract drift verification skipped.")
            return report
        repo_root = Path(res.stdout.strip()).resolve()
    except (subprocess.SubprocessError, OSError):
        report["warnings"].append("Git command failed; contract drift verification skipped.")
        return report

    supported_suffixes = {".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs"}

    if specific_files:
        candidate_files = [f.resolve() for f in specific_files if f.suffix.lower() in supported_suffixes and f.is_file()]
    else:
        # Get changed files between working tree and base_ref
        try:
            diff_res = subprocess.run(
                ["git", "diff", "--name-only", base_ref],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                check=False
            )
            changed_names = [line.strip() for line in diff_res.stdout.splitlines() if line.strip()]
        except (subprocess.SubprocessError, OSError):
            changed_names = []

        candidate_files = []
        for name in changed_names:
            p = (repo_root / name).resolve()
            if p.suffix.lower() in supported_suffixes and p.is_file():
                candidate_files.append(p)

    for cand_path in candidate_files:
        try:
            rel_path = cand_path.relative_to(repo_root)
        except ValueError:
            continue

        base_content = get_git_base_content(base_ref, str(rel_path), repo_root)
        if base_content is None:
            # New file, completely additive
            continue

        try:
            with open(cand_path, "r", encoding="utf-8", errors="replace") as fc:
                cand_content = fc.read()
        except OSError:
            continue

        base_symbols = extract_public_symbols(base_content, cand_path)
        cand_symbols = extract_public_symbols(cand_content, cand_path)

        v, w, a = compare_symbol_contracts(base_symbols, cand_symbols, rel_path.name)
        report["violations"].extend(v)
        report["warnings"].extend(w)
        report["additions"].extend(a)
        report["files_checked"] += 1

    if report["violations"]:
        report["status"] = "RETRY"
        for v in report["violations"]:
            report["suggested_fixes"].append("Preserve exported symbol signature or provide backwards-compatible defaults")

    return report


def main():
    parser = argparse.ArgumentParser(description="Antigravity Public API Contract Guard")
    parser.add_argument("--base-ref", default="HEAD", help="Base git reference to compare against (default: HEAD)")
    parser.add_argument("--target", default=".", help="Target workspace directory or file path")
    parser.add_argument("--base-file", default=None, help="Explicit base file for pairwise comparison")
    parser.add_argument("--candidate-file", default=None, help="Explicit candidate file for pairwise comparison")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON format")

    args = parser.parse_args()

    # Pairwise comparison mode
    if args.base_file and args.candidate_file:
        b_path = Path(args.base_file).resolve()
        c_path = Path(args.candidate_file).resolve()
        if not b_path.is_file() or not c_path.is_file():
            sys.stderr.write("Error: Both base-file and candidate-file must exist.\n")
            sys.exit(2)
        with open(b_path, "r", encoding="utf-8", errors="replace") as fb:
            b_src = fb.read()
        with open(c_path, "r", encoding="utf-8", errors="replace") as fc:
            c_src = fc.read()

        b_syms = extract_public_symbols(b_src, b_path)
        c_syms = extract_public_symbols(c_src, c_path)
        v, w, a = compare_symbol_contracts(b_syms, c_syms, c_path.name)
        status = "PASS" if not v else "RETRY"
        result = {
            "status": status,
            "violations": v,
            "warnings": w,
            "additions": a,
            "suggested_fixes": ["Preserve public signature or provide defaults" for _ in v]
        }
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Status: {status}")
            for item in v:
                print(f"VIOLATION: {item}")
            for item in a:
                print(f"ADDITION: {item}")
        sys.exit(0 if status == "PASS" else 1)

    target_path = Path(args.target).resolve()
    if target_path.is_file():
        rep = audit_api_contract_drift(target_path.parent, base_ref=args.base_ref, specific_files=[target_path])
    else:
        rep = audit_api_contract_drift(target_path, base_ref=args.base_ref)

    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        print(f"Status: {rep['status']} (Files checked: {rep['files_checked']})")
        for v in rep["violations"]:
            print(f"VIOLATION: {v}")
        for a in rep["additions"]:
            print(f"ADDITION: {a}")

    sys.exit(0 if rep["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
