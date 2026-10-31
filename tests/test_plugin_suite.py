#!/usr/bin/env python3
"""
Comprehensive Test Suite for Antigravity Dev Suite
Tests syntax validation, delimiter scanner, critic loop, visual QA, and manifest configurations.
"""

import sys
import os
import json
import tempfile
import subprocess
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"

def run_script(script_name: str, args: list, input_data: str = None) -> tuple:
    cmd = [sys.executable, str(SCRIPTS_DIR / script_name)] + args
    res = subprocess.run(
        cmd,
        input=input_data,
        text=True,
        capture_output=True
    )
    return res.returncode, res.stdout, res.stderr

def test_manifests():
    # 1. plugin.json
    with open(PLUGIN_ROOT / "plugin.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data.get("name") == "antigravity-dev-suite"

    # 2. hooks.json
    with open(PLUGIN_ROOT / "hooks.json", "r", encoding="utf-8") as f:
        hooks = json.load(f)
        assert "antigravity-dev-suite-hooks" in hooks

    # 3. mcp_config.json
    with open(PLUGIN_ROOT / "mcp_config.json", "r", encoding="utf-8") as f:
        mcp = json.load(f)
        assert "mcpServers" in mcp

def test_auto_debug_runner_syntax_error():
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("def invalid_syntax(:\n    pass\n")
        bad_py = f.name

    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": bad_py}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0  # PostToolUse contract requires clean exit
        assert stdout.strip() == "{}"
        assert "SyntaxError" in stderr or "invalid_syntax" in stderr
    finally:
        if os.path.exists(bad_py):
            os.remove(bad_py)

def test_auto_debug_runner_valid_python():
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("def valid_function():\n    return 42\n")
        good_py = f.name

    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": good_py}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == ""
    finally:
        if os.path.exists(good_py):
            os.remove(good_py)

def test_auto_debug_runner_json_error():
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        f.write("{\ninvalid_json: 123\n}")
        bad_json = f.name

    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": bad_json}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert "JSONDecodeError" in stderr or "invalid_json" in stderr or "Error" in stderr
    finally:
        if os.path.exists(bad_json):
            os.remove(bad_json)

def test_auto_debug_runner_bracket_mismatch():
    with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
        f.write("function test() { const str = 'hello'; return (1 + 2]; }")
        bad_ts = f.name

    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": bad_ts}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert "BracketMismatch" in stderr or "unmatched" in stderr
    finally:
        if os.path.exists(bad_ts):
            os.remove(bad_ts)

def test_auto_debug_runner_comments_and_strings():
    with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
        # Delimiters inside quotes and comments should NOT cause errors
        f.write("const a = '{'; // }\n/* ( */\nfunction ok() { return [1, 2, 3]; }\n")
        good_js = f.name

    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": good_js}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == ""
    finally:
        if os.path.exists(good_js):
            os.remove(good_js)

def test_critic_loop_test_mode():
    code, stdout, stderr = run_script("critic_loop.py", ["--mode", "logic", "--test-mode"])
    assert code == 0
    data = json.loads(stdout)
    assert data["status"] == "PASS"

def test_visual_qa_test_mode():
    code, stdout, stderr = run_script("visual_qa.py", ["--test-mode"])
    assert code == 0
    data = json.loads(stdout)
    assert data["status"] == "SUCCESS"
    assert "desktop" in data.get("screenshots", {})
    assert "mobile" in data.get("screenshots", {})

def test_no_stub_rules():
    rules_dir = PLUGIN_ROOT / "rules"
    for rule_file in rules_dir.glob("*.md"):
        content = rule_file.read_text(encoding="utf-8")
        assert "<!-- Consolidated into" not in content, f"Stub file detected: {rule_file.name}"

if __name__ == "__main__":
    print("Running Complete Antigravity Dev Suite Test Suite...")
    test_manifests()
    print("✔ Manifests valid")
    test_critic_loop_test_mode()
    print("✔ Critic loop test-mode passed")
    test_visual_qa_test_mode()
    print("✔ Visual QA test-mode passed")
    test_auto_debug_runner_valid_python()
    print("✔ Auto debug runner valid python passed")
    test_auto_debug_runner_syntax_error()
    print("✔ Auto debug runner syntax error handling passed")
    test_auto_debug_runner_json_error()
    print("✔ Auto debug runner json error handling passed")
    test_auto_debug_runner_bracket_mismatch()
    print("✔ Auto debug runner bracket mismatch check passed")
    test_auto_debug_runner_comments_and_strings()
    print("✔ Auto debug runner comments and strings check passed")
    test_no_stub_rules()
    print("✔ No stub rules check passed")
    print("\n🎉 ALL TESTS PASSED (100% GREEN)")
