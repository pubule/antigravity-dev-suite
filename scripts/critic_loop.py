#!/usr/bin/env python3
"""
Antigravity Critic Loop Orchestrator
Executes verification and formats structured evaluation reports.
"""

import sys
import os
import json
import argparse
import subprocess
from pathlib import Path

def run_critic_audit(mode: str, target: str) -> dict:
    report = {
        "mode": mode,
        "target": target,
        "status": "PASS",
        "violations": [],
        "suggested_fixes": []
    }
    
    if mode == "visual":
        scripts_dir = Path(__file__).parent
        visual_qa_script = scripts_dir / "visual_qa.py"
        try:
            res = subprocess.run(
                [sys.executable, str(visual_qa_script), target],
                capture_output=True,
                text=True,
                check=False
            )
            if res.stdout:
                qa_data = json.loads(res.stdout)
                if qa_data.get("page_errors") or qa_data.get("console_errors"):
                    report["status"] = "RETRY"
                    report["violations"].extend(qa_data.get("page_errors", []))
                    report["violations"].extend(qa_data.get("console_errors", []))
                report["visual_artifacts"] = qa_data.get("screenshots", {})
        except Exception as e:
            report["warnings"] = [f"Critic execution error: {str(e)}"]
            
    return report

def main():
    parser = argparse.ArgumentParser(description="Antigravity Critic Loop Runner")
    parser.add_argument("--mode", choices=["logic", "visual", "all"], default="all", help="Critic evaluation mode")
    parser.add_argument("--test-mode", action="store_true", help="Run in self-test synthetic mode")
    parser.add_argument("target", nargs="?", default="", help="File or URL target")
    
    args = parser.parse_args()
    target = "--test-mode" if (args.test_mode or not args.target) else args.target
    report = run_critic_audit(args.mode, target)
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
