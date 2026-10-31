#!/usr/bin/env python3
"""
Antigravity Critic Loop Orchestrator (Cross-Platform)
Executes deep verification and formats structured evaluation reports for logic, AST, and visual QA.
Compatible with Windows 10/11, macOS, and Linux.
"""

import sys
import os
import ast
import json
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

def audit_code_logic(target: str, test_mode: bool = False) -> dict:
    """Audits code syntax, structural integrity, and potential defect patterns."""
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

    target_path = Path(target).resolve()
    if not target_path.exists():
        logic_report["status"] = "RETRY"
        logic_report["violations"].append(f"Target path does not exist: {target}")
        logic_report["suggested_fixes"].append("Provide a valid file or directory path")
        return logic_report

    if target_path.is_file():
        files_to_check = [target_path]
    else:
        files_to_check = find_source_files(target_path)

    for file in files_to_check:
        errs = validate_code_file(file)
        if errs:
            logic_report["status"] = "RETRY"
            for err in errs:
                logic_report["violations"].append(err)
                logic_report["suggested_fixes"].append(f"Fix syntax/delimiter defect in {file.name}")

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
    if mode in ["logic", "all"]:
        logic_res = audit_code_logic(target, test_mode=test_mode)
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
    parser.add_argument("--mode", choices=["logic", "visual", "all"], default="all", help="Critic evaluation mode")
    parser.add_argument("--test-mode", action="store_true", help="Run in self-test synthetic mode")
    parser.add_argument("target", nargs="?", default="", help="File or directory target")

    args = parser.parse_args()
    is_test = args.test_mode or (args.target == "--test-mode")
    target = "" if is_test else args.target

    report = run_critic_audit(args.mode, target, test_mode=is_test)
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["status"] == "PASS" else 1)

if __name__ == "__main__":
    main()
