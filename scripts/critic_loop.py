#!/usr/bin/env python3
"""
Antigravity Critic Loop Orchestrator (Cross-Platform)
Executes deep verification and formats structured evaluation reports for logic, AST, and visual QA.
Compatible with Windows 10/11, macOS, and Linux.
"""

import sys
import os
import re
import ast
import json
import glob
import argparse
import subprocess
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
    from auto_debug_runner import get_last_syntax_error, clear_last_syntax_error
except ImportError:
    get_last_syntax_error = lambda: None
    clear_last_syntax_error = lambda: False

SECRET_PATTERNS = [
    (re.compile(r'\b(?:sk-[a-zA-Z0-9_\-]{20,}|ghp_[a-zA-Z0-9]{20,}|github_pat_[a-zA-Z0-9_]{50,}|glpat-[a-zA-Z0-9_\-]{20,}|xox[baprs]-[0-9a-zA-Z]{10,48}|sk_live_[0-9a-zA-Z]{24,}|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16})\b'), "API key / token"),
    (re.compile(r'(?i)aws_secret_access_key\s*[:=]\s*[\'"]?[A-Za-z0-9/+=]{40}[\'"]?'), "AWS Secret Access Key"),
    (re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'), "Private Key"),
]

REDOS_PATTERN = re.compile(r'\([^\)]*(?<!\\\\)[\+\*][^\)]*\)(?<!\\\\)[\+\*]|\([^\)\\]*[\+\*]\)\{[0-9]+,\}')
UNPROTECTED_FETCH = re.compile(r'^\s*fetch\s*\(')

def audit_code_logic(target: str, test_mode: bool = False, submode: str = "all") -> dict:
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

    for file in files_to_check:
        if check_syntax:
            errs = validate_code_file(file)
            if errs:
                logic_report["status"] = "RETRY"
                for err in errs:
                    logic_report["violations"].append(err)
                    logic_report["suggested_fixes"].append(f"Fix syntax/delimiter defect in {file.name}")

        # Security, hygiene, and semantic complexity checks
        if check_security or check_semantic:
            try:
                with open(file, "r", encoding="utf-8", errors="replace") as fc:
                    content = fc.read()

                # 1. OWASP Top 10 Hardcoded Secret Scan
                if check_security:
                    for pat, desc in SECRET_PATTERNS:
                        if pat.search(content):
                            logic_report["status"] = "RETRY"
                            logic_report["violations"].append(f"SecurityViolation in {file.name}: potential hardcoded secret detected ({desc})")
                            logic_report["suggested_fixes"].append("Extract secret into secure environment variable")

                # 2. Defensive Engineering & Semantic AST in Python
                if file.suffix in [".py", ".pyi"]:
                    try:
                        tree = ast.parse(content, filename=str(file))
                        for node in ast.walk(tree):
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
                                        logic_report["status"] = "RETRY"
                                        action_word = "pass" if is_pass else "..."
                                        logic_report["violations"].append(f"EmptyExceptionHandling in {file.name}: empty 'except' block with {action_word} at line {node.lineno}")
                                        logic_report["suggested_fixes"].append("Handle exception or log with contextual details")

                            # Mutable default arguments (def fn(x=[]))
                            if check_semantic and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                all_defaults = list(node.args.defaults) + [d for d in node.args.kw_defaults if d is not None]
                                for d in all_defaults:
                                    if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                                        logic_report["status"] = "RETRY"
                                        logic_report["violations"].append(
                                            f"MutableDefaultArgument in {file.name}: function '{node.name}' defines mutable default argument at line {node.lineno}"
                                        )
                                        logic_report["suggested_fixes"].append(
                                            f"Use None as default in '{node.name}' and initialize collection dynamically inside body"
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
                                            logic_report["status"] = "RETRY"
                                            logic_report["violations"].append(
                                                f"ReDoSRisk in {file.name}: regex contains nested quantifiers '{m.group(0)}' with catastrophic backtracking risk at line {node.lineno}"
                                            )
                                            logic_report["suggested_fixes"].append(
                                                "Refactor regex to eliminate nested quantifiers and prevent catastrophic backtracking"
                                            )
                    except Exception as ast_err:
                        logic_report["details"][f"{file.name}_ast_notice"] = str(ast_err)

                # 3. JavaScript / TypeScript Semantic & Concurrency Checks
                if check_semantic and file.suffix in [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"]:
                    for line_idx, line in enumerate(content.splitlines(), start=1):
                        stripped = line.strip()
                        # Unawaited fetch call
                        if UNPROTECTED_FETCH.search(line) and not stripped.startswith("//") and not stripped.startswith("/*"):
                            logic_report["status"] = "RETRY"
                            logic_report["violations"].append(
                                f"UnawaitedPromise in {file.name}: floating fetch() call without await, return, or void at line {line_idx}"
                            )
                            logic_report["suggested_fixes"].append(
                                "Await promise or handle rejection with .catch() or return statement"
                            )
                        # ReDoS in JS RegExp constructor or regex literals
                        if ("RegExp" in line or "= /" in line or line.startswith("/")) and not stripped.startswith("//"):
                            m = REDOS_PATTERN.search(line)
                            if m:
                                logic_report["status"] = "RETRY"
                                logic_report["violations"].append(
                                    f"ReDoSRisk in {file.name}: regex contains nested quantifiers '{m.group(0)}' at line {line_idx}"
                                )
                                logic_report["suggested_fixes"].append(
                                    "Refactor regex to eliminate nested quantifiers and prevent catastrophic backtracking"
                                )
            except Exception as read_err:
                logic_report["details"][f"{file.name}_read_notice"] = str(read_err)

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

def run_critic_audit(mode: str, target: str, test_mode: bool = False) -> dict:
    report = {
        "mode": mode,
        "target": "synthetic_test" if test_mode else target,
        "status": "PASS",
        "violations": [],
        "suggested_fixes": []
    }

    # 1. Logic & AST Critique
    if mode in ["logic", "all", "syntax", "security", "complexity", "semantic"]:
        logic_res = audit_code_logic(target, test_mode=test_mode, submode=mode)
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

    return report

def main():
    parser = argparse.ArgumentParser(description="Antigravity Critic Loop Runner (Claude Opus 5.5 Standard)")
    parser.add_argument("--mode", choices=["logic", "visual", "syntax", "security", "complexity", "semantic", "all"], default="all", help="Critic evaluation mode")
    parser.add_argument("--test-mode", action="store_true", help="Run in self-test synthetic mode")
    parser.add_argument("--target", dest="target_flag", default=None, help="Target file or directory (flag form)")
    parser.add_argument("target", nargs="?", default="", help="File or directory target (positional)")

    args = parser.parse_args()
    is_test = args.test_mode or (args.target == "--test-mode") or (args.target_flag == "--test-mode")
    raw_target = args.target_flag if args.target_flag is not None else args.target
    target = "" if is_test else raw_target

    report = run_critic_audit(args.mode, target, test_mode=is_test)
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["status"] == "PASS" else 1)

if __name__ == "__main__":
    main()
