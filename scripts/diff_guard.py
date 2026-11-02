#!/usr/bin/env python3
"""
Antigravity AST Diff Guard for Code Hygiene & Comment Preservation (Cross-Platform)
Inspects git diff against HEAD to enforce:
1. Documentation and docstring preservation.
2. Comment integrity (detects unrequested stripping of existing comments).
3. Anti-Overengineering / KISS complexity blowup protection.
Complies with Claude Opus 5.5 directives and ASD-STE100 technical rules.
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def safe_git_env() -> Dict[str, str]:
    """Provides sandboxed git environment variables to prevent permission errors."""
    env = dict(os.environ)
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def get_git_diff_text(workspace_dir: Path, cached: bool = False) -> str:
    """Executes git diff safely within sandbox boundaries."""
    cmd = ["git", "diff", "--unified=3"]
    if cached:
        cmd.append("--cached")
    else:
        cmd.append("HEAD")

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(workspace_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=safe_git_env(),
            timeout=10
        )
        if proc.returncode == 0:
            return proc.stdout
        # Fallback to unstaged diff if HEAD fails (e.g. brand new repository)
        if not cached:
            proc2 = subprocess.run(
                ["git", "diff"],
                cwd=str(workspace_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=safe_git_env(),
                timeout=10
            )
            if proc2.returncode == 0:
                return proc2.stdout
    except (subprocess.SubprocessError, OSError) as err:
        logging.getLogger(__name__).debug("git diff execution failed: %s", err)
    return ""


def get_git_file_content(workspace_dir: Path, rel_path: str, revision: str = "HEAD") -> Optional[str]:
    """Retrieves file content from a specific git revision."""
    try:
        proc = subprocess.run(
            ["git", "show", f"{revision}:{rel_path}"],
            cwd=str(workspace_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=safe_git_env(),
            timeout=5
        )
        if proc.returncode == 0:
            return proc.stdout
    except (subprocess.SubprocessError, OSError) as err:
        logging.getLogger(__name__).debug("git show %s:%s failed: %s", revision, rel_path, err)
    return None


def extract_python_docstrings(content: str) -> Dict[str, str]:
    """Extracts function and class docstrings mapped by qualified name."""
    docstrings: Dict[str, str] = {}
    try:
        tree = ast.parse(content)
    except SyntaxError as err:
        logging.getLogger(__name__).debug("AST parse for docstrings failed: %s", err)
        return docstrings

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            ds = ast.get_docstring(node)
            docstrings[node.name] = ds.strip() if ds is not None else ""

    return docstrings


def calculate_ast_max_nesting(node: ast.AST, current_depth: int = 0) -> int:
    """Calculates maximum block nesting depth for a function."""
    nesting_nodes = (
        ast.If, ast.For, ast.AsyncFor, ast.While, ast.With,
        ast.AsyncWith, ast.Try, ast.ExceptHandler
    )
    if hasattr(ast, "Match"):
        nesting_nodes = nesting_nodes + (ast.Match,)

    max_depth = current_depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, nesting_nodes):
            depth = calculate_ast_max_nesting(child, current_depth + 1)
        else:
            depth = calculate_ast_max_nesting(child, current_depth)
        if depth > max_depth:
            max_depth = depth

    return max_depth


def calculate_ast_cognitive_complexity(node: ast.AST, nesting_level: int = 0) -> int:
    """
    Calculates cognitive complexity of an AST node according to Sonar / Opus 5.5 standards.
    Increments for control structures with nesting penalties.
    """
    complexity = 0

    branching_nodes = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler)
    if hasattr(ast, "Match"):
        branching_nodes = branching_nodes + (ast.Match,)

    for child in ast.iter_child_nodes(node):
        if isinstance(child, branching_nodes):
            complexity += 1 + nesting_level
            complexity += calculate_ast_cognitive_complexity(child, nesting_level + 1)
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            complexity += calculate_ast_cognitive_complexity(child, nesting_level + 1)
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
            complexity += calculate_ast_cognitive_complexity(child, nesting_level)
        elif isinstance(child, (ast.Try, ast.With, ast.AsyncWith)):
            complexity += calculate_ast_cognitive_complexity(child, nesting_level)
        else:
            complexity += calculate_ast_cognitive_complexity(child, nesting_level)

    return complexity


def inspect_python_diff_hygiene(
    workspace_dir: Path,
    rel_path: str,
    old_content: str,
    new_content: str
) -> Tuple[List[str], List[str]]:
    """Inspects Python code diff for docstring deletion and excessive nesting blowup."""
    violations: List[str] = []
    fixes: List[str] = []

    # Check docstring preservation
    old_docs = extract_python_docstrings(old_content)
    new_docs = extract_python_docstrings(new_content)

    for name, old_doc in old_docs.items():
        if len(old_doc) < 10:
            continue  # Ignore trivial 1-word docstrings

        if name in new_docs:
            new_doc = new_docs[name]
            # Docstring completely deleted
            if not new_doc:
                violations.append(
                    f"DocstringLoss in {rel_path}: docstring for '{name}' was removed."
                )
                fixes.append(f"Restore existing docstring for '{name}' in {rel_path}.")
            # Docstring severely truncated (> 70% content removed)
            elif len(new_doc) < len(old_doc) * 0.3:
                violations.append(
                    f"DocstringTruncated in {rel_path}: docstring for '{name}' was significantly truncated."
                )
                fixes.append(f"Preserve existing docstring details for '{name}' in {rel_path}.")

    # Check KISS nesting depth and cognitive complexity delta
    old_nesting: Dict[str, int] = {}
    old_cognitive: Dict[str, int] = {}
    try:
        old_tree = ast.parse(old_content)
        for node in ast.walk(old_tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                old_nesting[node.name] = calculate_ast_max_nesting(node, current_depth=1)
                old_cognitive[node.name] = calculate_ast_cognitive_complexity(node, nesting_level=0)
    except SyntaxError as old_err:
        logging.getLogger(__name__).debug("AST parse of old revision failed for %s: %s", rel_path, old_err)

    try:
        new_tree = ast.parse(new_content)
        for node in ast.walk(new_tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                new_depth = calculate_ast_max_nesting(node, current_depth=1)
                old_depth = old_nesting.get(node.name)

                func_text = ""
                try:
                    func_text = ast.get_source_segment(new_content, node) or ""
                except Exception:
                    func_text = ""
                func_doc = ast.get_docstring(node) or ""
                has_safe = "# safe-bounds" in func_text or "# nosec" in func_text or "# safe-bounds" in func_doc or "# nosec" in func_doc

                if not has_safe:
                    # Existing function whose nesting expanded significantly
                    if old_depth is not None and new_depth >= old_depth + 3 and new_depth > 6:
                        violations.append(
                            f"ComplexityBlowup in {rel_path}: function '{node.name}' nesting expanded from {old_depth} to {new_depth} (KISS violation)."
                        )
                        fixes.append(
                            f"Refactor '{node.name}' in {rel_path} using early returns or helper functions to flatten logic."
                        )
                    # Newly created function with extreme nesting
                    elif old_depth is None and new_depth > 7:
                        violations.append(
                            f"ExcessiveNesting in {rel_path}: new function '{node.name}' has nesting depth of {new_depth} (exceeds limit 7, KISS violation)."
                        )
                        fixes.append(
                            f"Refactor new function '{node.name}' in {rel_path} to reduce nesting depth."
                        )

                    new_cog = calculate_ast_cognitive_complexity(node, nesting_level=0)
                    old_cog = old_cognitive.get(node.name)
                    if old_cog is not None and (new_cog >= old_cog + 10) and new_cog > 15:
                        violations.append(
                            f"CognitiveComplexityBlowup in {rel_path}: function '{node.name}' cognitive complexity increased from {old_cog} to {new_cog} (exceeds limit 15, KISS violation)."
                        )
                        fixes.append(
                            f"Refactor '{node.name}' in {rel_path} to reduce cognitive complexity below 15 by extracting helpers."
                        )
                    elif old_cog is None and new_cog > 15:
                        violations.append(
                            f"ExcessiveCognitiveComplexity in {rel_path}: new function '{node.name}' cognitive complexity is {new_cog} (exceeds limit 15, KISS violation)."
                        )
                        fixes.append(
                            f"Refactor new function '{node.name}' in {rel_path} to reduce cognitive complexity below 15."
                        )
    except SyntaxError as new_err:
        logging.getLogger(__name__).debug("AST parse of new content failed for %s: %s", rel_path, new_err)

    return violations, fixes


def parse_unified_diff(diff_text: str) -> Dict[str, Dict[str, Any]]:
    """Parses unified diff into per-file added and deleted line statistics."""
    file_diffs: Dict[str, Dict[str, Any]] = {}
    current_file = None

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split(" ")
            if len(parts) >= 4:
                b_path = parts[3]
                if b_path.startswith("b/"):
                    current_file = b_path[2:]
                    file_diffs[current_file] = {
                        "added_comments": 0,
                        "deleted_comments": 0,
                        "added_lines": 0,
                        "deleted_lines": 0,
                    }
        elif current_file and current_file in file_diffs:
            if line.startswith("+++ ") or line.startswith("--- ") or line.startswith("@@"):
                continue

            stripped = line[1:].strip() if len(line) > 1 else ""
            is_comment = (
                stripped.startswith("#") or
                stripped.startswith("//") or
                stripped.startswith("/*") or
                stripped.startswith("*") or
                stripped.startswith('"""') or
                stripped.startswith("'''")
            )

            if line.startswith("+"):
                file_diffs[current_file]["added_lines"] += 1
                if is_comment:
                    file_diffs[current_file]["added_comments"] += 1
            elif line.startswith("-"):
                file_diffs[current_file]["deleted_lines"] += 1
                if is_comment:
                    file_diffs[current_file]["deleted_comments"] += 1

    return file_diffs


def audit_diff_guard(
    workspace_dir: Path,
    cached: bool = False,
    specific_files: Optional[List[Path]] = None
) -> Dict[str, Any]:
    """Audits workspace git diff against code hygiene, documentation, and KISS invariants."""
    ws = workspace_dir.resolve()
    report: Dict[str, Any] = {
        "status": "PASS",
        "violations": [],
        "suggested_fixes": [],
        "details": {}
    }

    diff_text = get_git_diff_text(ws, cached=cached)
    if not diff_text.strip():
        report["details"]["notice"] = "No git diff detected"
        return report

    parsed_diffs = parse_unified_diff(diff_text)
    specific_rel_paths = None
    if specific_files is not None:
        specific_rel_paths = set()
        for f in specific_files:
            try:
                f_res = f.resolve()
                if ws in f_res.parents or f_res == ws:
                    specific_rel_paths.add(str(f_res.relative_to(ws)).replace("\\", "/"))
            except (ValueError, OSError) as resolve_err:
                sys.stderr.write(f"[diff_guard] Notice: path resolution error: {resolve_err}\n")

    for rel_path, stats in parsed_diffs.items():
        if specific_rel_paths is not None and rel_path not in specific_rel_paths:
            continue

        file_path = ws / rel_path
        if not file_path.is_file():
            continue  # Deleted or renamed file

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                new_content = f.read()
        except OSError:
            continue

        # Check comment stripping invariant
        # If deleted comments > 4 and net comment reduction > 3
        net_comment_drop = stats["deleted_comments"] - stats["added_comments"]
        if stats["deleted_comments"] >= 4 and net_comment_drop >= 3:
            # Check if this is not a complete file deletion/rewrite
            if stats["added_lines"] > 0:
                report["violations"].append(
                    f"CommentStripping in {rel_path}: removed {stats['deleted_comments']} comment lines without replacement (net reduction of {net_comment_drop})."
                )
                report["suggested_fixes"].append(
                    f"Maintain documentation integrity: restore explanatory comments in {rel_path}."
                )

        # Check aggressive code purges without structural replacement
        if stats["deleted_lines"] > 120 and stats["added_lines"] < 10:
            report["violations"].append(
                f"AggressiveDeletion in {rel_path}: removed {stats['deleted_lines']} lines with only {stats['added_lines']} lines added."
            )
            report["suggested_fixes"].append(
                f"Verify intentionality of large deletion in {rel_path}."
            )

        # Python-specific AST docstring and nesting checks
        if file_path.suffix.lower() in (".py", ".pyi"):
            old_content = get_git_file_content(ws, rel_path, revision="HEAD")
            if old_content:
                py_viols, py_fixes = inspect_python_diff_hygiene(
                    ws, rel_path, old_content, new_content
                )
                report["violations"].extend(py_viols)
                report["suggested_fixes"].extend(py_fixes)

    if report["violations"]:
        report["status"] = "RETRY"

    report["details"]["files_inspected"] = list(parsed_diffs.keys())
    return report


def main():
    parser = argparse.ArgumentParser(description="Antigravity AST Diff Guard")
    parser.add_argument("--workspace", default=".", help="Root workspace directory (default: .)")
    parser.add_argument("--cached", action="store_true", help="Inspect staged (cached) diff only")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON format")

    args = parser.parse_args()
    ws_dir = Path(args.workspace).resolve()

    if not ws_dir.is_dir():
        sys.stderr.write(f"Error: Workspace directory does not exist: {ws_dir}\n")
        sys.exit(1)

    result = audit_diff_guard(ws_dir, cached=args.cached)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result["status"] == "PASS":
            print("PASS: AST diff inspection passed with zero documentation or KISS violations.")
        else:
            print("RETRY: Diff hygiene violations detected:")
            for v in result["violations"]:
                print(f"  - {v}")
            print("\nSuggested fixes:")
            for s in result["suggested_fixes"]:
                print(f"  - {s}")
            sys.exit(1)


if __name__ == "__main__":
    main()
