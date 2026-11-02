#!/usr/bin/env python3
"""
Antigravity Critic Loop Orchestrator (Cross-Platform)
Executes deep verification and formats structured evaluation reports for logic, AST, and visual QA.
Compatible with Windows 10/11, macOS, and Linux.
"""

from __future__ import annotations

import sys
import os
import re
import ast
import json
import glob
import hashlib
import argparse
import tempfile
import subprocess
from typing import Any
from pathlib import Path

# Add current scripts directory to sys.path for robust relative import
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from validator_core import validate_code_file, find_source_files
except ImportError:
    import validator_core
    validate_code_file = validator_core.validate_code_file
    find_source_files = validator_core.find_source_files

try:
    from auto_debug_runner import (
        get_last_syntax_error,
        clear_last_syntax_error,
        record_critic_run,
        get_last_critic_run,
        clear_last_critic_run,
    )
except ImportError:
    get_last_syntax_error = lambda: None
    clear_last_syntax_error = lambda: False
    record_critic_run = lambda *args, **kwargs: None
    get_last_critic_run = lambda: None
    clear_last_critic_run = lambda: False

try:
    from api_contract_guard import audit_api_contract_drift
except ImportError:
    audit_api_contract_drift = None

try:
    from diff_guard import audit_diff_guard
except ImportError:
    audit_diff_guard = None

def get_critic_cache_path(workspace_dir: Path | None = None) -> Path:
    """Returns filesystem path for incremental AST critic cache."""
    ws = Path(workspace_dir or Path.cwd()).resolve()
    cache_dir = ws / ".agy_cache"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / "critic_cache.json"
    except (OSError, PermissionError):
        fallback_dir = Path(tempfile.gettempdir()) / "agy_critic_cache"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        ws_hash = hashlib.md5(str(ws).encode("utf-8")).hexdigest()[:8]
        return fallback_dir / f"critic_cache_{ws_hash}.json"

def compute_file_sha256(file_path: Path) -> str:
    """Computes SHA-256 digest of file contents for incremental cache invalidation."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()

def clear_critic_cache(workspace_dir: Path | None = None) -> bool:
    """Purges persistent incremental critic cache."""
    cache_file = get_critic_cache_path(workspace_dir)
    if cache_file.is_file():
        try:
            cache_file.unlink()
            return True
        except OSError:
            return False
    return False

SECRET_PATTERNS = [
    (re.compile(r'\b(?:sk-[a-zA-Z0-9_\-]{20,}|ghp_[a-zA-Z0-9]{20,}|github_pat_[a-zA-Z0-9_]{50,}|glpat-[a-zA-Z0-9_\-]{20,}|xox[baprs]-[0-9a-zA-Z]{10,48}|sk_live_[0-9a-zA-Z]{24,}|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16})\b'), "API key / token"),
    (re.compile(r'(?i)aws_secret_access_key\s*[:=]\s*[\'"]?[A-Za-z0-9/+=]{40}[\'"]?'), "AWS Secret Access Key"),
    (re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'), "Private Key"),
]

REDOS_PATTERN = re.compile(r'\([^\)]*(?<!\\\\)[\+\*][^\)]*\)(?<!\\\\)[\+\*]|\([^\)\\]*[\+\*]\)\{[0-9]+,\}')
UNPROTECTED_FETCH = re.compile(r'^\s*fetch\s*\(')
UNSAFE_EVAL_JS = re.compile(r'\b(eval|new\s+Function)\s*\(')
UNSAFE_INNER_HTML = re.compile(r'(?:\.innerHTML\s*=\s*(?!DOMPurify\.sanitize)|dangerouslySetInnerHTML\s*=\s*\{\s*\{\s*__html:\s*(?!DOMPurify\.sanitize))')
GO_UNHANDLED_PANIC = re.compile(r'\bpanic\s*\(')
GO_MUTEX_LOCK = re.compile(r'\b(?P<lockvar>\w+)\.(Lock|RLock)\(\)')
RUST_UNWRAP_EXPECT = re.compile(r'\.(unwrap|expect)\s*\(')
SQL_KEYWORDS_PATTERN = re.compile(r'(?i)\b(SELECT\s+[\*\w\s,]+?\s+FROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b')
SQL_UNSAFE_ADD_NOT_NULL = re.compile(r'(?i)\bALTER\s+TABLE\s+\S+\s+ADD\s+(?:COLUMN\s+)?\S+\s+[^\n;]+?\bNOT\s+NULL\b(?!\s+DEFAULT)')
SQL_NON_CONCURRENT_INDEX = re.compile(r'(?i)\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+(?!CONCURRENTLY\b)')
SQL_UNSAFE_DROP = re.compile(r'(?i)\bDROP\s+(?:TABLE|COLUMN)\b')
SQL_UNSAFE_ALTER_TYPE = re.compile(r'(?i)\bALTER\s+(?:TABLE\s+\S+\s+)?(?:ALTER\s+COLUMN\s+\S+\s+TYPE|MODIFY\s+\S+)\b')

def audit_code_logic(target: str, test_mode: bool = False, submode: str = "all", use_cache: bool = True) -> dict:
    """Audits code syntax, structural integrity, OWASP security, and hygiene defect patterns."""
    logic_report = {
        "status": "PASS",
        "violations": [],
        "suggested_fixes": [],
        "details": {}
    }

    if test_mode:
        sample_code = "def hello():\n    return 'world'\n"
        try:
            ast.parse(sample_code)
            logic_report["details"]["synthetic_test"] = "AST parse successful"
        except SyntaxError as e:
            logic_report["status"] = "RETRY"
            logic_report["violations"].append(f"Synthetic syntax error: {str(e)}")
            logic_report["suggested_fixes"].append("Fix syntax in synthetic generator")
        return logic_report

    # Disambiguate HTTP URLs, empty targets, globs, and comma-separated targets
    if not target or target.startswith("http://") or target.startswith("https://") or target.startswith("localhost:") or target.startswith("127.0.0.1:"):
        raw_targets = [str(Path.cwd())]
    else:
        raw_targets = [t.strip() for t in target.split(",") if t.strip()]

    files_to_check: list[Path] = []
    seen_files: set[Path] = set()

    for item in raw_targets:
        if any(char in item for char in ["*", "?", "["]):
            matched = glob.glob(os.path.expanduser(item), recursive=True)
            if not matched:
                logic_report["status"] = "RETRY"
                logic_report["violations"].append(f"No files matched glob pattern: {item}")
                logic_report["suggested_fixes"].append("Check pattern expression")
            for m in matched:
                mp = Path(m).resolve()
                if mp.is_file() and mp not in seen_files:
                    seen_files.add(mp)
                    files_to_check.append(mp)
                elif mp.is_dir():
                    for f in find_source_files(mp):
                        if f not in seen_files:
                            seen_files.add(f)
                            files_to_check.append(f)
            continue

        target_path = Path(item).expanduser().resolve()
        if not target_path.exists():
            logic_report["status"] = "RETRY"
            logic_report["violations"].append(f"Target path does not exist: {item}")
            logic_report["suggested_fixes"].append("Provide a valid file or directory path")
            continue

        if target_path.is_file():
            if target_path not in seen_files:
                seen_files.add(target_path)
                files_to_check.append(target_path)
        else:
            for f in find_source_files(target_path):
                if f not in seen_files:
                    seen_files.add(f)
                    files_to_check.append(f)

    check_syntax = submode in ["all", "logic", "syntax"]
    check_security = submode in ["all", "logic", "security"]
    check_semantic = submode in ["all", "logic", "security", "complexity", "semantic"]

    cache: dict[str, Any] = {}
    cache_path = get_critic_cache_path() if (use_cache and not test_mode) else None
    if use_cache and not test_mode:
        try:
            if cache_path.is_file():
                with open(cache_path, "r", encoding="utf-8") as cf:
                    cache = json.load(cf)
        except Exception:
            cache = {}

    cache_dirty = False

    for file in files_to_check:
        file_sha = None
        cache_key = f"{file.resolve()}:{submode}"
        if use_cache and not test_mode and file.is_file():
            try:
                file_sha = compute_file_sha256(file)
                if cache_key in cache and cache[cache_key].get("sha256") == file_sha:
                    cached_entry = cache[cache_key]
                    if cached_entry.get("status") == "RETRY":
                        logic_report["status"] = "RETRY"
                    logic_report["violations"].extend(cached_entry.get("violations", []))
                    logic_report["suggested_fixes"].extend(cached_entry.get("suggested_fixes", []))
                    continue
            except Exception:
                file_sha = None

        file_viols: list[str] = []
        file_fixes: list[str] = []

        if check_syntax:
            errs = validate_code_file(file)
            if errs:
                for err in errs:
                    file_viols.append(err)
                    file_fixes.append(f"Fix syntax/delimiter defect in {file.name}")

        # Security, hygiene, and semantic complexity checks
        if check_security or check_semantic:
            try:
                with open(file, "r", encoding="utf-8", errors="replace") as fc:
                    content = fc.read()

                # 1. OWASP Top 10 Hardcoded Secret Scan
                if check_security:
                    for pat, desc in SECRET_PATTERNS:
                        if pat.search(content):
                            file_viols.append(f"SecurityViolation in {file.name}: potential hardcoded secret detected ({desc})")
                            file_fixes.append("Extract secret into secure environment variable")

                # 2. Defensive Engineering & Semantic AST in Python
                if file.suffix in [".py", ".pyi"]:
                    is_test_file = file.name.startswith("test_") or file.name.endswith("_test.py") or "/tests/" in str(file) or "\\tests\\" in str(file)
                    content_lines = content.splitlines()
                    try:
                        tree = ast.parse(content, filename=str(file))
                        for p in ast.walk(tree):
                            for ch in ast.iter_child_nodes(p):
                                ch.parent = p

                        for node in ast.walk(tree):
                            lineno = getattr(node, "lineno", 0)
                            start_line = max(0, lineno - 1)
                            end_line = max(0, getattr(node, "end_lineno", lineno))
                            node_text = "\n".join(content_lines[start_line:end_line])
                            has_nosec = "# nosec" in node_text or "# safe-shell" in node_text

                            # Empty exception handling
                            if check_security and isinstance(node, ast.ExceptHandler):
                                if len(node.body) == 1:
                                    stmt = node.body[0]
                                    is_pass = isinstance(stmt, ast.Pass)
                                    is_ellipsis = (
                                        isinstance(stmt, ast.Expr)
                                        and isinstance(stmt.value, ast.Constant)
                                        and stmt.value.value is Ellipsis
                                    )
                                    if is_pass or is_ellipsis:
                                        action_word = "pass" if is_pass else "..."
                                        file_viols.append(f"EmptyExceptionHandling in {file.name}: empty 'except' block with {action_word} at line {lineno}")
                                        file_fixes.append("Handle exception or log with contextual details")

                            # Mutable default arguments (def fn(x=[]))
                            if check_semantic and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                all_defaults = list(node.args.defaults) + [d for d in node.args.kw_defaults if d is not None]
                                for d in all_defaults:
                                    if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                                        file_viols.append(
                                            f"MutableDefaultArgument in {file.name}: function '{node.name}' defines mutable default argument at line {lineno}"
                                        )
                                        file_fixes.append(
                                            f"Use None as default in '{node.name}' and initialize collection dynamically inside body"
                                        )

                            # Test rigor check in test files (Vacuous / Shallow tests)
                            if is_test_file and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                if node.name.startswith("test_") or node.name.endswith("_test"):
                                    if "# safe-test" not in node_text:
                                        assert_count = 0
                                        trivial_assert = False
                                        for child in ast.walk(node):
                                            if isinstance(child, ast.Assert):
                                                assert_count += 1
                                                if isinstance(child.test, ast.Constant) and child.test.value is True:
                                                    trivial_assert = True
                                                elif isinstance(child.test, ast.Compare):
                                                    if isinstance(child.test.left, ast.Constant) and len(child.test.comparators) == 1 and isinstance(child.test.comparators[0], ast.Constant) and child.test.left.value == child.test.comparators[0].value:
                                                        trivial_assert = True
                                            elif isinstance(child, ast.Call):
                                                c_func = child.func
                                                if isinstance(c_func, ast.Attribute) and isinstance(c_func.value, ast.Name) and c_func.value.id == "self" and c_func.attr.startswith("assert"):
                                                    assert_count += 1
                                                    if c_func.attr in ("assertTrue", "assertFalse") and child.args and isinstance(child.args[0], ast.Constant):
                                                        trivial_assert = True
                                                    elif c_func.attr == "assertEqual" and len(child.args) >= 2 and isinstance(child.args[0], ast.Constant) and isinstance(child.args[1], ast.Constant) and child.args[0].value == child.args[1].value:
                                                        trivial_assert = True
                                                elif isinstance(c_func, ast.Attribute) and isinstance(c_func.value, ast.Name) and c_func.value.id == "pytest" and c_func.attr in ("raises", "fail"):
                                                    assert_count += 1
                                            elif isinstance(child, ast.With):
                                                for item in child.items:
                                                    if isinstance(item.context_expr, ast.Call) and isinstance(item.context_expr.func, ast.Attribute) and isinstance(item.context_expr.func.value, ast.Name) and item.context_expr.func.value.id == "pytest" and item.context_expr.func.attr == "raises":
                                                        assert_count += 1
                                        if assert_count == 0:
                                            file_viols.append(
                                                f"VacuousTest in {file.name}: test function '{node.name}' has 0 assertions at line {lineno}"
                                            )
                                            file_fixes.append(
                                                f"Add explicit assertions verifying return values or state invariants to '{node.name}'"
                                            )
                                        elif assert_count == 1 and trivial_assert:
                                            file_viols.append(
                                                f"ShallowTest in {file.name}: test function '{node.name}' contains only 1 trivial assertion at line {lineno}"
                                            )
                                            file_fixes.append(
                                                f"Implement meaningful assertions verifying actual domain state or return values in '{node.name}'"
                                            )

                            # ReDoS check in Python re.compile calls
                            if check_semantic and isinstance(node, ast.Call):
                                func = node.func
                                is_re = False
                                if isinstance(func, ast.Attribute) and func.attr == "compile":
                                    if isinstance(func.value, ast.Name) and func.value.id in ("re", "regex"):
                                        is_re = True
                                elif isinstance(func, ast.Name) and func.id in ("compile", "re_compile"):
                                    is_re = True
                                if is_re and node.args:
                                    first_arg = node.args[0]
                                    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                                        m = REDOS_PATTERN.search(first_arg.value)
                                        if m:
                                            file_viols.append(
                                                f"ReDoSRisk in {file.name}: regex contains nested quantifiers '{m.group(0)}' with catastrophic backtracking risk at line {lineno}"
                                            )
                                            file_fixes.append(
                                                "Refactor regex to eliminate nested quantifiers and prevent catastrophic backtracking"
                                            )

                                # Missing timeout in subprocess and network calls
                                if not is_test_file and not has_nosec and "# safe-timeout" not in node_text:
                                    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "subprocess":
                                        if func.attr in ("run", "Popen", "check_output", "call", "check_call"):
                                            if not any(kw.arg == "timeout" for kw in node.keywords):
                                                file_viols.append(
                                                    f"MissingTimeoutRisk in {file.name}: subprocess.{func.attr}() called without explicit timeout at line {lineno}"
                                                )
                                                file_fixes.append(
                                                    "Provide explicit timeout parameter (e.g. timeout=30) to prevent indefinite hangs"
                                                )
                                    client_id = ""
                                    if isinstance(func, ast.Attribute):
                                        if isinstance(func.value, ast.Name) and func.value.id in ("requests", "httpx"):
                                            client_id = func.value.id
                                        elif isinstance(func.value, ast.Attribute) and func.value.attr == "request" and isinstance(func.value.value, ast.Name) and func.value.value.id == "urllib":
                                            client_id = "urllib.request"
                                    if client_id and func.attr in ("get", "post", "put", "delete", "patch", "request", "urlopen"):
                                        if not any(kw.arg == "timeout" for kw in node.keywords):
                                            file_viols.append(
                                                f"MissingTimeoutRisk in {file.name}: {client_id}.{func.attr}() called without explicit timeout at line {lineno}"
                                            )
                                            file_fixes.append(
                                                "Provide explicit timeout parameter to avoid indefinite network hangs"
                                            )

                                # Unmanaged resource handles (open without with)
                                if isinstance(func, ast.Name) and func.id == "open":
                                    if not has_nosec and "# safe-resource" not in node_text:
                                        p_node = getattr(node, "parent", None)
                                        if not (isinstance(p_node, ast.withitem) and p_node.context_expr is node):
                                            file_viols.append(
                                                f"UnmanagedResourceRisk in {file.name}: open() called without 'with' context manager at line {lineno}"
                                            )
                                            file_fixes.append(
                                                "Use 'with open(...) as handle:' context manager to ensure deterministic cleanup"
                                            )

                                # Discarded / Floating asyncio.create_task
                                if not is_test_file and not has_nosec and "# safe-task" not in node_text:
                                    is_task = False
                                    if isinstance(func, ast.Attribute) and func.attr == "create_task":
                                        if isinstance(func.value, ast.Name) and func.value.id == "asyncio":
                                            is_task = True
                                    elif isinstance(func, ast.Name) and func.id == "create_task":
                                        is_task = True
                                    if is_task:
                                        p_node = getattr(node, "parent", None)
                                        if isinstance(p_node, ast.Expr):
                                            file_viols.append(
                                                f"FloatingTaskRisk in {file.name}: discarded asyncio.create_task() reference at line {lineno} (risks premature garbage collection)"
                                            )
                                            file_fixes.append(
                                                "Retain task reference in a collection or await it to prevent premature GC cancellation"
                                            )

                                # Command injection via subprocess shell=True
                                if not is_test_file and not has_nosec:
                                    is_shell_true = False
                                    for kw in node.keywords:
                                        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                            is_shell_true = True
                                            break
                                    if is_shell_true and node.args:
                                        first_arg = node.args[0]
                                        if not (isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str)):
                                            file_viols.append(
                                                f"CommandInjectionRisk in {file.name}: subprocess call with shell=True and dynamic arguments at line {lineno}"
                                            )
                                            file_fixes.append(
                                                "Pass arguments as a list without shell=True to prevent command injection"
                                            )

                                # Insecure deserialization (pickle)
                                if not is_test_file and not has_nosec:
                                    if isinstance(func, ast.Attribute) and func.attr in ("load", "loads"):
                                        if isinstance(func.value, ast.Name) and func.value.id == "pickle":
                                            file_viols.append(
                                                f"InsecureDeserialization in {file.name}: unsafe pickle.{func.attr}() at line {lineno}"
                                            )
                                            file_fixes.append(
                                                "Use secure serialization formats (JSON, Protobuf, or SafeLoader)"
                                            )

                                # Dangerous dynamic eval/exec
                                if not is_test_file and not has_nosec:
                                    if isinstance(func, ast.Name) and func.id in ("eval", "exec"):
                                        file_viols.append(
                                            f"DangerousEval in {file.name}: dynamic invocation of {func.id}() at line {lineno}"
                                        )
                                        file_fixes.append(
                                            f"Replace {func.id}() with explicit AST parsing or structured data parsing"
                                        )

                            # SQL injection in f-strings
                            if check_semantic and not is_test_file and isinstance(node, ast.JoinedStr):
                                has_sql_kw = False
                                for part in node.values:
                                    if isinstance(part, ast.Constant) and isinstance(part.value, str):
                                        if SQL_KEYWORDS_PATTERN.search(part.value):
                                            has_sql_kw = True
                                            break
                                if has_sql_kw and any(isinstance(part, ast.FormattedValue) for part in node.values):
                                    file_viols.append(
                                        f"SQLInjectionRisk in {file.name}: dynamic string interpolation in SQL statement at line {lineno}"
                                    )
                                    file_fixes.append(
                                        "Use parameterized queries or prepared statements instead of f-strings"
                                    )

                            # Quadratic traps in loops (linear searches, .index(), or unindexed collections)
                            if check_semantic and not is_test_file and isinstance(node, (ast.For, ast.While)):
                                for child in ast.walk(node):
                                    if child is node:
                                        continue
                                    child_lineno = getattr(child, "lineno", 0)
                                    line_txt = content.splitlines()[child_lineno - 1] if 1 <= child_lineno <= len(content.splitlines()) else ""
                                    if "# nosec" in line_txt or "# safe-bounds" in line_txt:
                                        continue

                                    # Sequence lookup .index() inside loop
                                    if isinstance(child, ast.Call) and isinstance(getattr(child, "func", None), ast.Attribute):
                                        if child.func.attr == "index":
                                            file_viols.append(
                                                f"QuadraticTrap in {file.name}: linear sequence lookup .index() inside loop at line {child_lineno} (risks O(n^2) complexity)"
                                            )
                                            file_fixes.append(
                                                "Convert sequence to dict or hash map before loop to achieve O(1) lookups"
                                            )
                                            break

                                    # Linear membership search 'in <list>' inside loop
                                    if isinstance(child, ast.Compare):
                                        for op, comp in zip(child.ops, child.comparators):
                                            if isinstance(op, (ast.In, ast.NotIn)) and isinstance(comp, ast.Name):
                                                var_lower = comp.id.lower()
                                                if any(var_lower.endswith(sfx) for sfx in ("_list", "_arr", "_array", "_items", "_records", "_rows")):
                                                    file_viols.append(
                                                        f"QuadraticTrap in {file.name}: linear membership search 'in {comp.id}' inside loop at line {child_lineno} (risks O(n^2) complexity)"
                                                    )
                                                    file_fixes.append(
                                                        f"Convert '{comp.id}' to set or dict before loop to achieve O(1) membership testing"
                                                    )
                                                    break
                    except Exception as ast_err:
                        logic_report["details"][f"{file.name}_ast_notice"] = str(ast_err)

                # 3. JavaScript / TypeScript Semantic & Concurrency Checks
                if check_semantic and file.suffix in [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"]:
                    for line_idx, line in enumerate(content.splitlines(), start=1):
                        stripped = line.strip()
                        if stripped.startswith("//") or stripped.startswith("/*"):
                            continue
                        # Unawaited fetch call
                        if UNPROTECTED_FETCH.search(line):
                            file_viols.append(
                                f"UnawaitedPromise in {file.name}: floating fetch() call without await, return, or void at line {line_idx}"
                            )
                            file_fixes.append(
                                "Await promise or handle rejection with .catch() or return statement"
                            )
                        # Quadratic trap in JS/TS: indexOf or findIndex in loop
                        if any(pat in line for pat in [".indexOf(", ".findIndex("]) and ("// nosec" not in line and "// safe-bounds" not in line):
                            prev_context = "\n".join(content.splitlines()[max(0, line_idx - 6):line_idx])
                            if any(k in prev_context for k in ["for (", ".forEach(", ".map("]):
                                file_viols.append(
                                    f"QuadraticTrap in {file.name}: linear search inside iteration loop at line {line_idx} (risks O(n^2) complexity)"
                                )
                                file_fixes.append(
                                    "Index array into Map or Set before loop for O(1) lookups"
                                )
                        # ReDoS in JS RegExp constructor or regex literals
                        if "RegExp" in line or "= /" in line or line.startswith("/"):
                            m = REDOS_PATTERN.search(line)
                            if m:
                                file_viols.append(
                                    f"ReDoSRisk in {file.name}: regex contains nested quantifiers '{m.group(0)}' at line {line_idx}"
                                )
                                file_fixes.append(
                                    "Refactor regex to eliminate nested quantifiers and prevent catastrophic backtracking"
                                )
                        # Dangerous dynamic code evaluation
                        if UNSAFE_EVAL_JS.search(line):
                            file_viols.append(
                                f"DangerousEval in {file.name}: dynamic code execution via eval/Function at line {line_idx}"
                            )
                            file_fixes.append(
                                "Avoid dynamic code execution; use structured JSON or explicit handlers"
                            )
                        # XSS risk via innerHTML
                        if UNSAFE_INNER_HTML.search(line):
                            file_viols.append(
                                f"XSSRisk in {file.name}: unsanitized innerHTML or dangerouslySetInnerHTML at line {line_idx}"
                            )
                            file_fixes.append(
                                "Sanitize HTML using DOMPurify.sanitize() before assigning to DOM"
                            )

                # 4. Go Production Panic & Mutex Concurrency Checks
                if check_semantic and file.suffix == ".go" and not file.name.endswith("_test.go"):
                    go_lines = content.splitlines()
                    for line_idx, line in enumerate(go_lines, start=1):
                        stripped = line.strip()
                        if stripped.startswith("//") or stripped.startswith("/*"):
                            continue
                        if GO_UNHANDLED_PANIC.search(line):
                            file_viols.append(
                                f"UnhandledPanic in {file.name}: unhandled panic() in production Go code at line {line_idx}"
                            )
                            file_fixes.append(
                                "Return an error (error value) instead of panicking in production code"
                            )
                        # Check for unreleased Mutex Lock
                        m_lock = GO_MUTEX_LOCK.search(line)
                        if m_lock and "// safe-lock" not in line and "/* safe-lock */" not in line:
                            lock_var = m_lock.group("lockvar")
                            method = m_lock.group(2)
                            unlock_method = "RUnlock" if method == "RLock" else "Unlock"
                            next_lines = "\n".join(go_lines[line_idx:line_idx + 6])
                            defer_pat = rf'defer\s+{re.escape(lock_var)}\.{unlock_method}\(\)'
                            if not re.search(defer_pat, next_lines):
                                file_viols.append(
                                    f"UnprotectedMutexLock in {file.name}: {lock_var}.{method}() invoked without immediate defer {lock_var}.{unlock_method}() at line {line_idx}"
                                )
                                file_fixes.append(
                                    f"Add 'defer {lock_var}.{unlock_method}()' immediately after acquiring mutex lock"
                                )

                # 5. Rust Production Unwrap/Expect Checks
                if check_semantic and file.suffix == ".rs" and "test" not in str(file).lower():
                    lines = content.splitlines()
                    in_test_block = False
                    for line_idx, line in enumerate(lines, start=1):
                        stripped = line.strip()
                        if "#[cfg(test)]" in stripped or "#[test]" in stripped:
                            in_test_block = True
                        if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("#["):
                            continue
                        if "// safe-unwrap" in line or "/* safe-unwrap */" in line:
                            continue
                        if in_test_block:
                            continue
                        m = RUST_UNWRAP_EXPECT.search(line)
                        if m:
                            file_viols.append(
                                f"ProductionPanicRisk in {file.name}: .{m.group(1)}() in production Rust code at line {line_idx}"
                            )
                            file_fixes.append(
                                f"Handle Result/Option using ?, match, or unwrap_or instead of .{m.group(1)}()"
                            )

                # 6. Database Migration Safety & Zero-Downtime SQL Checks
                if check_semantic and file.suffix == ".sql":
                    is_safe_migration = "-- safe-migration" in content or "/* safe-migration */" in content
                    if not is_safe_migration:
                        for line_idx, line in enumerate(content.splitlines(), start=1):
                            stripped = line.strip()
                            if stripped.startswith("--") or stripped.startswith("/*"):
                                continue
                            if SQL_UNSAFE_ADD_NOT_NULL.search(line):
                                file_viols.append(
                                    f"UnsafeMigration in {file.name}: adding NOT NULL column without DEFAULT locks table at line {line_idx}"
                                )
                                file_fixes.append(
                                    "Provide DEFAULT value or add column as nullable first, backfill rows, then apply NOT NULL"
                                )
                            if SQL_NON_CONCURRENT_INDEX.search(line):
                                file_viols.append(
                                    f"UnsafeMigration in {file.name}: CREATE INDEX without CONCURRENTLY locks table against writes at line {line_idx}"
                                )
                                file_fixes.append(
                                    "Use CREATE INDEX CONCURRENTLY to avoid blocking table writes in production"
                                )
                            if SQL_UNSAFE_DROP.search(line) and "-- allow-drop" not in line:
                                file_viols.append(
                                    f"UnsafeMigration in {file.name}: DROP TABLE/COLUMN risks immediate data loss and downtime at line {line_idx}"
                                )
                                file_fixes.append(
                                    "Follow Rule 14 expand/contract pattern: deprecate column/table in release N, remove in release N+1"
                                )
                            if SQL_UNSAFE_ALTER_TYPE.search(line):
                                file_viols.append(
                                    f"UnsafeMigration in {file.name}: altering column type directly causes table rewrite lock at line {line_idx}"
                                )
                                file_fixes.append(
                                    "Add new column with target type additively, backfill data, and switch reads asynchronously"
                                )
            except Exception as read_err:
                logic_report["details"][f"{file.name}_read_notice"] = str(read_err)

        if file_viols:
            logic_report["status"] = "RETRY"
        logic_report["violations"].extend(file_viols)
        logic_report["suggested_fixes"].extend(file_fixes)

        if use_cache and not test_mode and file_sha:
            cache[cache_key] = {
                "sha256": file_sha,
                "status": "RETRY" if file_viols else "PASS",
                "violations": file_viols,
                "suggested_fixes": file_fixes
            }
            cache_dirty = True

    if cache_dirty and use_cache and not test_mode:
        try:
            with open(cache_path, "w", encoding="utf-8") as cf:
                json.dump(cache, cf, indent=2)
        except Exception as cache_err:
            sys.stderr.write(f"[critic_cache] Notice: failed to write cache: {cache_err}\n")

    # 3. Check for any unresolved syntax errors cached from PostToolUse hooks
    if check_syntax:
        last_diag = get_last_syntax_error()
        if last_diag and isinstance(last_diag.get("errors"), list) and last_diag.get("errors"):
            diag_file_str = last_diag.get("file", "")
            diag_path = Path(diag_file_str).resolve() if diag_file_str else None
            if diag_path and (diag_path in files_to_check or not target or diag_file_str == target or str(diag_path) == str(Path(target).resolve())):
                for err in last_diag["errors"]:
                    if err not in logic_report["violations"]:
                        logic_report["status"] = "RETRY"
                        logic_report["violations"].append(err)
                        logic_report["suggested_fixes"].append(f"Fix recorded syntax defect in {diag_path.name}")

    # 4. Check for breaking API contract drift if in git workspace
    check_contract = submode in ["all", "contract"]
    if check_contract and audit_api_contract_drift and not test_mode:
        try:
            ws_target = target_path if 'target_path' in locals() and target_path.is_dir() else Path.cwd()
            drift = audit_api_contract_drift(ws_target, specific_files=files_to_check if target and target != "." else None)
            if drift.get("violations"):
                logic_report["status"] = "RETRY"
                logic_report["violations"].extend(drift["violations"])
                logic_report["suggested_fixes"].extend(drift.get("suggested_fixes", []))
            if drift.get("additions"):
                logic_report["details"]["api_contract_additions"] = drift["additions"]
        except Exception as drift_err:
            logic_report["details"]["api_contract_notice"] = str(drift_err)

    # 5. Check for documentation loss, comment stripping, and KISS diff violations
    check_diff = submode in ["all", "diff", "logic"]
    if check_diff and audit_diff_guard and not test_mode:
        try:
            ws_target = target_path if 'target_path' in locals() and target_path.is_dir() else Path.cwd()
            diff_res = audit_diff_guard(ws_target, specific_files=files_to_check if target and target != "." else None)
            if diff_res.get("violations"):
                logic_report["status"] = "RETRY"
                logic_report["violations"].extend(diff_res["violations"])
                logic_report["suggested_fixes"].extend(diff_res.get("suggested_fixes", []))
            if diff_res.get("details"):
                logic_report["details"]["diff_guard"] = diff_res["details"]
        except Exception as dg_err:
            logic_report["details"]["diff_guard_notice"] = str(dg_err)

    if logic_report["status"] == "PASS" and check_syntax:
        clear_last_syntax_error()

    return logic_report

def audit_visual_qa(target: str, test_mode: bool = False) -> dict:
    """Invokes visual_qa.py runner and parses UI defects and console errors."""
    visual_report = {
        "status": "PASS",
        "violations": [],
        "suggested_fixes": [],
        "visual_artifacts": {},
        "warnings": []
    }

    if not test_mode and target:
        tp = Path(target)
        if tp.is_file() and tp.suffix.lower() in [
            ".py", ".go", ".rs", ".java", ".c", ".cpp", ".sql", ".sh", ".bash",
            ".zsh", ".ps1", ".md", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"
        ]:
            return visual_report

    visual_qa_script = SCRIPTS_DIR / "visual_qa.py"

    cmd = [sys.executable, str(visual_qa_script)]
    if test_mode or not target:
        cmd.append("--test-mode")
    else:
        cmd.append(target)

    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=45,
            check=False
        )
        if res.stdout:
            try:
                qa_data = json.loads(res.stdout)
                if qa_data.get("page_errors"):
                    visual_report["status"] = "RETRY"
                    visual_report["violations"].extend([f"Page error: {e}" for e in qa_data["page_errors"]])
                    visual_report["suggested_fixes"].append("Resolve runtime JavaScript exception on page")
                if qa_data.get("console_errors"):
                    visual_report["status"] = "RETRY"
                    visual_report["violations"].extend([f"Console error: {e}" for e in qa_data["console_errors"]])
                    visual_report["suggested_fixes"].append("Fix console error in frontend components")
                if qa_data.get("a11y_violations"):
                    visual_report["status"] = "RETRY"
                    visual_report["violations"].extend([f"A11yViolation: {v}" for v in qa_data["a11y_violations"]])
                    visual_report["suggested_fixes"].append("Fix accessibility violations to conform with WCAG 2.1 AA")
                if qa_data.get("status") == "ERROR":
                    visual_report["status"] = "RETRY"
                    visual_report["violations"].extend(qa_data.get("warnings", []))
                visual_report["visual_artifacts"] = qa_data.get("screenshots", {})
                if qa_data.get("warnings"):
                    visual_report["warnings"].extend(qa_data["warnings"])
            except json.JSONDecodeError:
                visual_report["warnings"].append(f"Unparseable stdout from visual QA runner: {res.stdout.strip()}")
    except subprocess.TimeoutExpired:
        visual_report["status"] = "RETRY"
        visual_report["violations"].append(f"VisualQATimeout: visual QA runner timed out after 45s on target {target}")
        visual_report["suggested_fixes"].append("Ensure target web server responds within timeout limit")
    except Exception as e:
        visual_report["warnings"].append(f"Critic execution error: {str(e)}")

    return visual_report

def run_critic_audit(mode: str, target: str, test_mode: bool = False, use_cache: bool = True) -> dict:
    report = {
        "mode": mode,
        "target": "synthetic_test" if test_mode else target,
        "status": "PASS",
        "violations": [],
        "suggested_fixes": []
    }

    # 1. Logic & AST Critique
    if mode in ["logic", "all", "syntax", "security", "complexity", "semantic"]:
        logic_res = audit_code_logic(target, test_mode=test_mode, submode=mode, use_cache=use_cache)
        if logic_res["status"] == "RETRY":
            report["status"] = "RETRY"
        report["violations"].extend(logic_res["violations"])
        report["suggested_fixes"].extend(logic_res["suggested_fixes"])
        if logic_res.get("details"):
            report["logic_details"] = logic_res["details"]

    # 2. Visual Critique
    if mode in ["visual", "all"]:
        visual_res = audit_visual_qa(target, test_mode=test_mode)
        if visual_res["status"] == "RETRY":
            report["status"] = "RETRY"
        report["violations"].extend(visual_res["violations"])
        report["suggested_fixes"].extend(visual_res["suggested_fixes"])
        if visual_res.get("visual_artifacts"):
            report["visual_artifacts"] = visual_res["visual_artifacts"]
        if visual_res.get("warnings"):
            report["warnings"] = visual_res["warnings"]

    if not test_mode and record_critic_run:
        try:
            ws = Path.cwd().resolve()
            target_path = Path(target).resolve() if target else None
            if not target_path or ws in target_path.parents or target_path == ws:
                record_critic_run(
                    status=report["status"],
                    mode=mode,
                    target=str(target_path) if target_path else ".",
                    violations=report["violations"],
                    workspace_dir=ws
                )
        except Exception as rec_err:
            sys.stderr.write(f"[critic_loop] Notice: failed to record critic run: {rec_err}\n")

    return report

def main():
    parser = argparse.ArgumentParser(description="Antigravity Critic Loop Runner (Claude Opus 5.5 Standard)")
    parser.add_argument("--mode", choices=["logic", "visual", "syntax", "security", "complexity", "semantic", "all"], default="all", help="Critic evaluation mode")
    parser.add_argument("--test-mode", action="store_true", help="Run in self-test synthetic mode")
    parser.add_argument("--no-cache", action="store_true", help="Bypass incremental file caching")
    parser.add_argument("--clear-cache", action="store_true", help="Clear incremental AST critic cache")
    parser.add_argument("--target", dest="target_flag", default=None, help="Target file or directory (flag form)")
    parser.add_argument("target", nargs="?", default="", help="File or directory target (positional)")

    args = parser.parse_args()

    if args.clear_cache:
        clear_critic_cache()
        print(json.dumps({"status": "PASS", "cleared_cache": True}))
        sys.exit(0)

    is_test = args.test_mode or (args.target == "--test-mode") or (args.target_flag == "--test-mode")
    raw_target = args.target_flag if args.target_flag is not None else args.target
    target = "" if is_test else raw_target

    use_cache = not args.no_cache

    report = run_critic_audit(args.mode, target, test_mode=is_test, use_cache=use_cache)
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["status"] == "PASS" else 1)

if __name__ == "__main__":
    main()
