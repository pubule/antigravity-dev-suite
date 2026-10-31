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
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

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
        assert data.get("version") == "1.7.1"

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

def test_rust_lifetimes():
    with tempfile.NamedTemporaryFile(suffix=".rs", mode="w", delete=False) as f:
        f.write("""
pub struct Buffer<'a, 'b> {
    data: &'a [u8],
    tag: &'b str,
}

impl<'a, 'b> Buffer<'a, 'b> where 'a: 'b {
    pub fn process(s: &'a str) -> &'a str {
        println!("{}", s);
        s
    }
}
""")
        rs_file = f.name

    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": rs_file}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == "", f"Rust lifetimes caused false positive: {stderr}"
    finally:
        if os.path.exists(rs_file):
            os.remove(rs_file)

def test_rust_raw_strings_and_chars():
    with tempfile.NamedTemporaryFile(suffix=".rs", mode="w", delete=False) as f:
        f.write("""
fn check_rust_literals() {
    let c = 'a';
    let newline = '\\n';
    let single_quote = '\\'';
    let raw_json = r#"{"nested": [1, 2, 3], "bracket": "{"}"#;
    let raw_plain = r"simple { raw string } without hash";
    let byte_raw = br#"byte raw { string }"#;
    let count = 42;
    assert_eq!(c, 'a');
}
""")
        rs_file = f.name

    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": rs_file}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == "", f"Rust raw strings or char literals caused false positive: {stderr}"
    finally:
        if os.path.exists(rs_file):
            os.remove(rs_file)

def test_cpp_raw_strings():
    with tempfile.NamedTemporaryFile(suffix=".cpp", mode="w", delete=False) as f:
        f.write("""
#include <iostream>
#include <string>

int main() {
    const char* raw1 = R"(Unbalanced bracket { inside raw string)";
    const char* raw2 = R"delim(Nested ) bracket and "quotes" )delim";
    const char* regular = "normal string {";
    return 0;
}
""")
        cpp_file = f.name

    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": cpp_file}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == "", f"C++ raw strings caused false positive: {stderr}"
    finally:
        if os.path.exists(cpp_file):
            os.remove(cpp_file)

def test_js_regex_delimiters():
    with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
        f.write("""
const rx = /^[)}]/;
const rx2 = /["\\']+/g;
const rx3 = /\\//;
const fn = () => /\\(/;
function getRegex() {
    return /\\[/;
}
switch (val) {
    case /test/:
        break;
}
const arrayWithRegex = [ /first/, /second/ ];
const ternary = condition ? /patternA/ : /patternB/;
function valid() { return 1; }
""")
        ts_file = f.name

    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": ts_file}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == "", f"JS regex delimiters caused false positive: {stderr}"
    finally:
        if os.path.exists(ts_file):
            os.remove(ts_file)

def test_js_division_and_bracket_detection():
    # 1. Valid division expressions must not cause errors
    with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
        f.write("""
function calculate(a: number, b: number, arr: number[]) {
    const d1 = 10 / 2;
    const d2 = (a + b) / 2;
    const d3 = arr[0] / 2;
    const d4 = a / b;
    return d1 + d2 + d3 + d4;
}
""")
        good_ts = f.name

    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": good_ts}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == "", f"Valid division caused false positive: {stderr}"
    finally:
        if os.path.exists(good_ts):
            os.remove(good_ts)

    # 2. Bracket mismatch after division expressions must still be detected
    with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
        f.write("""
function calculate(a: number, b: number) {
    const d = 10 / 2;
    const unclosed = (1 + 2;
    return d;
}
""")
        bad_ts = f.name

    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": bad_ts}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert "BracketMismatch" in stderr or "UnclosedBracket" in stderr or "unmatched" in stderr or "unclosed" in stderr
    finally:
        if os.path.exists(bad_ts):
            os.remove(bad_ts)

def test_jsonc_trailing_commas_and_strings():
    with tempfile.NamedTemporaryFile(suffix=".jsonc", mode="w", delete=False) as f:
        f.write("""{
  "title": "Comma in string, [test], {ok}",
  "trailing_url": "http://domain.com/path,with,commas",
  "items": [
    1,
    2,
    3, // trailing comma in array
  ],
  "nested": {
    "key": "value", // trailing comma in object
  },
}""")
        jsonc_file = f.name

    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": jsonc_file}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == "", f"JSONC trailing commas or string values caused false positive: {stderr}"
    finally:
        if os.path.exists(jsonc_file):
            os.remove(jsonc_file)

def test_tool_call_argument_extraction():
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("def bad_syntax(:\n    pass\n")
        bad_file = f.name

    try:
        # Test AbsolutePath
        payload1 = json.dumps({"toolCall": {"name": "write_file", "args": {"AbsolutePath": bad_file}}})
        _, _, stderr1 = run_script("auto_debug_runner.py", [], input_data=payload1)
        assert "SyntaxError" in stderr1

        # Test target_file
        payload2 = json.dumps({"toolCall": {"name": "edit_file", "args": {"target_file": bad_file}}})
        _, _, stderr2 = run_script("auto_debug_runner.py", [], input_data=payload2)
        assert "SyntaxError" in stderr2

        # Test defensive extraction against null / malformed inputs
        from validator_core import extract_target_file
        assert extract_target_file({"toolCall": None}) == ""
        assert extract_target_file({"toolCall": {"args": None}}) == ""
        assert extract_target_file({"args": "string instead of dict"}) == ""
        assert extract_target_file(None) == ""
        assert extract_target_file(12345) == ""
    finally:
        if os.path.exists(bad_file):
            os.remove(bad_file)

def test_template_integrity():
    gemini_md = PLUGIN_ROOT / "templates" / "project-git-template" / "GEMINI.md"
    assert gemini_md.exists()
    content = gemini_md.read_text(encoding="utf-8")
    assert "file:///.agents" not in content, "Invalid root file URI in template GEMINI.md"

def test_backslash_arithmetic_escapes():
    with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
        # 3 backslashes followed by quote: \\\" (escaped quote)
        f.write('const s = "escaped\\\\\\"quote"; function valid() { return 1; }\n')
        ts_file = f.name

    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": ts_file}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == "", f"Backslash arithmetic caused false positive: {stderr}"
    finally:
        if os.path.exists(ts_file):
            os.remove(ts_file)

def test_tsx_jsx_components():
    with tempfile.NamedTemporaryFile(suffix=".tsx", mode="w", delete=False) as f:
        f.write('export function Card({ count }: { count: number }) {\n  return <div className={count > 0 ? "active" : "idle"}><span>{count < 10 ? "low" : "high"}</span></div>;\n}\n')
        tsx_file = f.name

    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": tsx_file}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == "", f"TSX JSX delimiters caused false positive: {stderr}"
    finally:
        if os.path.exists(tsx_file):
            os.remove(tsx_file)

def test_socket_server_dual_stack_probe():
    from visual_qa import is_http_server_active
    # Port 65534 is unlikely to be bound, probe should quickly return False without throwing exceptions
    active = is_http_server_active(65534)
    assert active is False

def test_js_ts_template_literal_nesting():
    # 1. Nested template literal with brackets inside strings should not cause false positives
    with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
        f.write(r"const s1 = `outer ${ `}` } end`;" + "\n" + r"const s2 = `outer ${ `{` } end`;" + "\nfunction test() { return 1; }\n")
        ts_file = f.name

    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": ts_file}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == "", f"Nested template literals caused false positive: {stderr}"
    finally:
        if os.path.exists(ts_file):
            os.remove(ts_file)

    # 2. Syntax errors inside template literal expressions must be caught
    with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
        f.write('const broken = `val: ${ [1, 2 } end`;\n')
        bad_ts = f.name

    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": bad_ts}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert "BracketMismatch" in stderr or "unmatched" in stderr or "UnclosedBracket" in stderr
    finally:
        if os.path.exists(bad_ts):
            os.remove(bad_ts)

def test_html_tag_validation():
    # 1. Valid HTML
    with tempfile.NamedTemporaryFile(suffix=".html", mode="w", delete=False) as f:
        f.write('<!DOCTYPE html><html><head><title>Test</title></head><body><div><p>Hello</p></div></body></html>')
        good_html = f.name

    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": good_html}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == ""
    finally:
        if os.path.exists(good_html):
            os.remove(good_html)

    # 2. Broken HTML (unmatched tag)
    with tempfile.NamedTemporaryFile(suffix=".html", mode="w", delete=False) as f:
        f.write('<div><span>Hello</div></span>')
        bad_html = f.name

    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": bad_html}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert "HTMLTagMismatch" in stderr or "TagMismatch" in stderr or "HTMLError" in stderr
    finally:
        if os.path.exists(bad_html):
            os.remove(bad_html)

def test_subagent_definitions():
    agents_dir = PLUGIN_ROOT / "agents"
    agent_files = list(agents_dir.glob("*.md"))
    assert len(agent_files) >= 3, "Missing subagent persona markdown files"
    for agent_file in agent_files:
        content = agent_file.read_text(encoding="utf-8")
        assert content.startswith("---"), f"Missing YAML frontmatter in {agent_file.name}"
        assert "name:" in content, f"Missing name in {agent_file.name}"
        assert "description:" in content, f"Missing description in {agent_file.name}"

if __name__ == "__main__":
    print("Running Complete Antigravity Dev Suite Test Suite...")
    test_manifests()
    print("✔ Manifests valid")
    test_subagent_definitions()
    print("✔ Subagent definitions valid")
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
    test_rust_lifetimes()
    print("✔ Rust lifetimes check passed")
    test_rust_raw_strings_and_chars()
    print("✔ Rust raw strings and char literals check passed")
    test_cpp_raw_strings()
    print("✔ C++ raw strings check passed")
    test_js_regex_delimiters()
    print("✔ JS regex delimiters check passed")
    test_js_division_and_bracket_detection()
    print("✔ JS division and bracket detection check passed")
    test_jsonc_trailing_commas_and_strings()
    print("✔ JSONC trailing commas and strings check passed")
    test_tool_call_argument_extraction()
    print("✔ Tool call argument extraction check passed")
    test_template_integrity()
    print("✔ Template integrity check passed")
    test_backslash_arithmetic_escapes()
    print("✔ Backslash arithmetic escapes check passed")
    test_tsx_jsx_components()
    print("✔ TSX/JSX components check passed")
    test_socket_server_dual_stack_probe()
    print("✔ Socket server dual-stack probe check passed")
    test_js_ts_template_literal_nesting()
    print("✔ JS/TS template literal nesting passed")
    test_html_tag_validation()
    print("✔ HTML tag validation passed")
    print("\n🎉 ALL TESTS PASSED (100% GREEN)")
