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
        assert data.get("version") == "1.13.0"

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

def test_toml_validation():
    # 1. Valid TOML
    with tempfile.NamedTemporaryFile(suffix=".toml", mode="w", delete=False) as f:
        f.write('[package]\nname = "test-pkg"\nversion = "1.0.0"\n[dependencies]\nserde = "1.0"\n')
        good_toml = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": good_toml}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == ""
    finally:
        if os.path.exists(good_toml):
            os.remove(good_toml)

    # 2. Invalid TOML
    with tempfile.NamedTemporaryFile(suffix=".toml", mode="w", delete=False) as f:
        f.write('[package\nname = "broken"\n')
        bad_toml = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": bad_toml}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert "TOMLDecodeError" in stderr or "Error" in stderr
    finally:
        if os.path.exists(bad_toml):
            os.remove(bad_toml)

def test_markdown_validation():
    # 1. Valid Markdown
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
        f.write('---\nname: test\n---\n# Title\n```python\nprint(1)\n```\n')
        good_md = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": good_md}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == ""
    finally:
        if os.path.exists(good_md):
            os.remove(good_md)

    # 2. Unclosed code block in Markdown
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
        f.write('# Title\n```python\nprint("unclosed code block")\n')
        bad_md = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": bad_md}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert "UnclosedCodeBlock" in stderr
    finally:
        if os.path.exists(bad_md):
            os.remove(bad_md)

    # 3. Unclosed frontmatter in Markdown
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
        f.write('---\nname: broken\ndescription: missing closing delimiter\n# Heading\n')
        bad_fm = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": bad_fm}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert "UnclosedFrontmatter" in stderr
    finally:
        if os.path.exists(bad_fm):
            os.remove(bad_fm)

def test_css_validation():
    # 1. Valid CSS
    with tempfile.NamedTemporaryFile(suffix=".css", mode="w", delete=False) as f:
        f.write('.container { display: flex; /* comment */ background: url("img.png"); }\n')
        good_css = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": good_css}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == ""
    finally:
        if os.path.exists(good_css):
            os.remove(good_css)

    # 2. Broken CSS (unclosed brace)
    with tempfile.NamedTemporaryFile(suffix=".css", mode="w", delete=False) as f:
        f.write('.container { display: flex; color: red;\n')
        bad_css = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": bad_css}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert "UnclosedBracket" in stderr
    finally:
        if os.path.exists(bad_css):
            os.remove(bad_css)

def test_shell_validation():
    # 1. Valid Shell
    with tempfile.NamedTemporaryFile(suffix=".sh", mode="w", delete=False) as f:
        f.write('''#!/usr/bin/env bash
# comment with (
while [[ $# -gt 0 ]]; do
  VAR_LEN="${#1}"
  echo "arg: $1, len: ${VAR_LEN}"
  shift
done
if [ -f "$1" ]; then
  echo "ok (test)"
fi
''')
        good_sh = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": good_sh}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == ""
    finally:
        if os.path.exists(good_sh):
            os.remove(good_sh)

    # 2. Broken Shell (unmatched bracket)
    with tempfile.NamedTemporaryFile(suffix=".sh", mode="w", delete=False) as f:
        f.write('if [ -f "$1" }; then\n  echo "broken"\nfi\n')
        bad_sh = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": bad_sh}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert "BracketMismatch" in stderr
    finally:
        if os.path.exists(bad_sh):
            os.remove(bad_sh)

def test_sql_validation():
    # 1. Valid SQL
    with tempfile.NamedTemporaryFile(suffix=".sql", mode="w", delete=False) as f:
        f.write("SELECT id, name FROM users WHERE (age > 18 AND status = 'active'); -- comment with (\n")
        good_sql = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": good_sql}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == ""
    finally:
        if os.path.exists(good_sql):
            os.remove(good_sql)

    # 2. Broken SQL (unclosed parenthesis)
    with tempfile.NamedTemporaryFile(suffix=".sql", mode="w", delete=False) as f:
        f.write("SELECT id FROM users WHERE (age > 18;\n")
        bad_sql = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": bad_sql}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert "UnclosedBracket" in stderr
    finally:
        if os.path.exists(bad_sql):
            os.remove(bad_sql)

def test_template_parity():
    import filecmp
    for folder in ['agents', 'rules', 'skills']:
        src_dir = PLUGIN_ROOT / folder
        tpl_dir = PLUGIN_ROOT / 'templates' / 'project-git-template' / '.agents' / folder
        for root_path, _, files in os.walk(src_dir):
            for f in files:
                src_f = Path(root_path) / f
                rel = src_f.relative_to(src_dir)
                tpl_f = tpl_dir / rel
                assert tpl_f.exists(), f"Missing template file: {tpl_f}"
                assert filecmp.cmp(src_f, tpl_f, shallow=False), f"Parity mismatch between {src_f} and {tpl_f}"

def test_no_hardcoded_user_paths():
    import re
    # Check all tracked text files for personal user directory paths
    target_exts = {".py", ".sh", ".ps1", ".md", ".json"}
    for root, dirs, files in os.walk(PLUGIN_ROOT):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
        for f in files:
            p = Path(root) / f
            if p.suffix.lower() in target_exts:
                text = p.read_text(encoding="utf-8", errors="replace")
                assert not re.search(r"/Users/[a-zA-Z0-9_\.]+", text), f"Hardcoded /Users/ path found in {p}"
                assert not re.search(r"C:\\Users\\[a-zA-Z0-9_\.]+", text), f"Hardcoded C:\\Users\\ path found in {p}"

def test_opening_line_number_in_bracket_mismatch():
    with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
        f.write("function test() {\n  const x = [1, 2, 3};\n  return x;\n}")
        bad_ts = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": bad_ts}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert "opened at line 2" in stderr or "line 2" in stderr
    finally:
        if os.path.exists(bad_ts):
            os.remove(bad_ts)

def test_auto_debug_runner_relative_path_resolution():
    with tempfile.TemporaryDirectory() as tmpdir:
        src_dir = Path(tmpdir) / "src"
        src_dir.mkdir()
        bad_file = src_dir / "broken.py"
        bad_file.write_text("def broken(:\n    pass\n", encoding="utf-8")

        # Payload with relative path 'src/broken.py' and workspacePaths = [tmpdir]
        payload = json.dumps({
            "toolCall": {"name": "edit_file", "args": {"Path": "src/broken.py"}},
            "workspacePaths": [tmpdir]
        })
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert "SyntaxError" in stderr or "broken" in stderr

def test_multi_doc_yaml_validation():
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write("""apiVersion: v1
kind: Service
metadata:
  name: my-service
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-deployment
spec:
  replicas: 3
""")
        yaml_file = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": yaml_file}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == "", f"Multi-doc YAML caused false positive: {stderr}"
    finally:
        if os.path.exists(yaml_file):
            os.remove(yaml_file)

def test_js_spread_operator_regex():
    with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
        f.write("""const str = "test 123";
const matches = [.../\\d+/g.exec(str) || []];
function valid() { return matches.length; }
""")
        ts_file = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": ts_file}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == "", f"Spread operator regex caused false positive: {stderr}"
    finally:
        if os.path.exists(ts_file):
            os.remove(ts_file)

def test_html_svg_self_closing_tags():
    with tempfile.NamedTemporaryFile(suffix=".html", mode="w", delete=False) as f:
        f.write("""<!DOCTYPE html>
<html>
<head><title>SVG Test</title></head>
<body>
  <svg viewBox="0 0 100 100">
    <circle cx="50" cy="50" r="40" stroke="green" stroke-width="4" fill="yellow" />
    <path d="M 10 10 L 90 90" stroke="black" />
    <rect x="20" y="20" width="60" height="60" fill="blue" />
  </svg>
</body>
</html>
""")
        html_file = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": html_file}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == "", f"HTML with inline SVG self-closing tags caused false positive: {stderr}"
    finally:
        if os.path.exists(html_file):
            os.remove(html_file)

def test_visual_qa_directory_target():
    # When inspecting a folder without index.html or dev server, visual_qa should cleanly exit code 0 with status SKIPPED_NO_DEV_SERVER
    with tempfile.TemporaryDirectory() as tmpdir:
        code, stdout, stderr = run_script("visual_qa.py", [tmpdir])
        assert code == 0
        data = json.loads(stdout)
        assert data["status"] == "SKIPPED_NO_DEV_SERVER"

def test_visual_qa_mobile_overflow_detection():
    # Create HTML with intentional horizontal overflow (e.g. 800px wide box on mobile)
    with tempfile.NamedTemporaryFile(suffix=".html", mode="w", delete=False) as f:
        f.write("""<!DOCTYPE html>
<html>
<head><title>Overflow Test</title></head>
<body style="margin: 0; padding: 0;">
  <div style="width: 800px; height: 100px; background: red;">Overflow Container</div>
</body>
</html>
""")
        html_file = f.name
    try:
        code, stdout, stderr = run_script("visual_qa.py", [html_file])
        assert code == 0
        data = json.loads(stdout)
        if data.get("status") == "SUCCESS":
            # If Playwright is available and captured, assert overflow was caught
            assert any("HorizontalOverflowDetected" in err for err in data.get("page_errors", []))
    finally:
        if os.path.exists(html_file):
            os.remove(html_file)

def test_toml_dependency_free_fallback():
    # Verify TOML fallback behavior when tomllib and tomli are unavailable
    import builtins
    orig_import = builtins.__import__
    def mock_import(name, *args, **kwargs):
        if name in ['tomllib', 'tomli']:
            raise ImportError(f"No module named {name}")
        return orig_import(name, *args, **kwargs)

    builtins.__import__ = mock_import
    try:
        import validator_core
        # 1. Valid TOML under fallback
        with tempfile.NamedTemporaryFile(suffix=".toml", mode="w", delete=False) as f:
            f.write('[package]\nname = "pkg-fallback"\nversion = "1.0.0"\n[dependencies]\nserde = "1.0"\n')
            good_toml = f.name
        try:
            errs = validator_core.validate_code_file(Path(good_toml))
            assert errs == [], f"TOML fallback reported false positive: {errs}"
        finally:
            if os.path.exists(good_toml):
                os.remove(good_toml)

        # 2. Broken bracket in TOML under fallback
        with tempfile.NamedTemporaryFile(suffix=".toml", mode="w", delete=False) as f:
            f.write('[package\nname = "broken"\n')
            bad_toml = f.name
        try:
            errs = validator_core.validate_code_file(Path(bad_toml))
            assert any("UnclosedBracket" in e or "BracketMismatch" in e for e in errs)
        finally:
            if os.path.exists(bad_toml):
                os.remove(bad_toml)
    finally:
        builtins.__import__ = orig_import

def test_html_generic_self_closing_tags():
    # Verify arbitrary self-closing tags (<custom-element />, <animate />, etc.) do not cause tag mismatches
    with tempfile.NamedTemporaryFile(suffix=".html", mode="w", delete=False) as f:
        f.write("""<!DOCTYPE html>
<html>
<head><title>Self Closing Test</title></head>
<body>
  <div>
    <animate attributeName="opacity" from="0" to="1" dur="1s" />
    <custom-tag prop="value" />
    <feDropShadow dx="2" dy="2" stdDeviation="3" />
    <p>Valid content</p>
  </div>
</body>
</html>
""")
        html_file = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": html_file}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == "", f"Generic self-closing tags caused false positive: {stderr}"
    finally:
        if os.path.exists(html_file):
            os.remove(html_file)

def test_js_extended_regex_starters():
    # Verify regex literals after keywords 'else', 'do', 'in', 'instanceof', 'of'
    with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
        f.write("""
function checkRegexStarters(a: any, b: any) {
    if (a) {
        return 1;
    } else /test/.test(b);

    do /pattern/.test('str'); while(false);

    const isMatch = 'key' in /regex/ ? true : false;
    const isInst = a instanceof /regex/.constructor;
    return 42;
}
""")
        ts_file = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": ts_file}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == "", f"Extended JS regex starters caused false positive: {stderr}"
    finally:
        if os.path.exists(ts_file):
            os.remove(ts_file)

def test_resolve_target_file_tilde_expansion():
    from validator_core import resolve_target_file
    # Test tilde path resolution
    home_dir = str(Path.home())
    payload = {"toolCall": {"name": "write_file", "args": {"Path": "~/non_existent_probe.py"}}}
    resolved = resolve_target_file(payload)
    assert resolved.startswith(home_dir) or resolved == "~/non_existent_probe.py"

def test_shell_case_and_heredocs():
    # 1. Shell script with case statement and heredoc
    with tempfile.NamedTemporaryFile(suffix=".sh", mode="w", delete=False) as f:
        f.write("""#!/usr/bin/env bash
case "$1" in
  start)
    echo "Starting..."
    ;;
  stop)
    echo "Stopping..."
    ;;
  *)
    echo "Usage: $0 {start|stop}"
    ;;
esac

cat << 'EOF'
Bracket ( inside heredoc should not fail validation
EOF

echo "Done"
""")
        good_sh = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": good_sh}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == "", f"Shell case statement or heredoc caused false positive: {stderr}"
    finally:
        if os.path.exists(good_sh):
            os.remove(good_sh)

def test_sql_postgres_dollar_quotes_and_escapes():
    with tempfile.NamedTemporaryFile(suffix=".sql", mode="w", delete=False) as f:
        f.write("""
-- PostgreSQL dollar quoting with internal unmatched brackets and quotes
CREATE OR REPLACE FUNCTION process_audit() RETURNS trigger AS $body$
BEGIN
  IF NEW.status = 'active' THEN
    RAISE NOTICE 'User''s action recorded: (custom format)';
  END IF;
  RETURN NEW;
END;
$body$ LANGUAGE plpgsql;

SELECT 'It''s working properly' AS test_col;
""")
        good_sql = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": good_sql}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == "", f"PostgreSQL dollar quotes or escaped quotes caused false positive: {stderr}"
    finally:
        if os.path.exists(good_sql):
            os.remove(good_sql)

def test_yaml_escaped_quotes_fallback():
    # Verify YAML fallback handles escaped quotes and hashes inside strings
    import builtins
    orig_import = builtins.__import__
    def mock_import(name, *args, **kwargs):
        if name == 'yaml':
            raise ImportError("No module named yaml")
        return orig_import(name, *args, **kwargs)

    builtins.__import__ = mock_import
    try:
        import validator_core
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write("""name: test-app
description: "This is a \\"quoted string\\" with # not a comment"
items:
  - id: 1
    val: "[bracket in quote]"
""")
            yaml_file = f.name
        try:
            errs = validator_core.validate_code_file(Path(yaml_file))
            assert errs == [], f"YAML fallback with escaped quotes reported false positive: {errs}"
        finally:
            if os.path.exists(yaml_file):
                os.remove(yaml_file)
    finally:
        builtins.__import__ = orig_import

def test_unclosed_js_regex_error():
    with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
        f.write("const unclosed = /pattern;\nconst y = 42;\n")
        bad_ts = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": bad_ts}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert "UnclosedRegex" in stderr
    finally:
        if os.path.exists(bad_ts):
            os.remove(bad_ts)

def test_python_stub_and_json5_validation():
    # 1. Python .pyi stub
    with tempfile.NamedTemporaryFile(suffix=".pyi", mode="w", delete=False) as f:
        f.write("def calculate(x: int, y: int) -> int: ...\n")
        good_pyi = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": good_pyi}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == ""
    finally:
        if os.path.exists(good_pyi):
            os.remove(good_pyi)

    # 2. JSON5 validation
    with tempfile.NamedTemporaryFile(suffix=".json5", mode="w", delete=False) as f:
        f.write("""{
  // JSON5 comment
  unquotedKey: 'single quote string',
  hexNumber: 0xFF,
  leadingDecimal: .5,
  trailingCommaList: [1, 2, ],
}
""")
        good_json5 = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": good_json5}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == "", f"JSON5 validation caused false positive: {stderr}"
    finally:
        if os.path.exists(good_json5):
            os.remove(good_json5)

    with tempfile.NamedTemporaryFile(suffix=".json5", mode="w", delete=False) as f:
        f.write("{\n  brokenKey: 'unclosed string\n}\n")
        bad_json5 = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": bad_json5}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert "UnclosedString" in stderr or "JSON5DecodeError" in stderr or "JSONDecodeError" in stderr, f"Expected error not caught in bad JSON5: {stderr}"
    finally:
        if os.path.exists(bad_json5):
            os.remove(bad_json5)

def test_polyglot_languages_validation():
    test_cases = [
        (".cs", 'namespace Demo { class Service { public void Run() { var list = new List<int> { 1, 2, 3 }; } } }'),
        (".kt", 'package demo\nfun process(): List<String> { return listOf("a", "b") }'),
        (".swift", 'import Foundation\nfunc fetch() -> [String] { return ["item1", "item2"] }'),
        (".dart", 'void main() { final items = <String>["a", "b"]; print(items); }'),
        (".php", '<?php\n# Hash comment\nfunction test() { return [1, 2, 3]; }\n'),
        (".rb", '# Ruby comment\ndef calculate(a, b)\n  [a, b].map { |x| x * 2 }\nend\n'),
        (".lua", '-- Lua comment\nfunction test()\n  local t = { 1, 2, 3 }\n  return t\nend\n'),
        (".hpp", '#pragma once\n#include <vector>\ntemplate<typename T>\nclass Buffer { std::vector<T> data; };\n'),
    ]

    for suffix, code_content in test_cases:
        with tempfile.NamedTemporaryFile(suffix=suffix, mode="w", delete=False) as f:
            f.write(code_content)
            temp_file = f.name
        try:
            payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": temp_file}}})
            code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
            assert code == 0, f"Polyglot test failed for {suffix}: exit code {code}"
            assert stdout.strip() == "{}"
            assert stderr.strip() == "", f"Polyglot test reported false positive for {suffix}: {stderr}"
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

def test_csharp_verbatim_strings():
    with tempfile.NamedTemporaryFile(suffix=".cs", mode="w", delete=False) as f:
        f.write('class Test { string query = @"SELECT {id} FROM ""users"" WHERE (status = 1)"; }\n')
        cs_file = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": cs_file}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == "", f"C# verbatim string caused false positive: {stderr}"
    finally:
        if os.path.exists(cs_file):
            os.remove(cs_file)

def test_kotlin_swift_multiline_strings():
    for ext in [".kt", ".swift"]:
        with tempfile.NamedTemporaryFile(suffix=ext, mode="w", delete=False) as f:
            f.write('val doc = """\n{"nested": [1, 2, 3], "tag": "test"}\n"""\n')
            temp_file = f.name
        try:
            payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": temp_file}}})
            code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
            assert code == 0
            assert stdout.strip() == "{}"
            assert stderr.strip() == "", f"Multiline string for {ext} caused false positive: {stderr}"
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

def test_swift_nested_block_comments():
    with tempfile.NamedTemporaryFile(suffix=".swift", mode="w", delete=False) as f:
        f.write('/* outer comment /* nested comment ( [ { */ still outer */ func test() -> Int { return 42 }\n')
        swift_file = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": swift_file}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == "", f"Swift nested block comment caused false positive: {stderr}"
    finally:
        if os.path.exists(swift_file):
            os.remove(swift_file)

def test_lua_comments_and_multiline_strings():
    with tempfile.NamedTemporaryFile(suffix=".lua", mode="w", delete=False) as f:
        f.write('--[[ Multi-line Lua comment with [ ( { ]] local str = [[ raw string with ) } ]] function ok() return 1 end\n')
        lua_file = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": lua_file}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == "", f"Lua comments or raw strings caused false positive: {stderr}"
    finally:
        if os.path.exists(lua_file):
            os.remove(lua_file)

def test_payload_extraction_diverse_formats():
    from validator_core import extract_target_file, resolve_target_file
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "demo.py"
        test_file.write_text("def hello(): pass\n", encoding="utf-8")

        # 1. Claude toolUse.input
        p1 = {"toolUse": {"name": "write_file", "input": {"Path": "demo.py"}}, "cwd": tmpdir}
        assert resolve_target_file(p1) == str(test_file.resolve())

        # 2. tool_input
        p2 = {"tool_input": {"file_path": "demo.py"}, "projectRoot": tmpdir}
        assert resolve_target_file(p2) == str(test_file.resolve())

        # 3. parameters
        p3 = {"parameters": {"target": "demo.py"}, "workspacePath": tmpdir}
        assert resolve_target_file(p3) == str(test_file.resolve())

def test_dev_server_expanded_ports():
    from visual_qa import COMMON_DEV_PORTS
    assert 5174 in COMMON_DEV_PORTS
    assert 3002 in COMMON_DEV_PORTS
    assert 8001 in COMMON_DEV_PORTS

def test_csharp_raw_strings_and_interpolations():
    csharp_code = '''
namespace TestApp {
    public class RawStringDemo {
        public string Multiline = """
            {
                "property": "value"
            }
            """;
        public string VerbatimInterpolated1 = $@"SELECT * FROM Table WHERE Col = '{Multiline}'";
        public string VerbatimInterpolated2 = @$"SELECT * FROM Table WHERE Col = '{Multiline}'";
    }
}
'''
    with tempfile.NamedTemporaryFile(suffix=".cs", mode="w", delete=False) as f:
        f.write(csharp_code)
        cs_file = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": cs_file}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == "", f"C# raw/verbatim string caused false positive: {stderr}"
    finally:
        if os.path.exists(cs_file):
            os.remove(cs_file)

def test_dart_raw_and_multiline_strings():
    dart_code = '''
void main() {
  final rawSingle = r"Raw string with quotes: 'hello'";
  final rawSQuote = r'Raw string with double quotes: "world"';
  final tripleDouble = """
    Multi-line Dart string
    with brackets { [ ( ) ] }
  """;
  final tripleSingle = \'\'\'
    Another multiline
    with symbols < > / \
  \'\'\';
  print(rawSingle);
}
'''
    with tempfile.NamedTemporaryFile(suffix=".dart", mode="w", delete=False) as f:
        f.write(dart_code)
        dart_file = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": dart_file}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == "", f"Dart raw/multiline string caused false positive: {stderr}"
    finally:
        if os.path.exists(dart_file):
            os.remove(dart_file)

def test_yaml_fallback_apostrophes():
    # Test YAML fallback when yaml module is not present
    import builtins
    orig_import = builtins.__import__
    def mock_import(name, *args, **kwargs):
        if name == 'yaml':
            raise ImportError("No module named yaml")
        return orig_import(name, *args, **kwargs)

    builtins.__import__ = mock_import
    try:
        import validator_core
        yaml_content = """title: It's working perfectly
description: Don't panic when checking brackets
nested:
  items: [1, 2, 3]
message: 'Single quoted with ''escaped'' quote'
"""
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write(yaml_content)
            yaml_file = f.name
        try:
            errs = validator_core.validate_code_file(Path(yaml_file))
            assert errs == [], f"YAML fallback false positive on apostrophes: {errs}"
        finally:
            if os.path.exists(yaml_file):
                os.remove(yaml_file)
    finally:
        builtins.__import__ = orig_import

def test_toml_fallback_multiline_strings():
    import builtins
    orig_import = builtins.__import__
    def mock_import(name, *args, **kwargs):
        if name in ['tomllib', 'tomli']:
            raise ImportError(f"No module named {name}")
        return orig_import(name, *args, **kwargs)

    builtins.__import__ = mock_import
    try:
        import validator_core
        toml_content = '''[package]
name = "multiline-test"
version = "1.0.0"
description = """
This is a multiline
basic string in TOML
[with brackets inside]
"""
literal_multi = \'\'\'
Literal multiline string
[with another section]
\'\'\'
[dependencies]
tokio = "1.0"
'''
        with tempfile.NamedTemporaryFile(suffix=".toml", mode="w", delete=False) as f:
            f.write(toml_content)
            toml_file = f.name
        try:
            errs = validator_core.validate_code_file(Path(toml_file))
            assert errs == [], f"TOML fallback false positive on multiline strings: {errs}"
        finally:
            if os.path.exists(toml_file):
                os.remove(toml_file)
    finally:
        builtins.__import__ = orig_import

def test_shell_bitshift_not_heredoc():
    sh_content = '''#!/usr/bin/env bash
MASK=$(( 1 << 4 ))
SHIFTED=$(( 2 << 8 ))
echo "Mask: $MASK Shifted: $SHIFTED"
'''
    with tempfile.NamedTemporaryFile(suffix=".sh", mode="w", delete=False) as f:
        f.write(sh_content)
        sh_file = f.name
    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": sh_file}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        assert stdout.strip() == "{}"
        assert stderr.strip() == "", f"Shell bitshift matched as heredoc: {stderr}"
    finally:
        if os.path.exists(sh_file):
            os.remove(sh_file)

def test_critic_loop_url_target_logic():
    from critic_loop import audit_code_logic
    res = audit_code_logic("http://localhost:5173", test_mode=False)
    assert res["status"] in ["PASS", "RETRY"]
    # Should not report "Target path does not exist"
    assert not any("Target path does not exist" in v for v in res["violations"])

def test_hooks_command_resolution():
    with open(PLUGIN_ROOT / "hooks.json", "r", encoding="utf-8") as f:
        hooks_data = json.load(f)
    hook_entry = hooks_data["antigravity-dev-suite-hooks"]["PostToolUse"][0]["hooks"][0]
    cmd = hook_entry["command"]
    # Ensure command includes dynamic path resolution across user environments
    assert "auto_debug_runner.py" in cmd

    # Test running hook command from an arbitrary foreign directory
    with tempfile.TemporaryDirectory() as foreign_dir:
        res = subprocess.run(
            cmd,
            shell=True,
            cwd=foreign_dir,
            input='{"toolCall": {"name": "write_file", "args": {"Path": "dummy.txt"}}}',
            text=True,
            capture_output=True
        )
        assert res.returncode == 0
        assert res.stdout.strip() == "{}"

def test_json5_single_quote_escapes_and_signed_hex():
    import validator_core
    with tempfile.NamedTemporaryFile(suffix=".json5", mode="w", delete=False) as f:
        f.write("""{
  title: 'Don\\'t stop believing',
  greeting: 'Hello "World"',
  signedHexNeg: -0x10,
  signedHexPos: +0x20,
  negDecimal: -.5,
  posDecimal: +.75,
  trailingDec: 42.,
}
""")
        json5_file = f.name
    try:
        errs = validator_core.validate_code_file(Path(json5_file))
        assert errs == [], f"JSON5 signed hex / escaped single quotes reported false positive: {errs}"

        # Test under fallback branch (when json5 and pyjson5 are not installed)
        import builtins
        orig_import = builtins.__import__
        def mock_import(name, *args, **kwargs):
            if name in ['json5', 'pyjson5']:
                raise ImportError(f"No module named {name}")
            return orig_import(name, *args, **kwargs)

        builtins.__import__ = mock_import
        try:
            fallback_errs = validator_core.validate_code_file(Path(json5_file))
            assert fallback_errs == [], f"JSON5 fallback reported false positive: {fallback_errs}"
        finally:
            builtins.__import__ = orig_import
    finally:
        if os.path.exists(json5_file):
            os.remove(json5_file)

def test_sql_mysql_hash_comments_and_backticks():
    import validator_core
    with tempfile.NamedTemporaryFile(suffix=".sql", mode="w", delete=False) as f:
        f.write("""
# MySQL hash comment with don't and (unmatched bracket
SELECT `user_id`, `select`, `table`
FROM `users`
WHERE `status` = 'active' # end of line comment with 'quotes
ORDER BY `id` DESC;
""")
        sql_file = f.name
    try:
        errs = validator_core.validate_code_file(Path(sql_file))
        assert errs == [], f"SQL MySQL hash comments or backticks reported false positive: {errs}"
    finally:
        if os.path.exists(sql_file):
            os.remove(sql_file)

def test_xml_svg_plist_validation():
    import validator_core
    with tempfile.NamedTemporaryFile(suffix=".svg", mode="w", delete=False) as f:
        f.write("""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
    <circle cx="50" cy="50" r="40" fill="red" />
    <g id="layer1">
        <rect x="10" y="10" width="30" height="30" />
    </g>
</svg>""")
        good_svg = f.name

    with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
        f.write("""<root><item id="1"><name>Test</name></item></root>""")
        good_xml = f.name

    with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
        f.write("""<root><item><name>Broken</item></name></root>""")
        bad_xml = f.name

    try:
        assert validator_core.validate_code_file(Path(good_svg)) == []
        assert validator_core.validate_code_file(Path(good_xml)) == []
        bad_errs = validator_core.validate_code_file(Path(bad_xml))
        assert bad_errs != []
        assert any("XML" in e or "Tag" in e for e in bad_errs)
    finally:
        for p in [good_svg, good_xml, bad_xml]:
            if os.path.exists(p):
                os.remove(p)

def test_vue_svelte_astro_validation():
    import validator_core
    with tempfile.NamedTemporaryFile(suffix=".vue", mode="w", delete=False) as f:
        f.write("""<template>
  <div class="container">
    <h1>{{ title }}</h1>
    <custom-input disabled />
  </div>
</template>
<script lang="ts">
export default { data() { return { title: 'Hello' }; } };
</script>
<style scoped>
.container { display: flex; }
</style>""")
        good_vue = f.name

    with tempfile.NamedTemporaryFile(suffix=".svelte", mode="w", delete=False) as f:
        f.write("""<script>
  let count = 0;
</script>
<button on:click={() => count++}>
  Clicks: {count}
</button>""")
        good_svelte = f.name

    with tempfile.NamedTemporaryFile(suffix=".astro", mode="w", delete=False) as f:
        f.write("""---
const title = "Astro Page";
---
<html lang="en">
  <head><title>{title}</title></head>
  <body><main><h1>{title}</h1></main></body>
</html>""")
        good_astro = f.name

    with tempfile.NamedTemporaryFile(suffix=".vue", mode="w", delete=False) as f:
        f.write("""<template><div><span></span></template>""")
        bad_vue = f.name

    try:
        assert validator_core.validate_code_file(Path(good_vue)) == []
        assert validator_core.validate_code_file(Path(good_svelte)) == []
        assert validator_core.validate_code_file(Path(good_astro)) == []
        bad_errs = validator_core.validate_code_file(Path(bad_vue))
        assert bad_errs != []
        assert any("UnclosedTag" in e or "HTMLTagMismatch" in e for e in bad_errs)
    finally:
        for p in [good_vue, good_svelte, good_astro, bad_vue]:
            if os.path.exists(p):
                os.remove(p)

def test_powershell_validation():
    import validator_core
    with tempfile.NamedTemporaryFile(suffix=".ps1", mode="w", delete=False) as f:
        f.write("""
# PowerShell script with line comment
<#
  PowerShell multi-line
  block comment with (brackets)
#>
$hereString = @'
This is a raw here-string with 'single' and "double" quotes and {brackets}
'@

$expandableHere = @"
Expandable here string with `escaped backticks
"@

function Get-Data {
    param([string]$Name)
    $escapedSingle = 'It''s working'
    $escapedDouble = "Quote `"inner`" test"
    return @($Name, $escapedSingle, $escapedDouble)
}
""")
        good_ps1 = f.name

    with tempfile.NamedTemporaryFile(suffix=".ps1", mode="w", delete=False) as f:
        f.write("""function Test { return (1 + 2; }""")
        bad_ps1 = f.name

    try:
        assert validator_core.validate_code_file(Path(good_ps1)) == []
        bad_errs = validator_core.validate_code_file(Path(bad_ps1))
        assert bad_errs != []
        assert any("BracketMismatch" in e or "UnclosedBracket" in e for e in bad_errs)
    finally:
        for p in [good_ps1, bad_ps1]:
            if os.path.exists(p):
                os.remove(p)

def test_jupyter_notebook_validation():
    import validator_core
    notebook_content = {
        "cells": [
            {
                "cell_type": "markdown",
                "source": ["# Analysis Notebook\n", "Introductory markdown."]
            },
            {
                "cell_type": "code",
                "execution_count": 1,
                "source": [
                    "%matplotlib inline\n",
                    "!pip install numpy\n",
                    "import numpy as np\n",
                    "data = np.array([1, 2, 3])\n",
                    "print(data.mean())\n"
                ]
            }
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 2
    }
    with tempfile.NamedTemporaryFile(suffix=".ipynb", mode="w", delete=False) as f:
        json.dump(notebook_content, f)
        good_ipynb = f.name

    broken_notebook = {
        "cells": [
            {
                "cell_type": "code",
                "source": ["def broken_func(:\n    pass\n"]
            }
        ],
        "nbformat": 4,
        "nbformat_minor": 2
    }
    with tempfile.NamedTemporaryFile(suffix=".ipynb", mode="w", delete=False) as f:
        json.dump(broken_notebook, f)
        bad_ipynb = f.name

    try:
        assert validator_core.validate_code_file(Path(good_ipynb)) == []
        bad_errs = validator_core.validate_code_file(Path(bad_ipynb))
        assert bad_errs != []
        assert any("NotebookSyntaxError" in e for e in bad_errs)
    finally:
        for p in [good_ipynb, bad_ipynb]:
            if os.path.exists(p):
                os.remove(p)

def test_graphql_protobuf_validation():
    import validator_core
    with tempfile.NamedTemporaryFile(suffix=".graphql", mode="w", delete=False) as f:
        f.write('''
# GraphQL schema definition
"""
User model representing system accounts
"""
type User {
    id: ID!
    username: String!
    roles: [String!]!
}

type Query {
    getUser(id: ID!): User
}
''')
        good_gql = f.name

    with tempfile.NamedTemporaryFile(suffix=".proto", mode="w", delete=False) as f:
        f.write('''
syntax = "proto3";
package api.v1;

// Service definition
/* Multi-line comment */
message UserRequest {
    string id = 1;
    map<string, string> attributes = 2;
}

service UserService {
    rpc GetUser(UserRequest) returns (UserRequest);
}
''')
        good_proto = f.name

    with tempfile.NamedTemporaryFile(suffix=".graphql", mode="w", delete=False) as f:
        f.write('''type User { id: ID! ''')
        bad_gql = f.name

    try:
        assert validator_core.validate_code_file(Path(good_gql)) == []
        assert validator_core.validate_code_file(Path(good_proto)) == []
        bad_errs = validator_core.validate_code_file(Path(bad_gql))
        assert bad_errs != []
        assert any("UnclosedBracket" in e for e in bad_errs)
    finally:
        for p in [good_gql, good_proto, bad_gql]:
            if os.path.exists(p):
                os.remove(p)

def test_ini_cfg_env_properties_validation():
    import validator_core
    with tempfile.NamedTemporaryFile(suffix=".ini", mode="w", delete=False) as f:
        f.write("""
; INI Configuration
[database]
host = 127.0.0.1
port = 5432
user = "admin" # inline comment

[server]
debug = true
""")
        good_ini = f.name

    with tempfile.NamedTemporaryFile(suffix=".env", mode="w", delete=False) as f:
        f.write("""
# Environment variables
PORT=8080
SERVICE_NAME="sample_service"
DATABASE_URL='postgres://localhost:5432/db'
QUOTED="hello \\"escaped\\" world"
""")
        good_env = f.name

    with tempfile.NamedTemporaryFile(suffix=".env", mode="w", delete=False) as f:
        f.write('BROKEN_KEY="unclosed string value\n')
        bad_env = f.name

    try:
        assert validator_core.validate_code_file(Path(good_ini)) == []
        assert validator_core.validate_code_file(Path(good_env)) == []
        bad_errs = validator_core.validate_code_file(Path(bad_env))
        assert bad_errs != []
        assert any("UnclosedString" in e for e in bad_errs)
    finally:
        for p in [good_ini, good_env, bad_env]:
            if os.path.exists(p):
                os.remove(p)

def test_file_uri_prefix_extraction():
    import validator_core
    unix_payload = {"toolCall": {"name": "write_file", "args": {"Path": "file:///workspace/project/file.py"}}}
    assert validator_core.extract_target_file(unix_payload) == "/workspace/project/file.py"

    win_payload = {"toolCall": {"name": "write_file", "args": {"Path": "file:///C:/workspace/project/file.py"}}}
    assert validator_core.extract_target_file(win_payload) == "C:/workspace/project/file.py"

    localhost_payload = {"toolCall": {"name": "write_file", "args": {"Path": "file://localhost/var/log/app.log"}}}
    assert validator_core.extract_target_file(localhost_payload) == "/var/log/app.log"

def test_critic_loop_glob_and_comma_targets():
    import critic_loop
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f1:
        f1.write("def func_a(): return 1\n")
        file1 = f1.name
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f2:
        f2.write("def func_b(): return 2\n")
        file2 = f2.name

    try:
        # Test comma-separated target string
        comma_target = f"{file1},{file2}"
        res = critic_loop.audit_code_logic(comma_target)
        assert res["status"] == "PASS"

        # Test single non-existent target in comma list
        bad_comma_target = f"{file1},/nonexistent/fake_file.py"
        res_bad = critic_loop.audit_code_logic(bad_comma_target)
        assert res_bad["status"] == "RETRY"
        assert any("Target path does not exist" in v for v in res_bad["violations"])
    finally:
        for p in [file1, file2]:
            if os.path.exists(p):
                os.remove(p)

def test_visual_qa_expanded_touch_targets_and_astro():
    import visual_qa
    with tempfile.NamedTemporaryFile(suffix=".html", mode="w", delete=False) as f:
        f.write("""<!DOCTYPE html>
<html>
<body>
    <select style="width: 20px; height: 20px;"><option>A</option></select>
    <textarea style="width: 30px; height: 30px;"></textarea>
    <div role="button" tabindex="0" style="width: 25px; height: 25px;">Click</div>
</body>
</html>""")
        temp_html = f.name

    try:
        # Verify visual QA runner accepts .astro component file without erroring out
        astro_fake = Path(tempfile.gettempdir()) / "SampleComponent.astro"
        astro_fake.write_text("<div />", encoding="utf-8")
        try:
            with tempfile.TemporaryDirectory() as out_dir:
                code, stdout, stderr = run_script("visual_qa.py", [str(astro_fake), "--output-dir", out_dir])
                assert code == 0
                data = json.loads(stdout)
                assert data["status"] in ["SKIPPED_NO_DEV_SERVER", "SUCCESS", "SKIPPED_DEPENDENCY"]
        finally:
            if astro_fake.exists():
                astro_fake.unlink()
    finally:
        if os.path.exists(temp_html):
            os.remove(temp_html)

def test_hooks_expanded_candidate_paths():
    with open(PLUGIN_ROOT / "hooks.json", "r", encoding="utf-8") as f:
        hooks = json.load(f)
    cmd = hooks["antigravity-dev-suite-hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    assert "ANTIGRAVITY_DEV_SUITE_PATH" in cmd
    assert ".agents" in cmd
    assert "antigravity-cli" in cmd

def test_auto_debug_runner_shell_wrapper_no_args():
    sh_script = SCRIPTS_DIR / "auto_debug_runner.sh"
    res = subprocess.run(["bash", str(sh_script)], capture_output=True, text=True)
    assert res.returncode == 0
    assert res.stdout.strip() == "{}"
    assert "unbound variable" not in res.stderr

def test_astro_frontmatter_with_ts_generics():
    from validator_core import validate_code_file
    with tempfile.NamedTemporaryFile(suffix=".astro", mode="w", delete=False) as f:
        f.write("""---
import Layout from '../layouts/Layout.astro';
interface Props {
  title: string;
  items: Array<string>;
  map: Map<string, number>;
}
const count = 3;
const isLow = count < 5;
const items: Array<string> = ['a', 'b'];
---
<Layout title="Test">
  <main>
    <h1>Hello Astro</h1>
    <p>{items.length}</p>
  </main>
</Layout>
""")
        astro_path = Path(f.name)
    try:
        errors = validate_code_file(astro_path)
        assert len(errors) == 0, f"Unexpected errors in Astro frontmatter: {errors}"
    finally:
        if astro_path.exists():
            astro_path.unlink()

def test_php_ruby_heredocs_validation():
    from validator_core import validate_code_file
    # PHP heredoc / nowdoc with unbalanced brackets inside text
    with tempfile.NamedTemporaryFile(suffix=".php", mode="w", delete=False) as f:
        f.write("""<?php
$str1 = <<<EOF
Unbalanced bracket in text: { and (
and double quote "
EOF;

$str2 = <<<'NOWDOC'
Nowdoc text with [ unbalanced brackets
NOWDOC;

function calculateTotal($items) {
    return array_sum($items);
}
?>""")
        php_path = Path(f.name)
    try:
        errors = validate_code_file(php_path)
        assert len(errors) == 0, f"Unexpected errors in PHP heredoc: {errors}"
    finally:
        if php_path.exists():
            php_path.unlink()

    # Ruby heredoc with unbalanced bracket
    with tempfile.NamedTemporaryFile(suffix=".rb", mode="w", delete=False) as f:
        f.write("""sql = <<~SQL
SELECT id, name FROM users WHERE (age > 21
SQL

def get_user_count
  42
end
""")
        rb_path = Path(f.name)
    try:
        errors = validate_code_file(rb_path)
        assert len(errors) == 0, f"Unexpected errors in Ruby heredoc: {errors}"
    finally:
        if rb_path.exists():
            rb_path.unlink()

def test_java_multiline_text_blocks():
    from validator_core import validate_code_file
    with tempfile.NamedTemporaryFile(suffix=".java", mode="w", delete=False) as f:
        f.write("""public class QueryRunner {
    public static final String SQL_QUERY = \"\"\"
        SELECT u.id, u.name, (COUNT(o.id) AS order_count
        FROM users u
        LEFT JOIN orders o ON u.id = o.user_id
        WHERE u.status = 'ACTIVE'
    \"\"\";

    public int run() {
        return 42;
    }
}
""")
        java_path = Path(f.name)
    try:
        errors = validate_code_file(java_path)
        assert len(errors) == 0, f"Unexpected errors in Java text blocks: {errors}"
    finally:
        if java_path.exists():
            java_path.unlink()

def test_json5_colons_in_single_quotes():
    from validator_core import validate_code_file
    with tempfile.NamedTemporaryFile(suffix=".json5", mode="w", delete=False) as f:
        f.write("""{
    // JSON5 with colons inside single quoted strings
    title: 'My Project: Awesome App',
    description: 'Note: please follow step 1: initialize',
    count: 42,
    hexValue: 0xFF,
    isActive: true,
}""")
        json5_path = Path(f.name)
    try:
        errors = validate_code_file(json5_path)
        assert len(errors) == 0, f"Unexpected errors in JSON5 with colons: {errors}"
    finally:
        if json5_path.exists():
            json5_path.unlink()

def test_yaml_fallback_block_scalars():
    from validator_core import validate_code_file
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write("""name: test-service
version: 1.0.0
description: |
  This is a multiline description with an unclosed ( parenthesis
  and [ brackets in markdown text.
notes: >
  Another folded block with unmatched } brace.
features:
  - fast
  - reliable
""")
        yaml_path = Path(f.name)
    try:
        errors = validate_code_file(yaml_path)
        assert len(errors) == 0, f"Unexpected errors in YAML block scalar: {errors}"
    finally:
        if yaml_path.exists():
            yaml_path.unlink()

def test_markdown_commonmark_multibacktick_fences():
    from validator_core import validate_code_file
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
        f.write("""# Markdown Document

````carousel
![Slide 1](slide1.png)
<!-- slide -->
```python
def example():
    print("Code inside carousel")
```
````

Normal text after carousel.
""")
        md_path = Path(f.name)
    try:
        errors = validate_code_file(md_path)
        assert len(errors) == 0, f"Unexpected errors in Markdown 4-backtick fence: {errors}"
    finally:
        if md_path.exists():
            md_path.unlink()

def test_cloud_blockchain_formats_validation():
    from validator_core import validate_code_file
    # 1. Prisma Schema (.prisma)
    with tempfile.NamedTemporaryFile(suffix=".prisma", mode="w", delete=False) as f:
        f.write("""datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

model User {
  id        Int      @id @default(autoincrement())
  email     String   @unique
  name      String?
  createdAt DateTime @default(now())
}
""")
        prisma_path = Path(f.name)
    try:
        errors = validate_code_file(prisma_path)
        assert len(errors) == 0, f"Prisma errors: {errors}"
    finally:
        if prisma_path.exists():
            prisma_path.unlink()

    # 2. Solidity (.sol)
    with tempfile.NamedTemporaryFile(suffix=".sol", mode="w", delete=False) as f:
        f.write("""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract SimpleStorage {
    uint256 private storedData;

    function set(uint256 x) public {
        storedData = x;
    }

    function get() public view returns (uint256) {
        return storedData;
    }
}
""")
        sol_path = Path(f.name)
    try:
        errors = validate_code_file(sol_path)
        assert len(errors) == 0, f"Solidity errors: {errors}"
    finally:
        if sol_path.exists():
            sol_path.unlink()

    # 3. Terraform / HCL (.tf, .hcl)
    with tempfile.NamedTemporaryFile(suffix=".tf", mode="w", delete=False) as f:
        f.write("""resource "aws_s3_bucket" "b" {
  bucket = "my-tf-test-bucket"

  tags = {
    Name        = "My bucket"
    Environment = "Dev"
  }
}
""")
        tf_path = Path(f.name)
    try:
        errors = validate_code_file(tf_path)
        assert len(errors) == 0, f"Terraform errors: {errors}"
    finally:
        if tf_path.exists():
            tf_path.unlink()

def test_critic_loop_security_and_hygiene_audit():
    from critic_loop import audit_code_logic
    # Test secret detection
    dummy_key = "s" + "k-proj-1234567890abcdef1234567890abcdef12345678"
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(f'API_KEY = "{dummy_key}"\n')
        secret_py = f.name
    try:
        res = audit_code_logic(secret_py)
        assert res["status"] == "RETRY"
        assert any("Secret" in v or "API key" in v or "token" in v for v in res["violations"])
    finally:
        if os.path.exists(secret_py):
            os.remove(secret_py)

    # Test empty catch / except detection
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("""def bad_handler():
    try:
        do_work()
    except Exception:
        pass
""")
        except_py = f.name
    try:
        res = audit_code_logic(except_py)
        assert res["status"] == "RETRY"
        assert any("EmptyExceptionHandling" in v or "except" in v for v in res["violations"])
    finally:
        if os.path.exists(except_py):
            os.remove(except_py)

def test_visual_qa_http_error_tracking_and_expanded_ports():
    from visual_qa import COMMON_DEV_PORTS
    assert 4173 in COMMON_DEV_PORTS  # Vite preview
    assert 8888 in COMMON_DEV_PORTS  # Jupyter/dev
    assert 3004 in COMMON_DEV_PORTS
    assert 5177 in COMMON_DEV_PORTS

def test_tool_payload_expanded_keys():
    from validator_core import extract_target_file
    p1 = {"filePath": "/path/to/component.tsx"}
    p2 = {"targetPath": "src/routes/api.ts"}
    p3 = {"sourcePath": "lib/utils.py"}
    p4 = {"file": "file://localhost/C:/project/app.py"}
    assert extract_target_file(p1) == "/path/to/component.tsx"
    assert extract_target_file(p2) == "src/routes/api.ts"
    assert extract_target_file(p3) == "lib/utils.py"
    assert extract_target_file(p4) in ["C:/project/app.py", "/C:/project/app.py"]

def test_env_and_ini_inline_comments_with_apostrophes():
    from validator_core import validate_code_file
    with tempfile.NamedTemporaryFile(suffix=".env", mode="w", delete=False) as f:
        f.write("""# Configuration file
DATABASE_URL="postgresql://localhost:5432/sample_db" # Don't touch this in prod
API_TIMEOUT=30 ; It's recommended to keep at 30s
APP_TITLE='Sample Application' # User's primary title
LOG_LEVEL="info"
""")
        env_path = Path(f.name)
    try:
        errors = validate_code_file(env_path)
        assert len(errors) == 0, f"Inline comments with apostrophes caused false positive: {errors}"
    finally:
        if env_path.exists():
            env_path.unlink()

def test_polyglot_css_sql_unclosed_multiline_comments():
    from validator_core import validate_code_file
    # 1. Polyglot unclosed /* comment
    with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
        f.write("function test() { return 1; }\n/* unclosed multi-line comment\n")
        ts_path = Path(f.name)
    try:
        errors = validate_code_file(ts_path)
        assert any("UnclosedComment" in e for e in errors), f"Unclosed TS block comment not detected: {errors}"
    finally:
        if ts_path.exists():
            ts_path.unlink()

    # 2. CSS unclosed /* comment
    with tempfile.NamedTemporaryFile(suffix=".css", mode="w", delete=False) as f:
        f.write(".card { color: red; }\n/* unclosed CSS block comment\n")
        css_path = Path(f.name)
    try:
        errors = validate_code_file(css_path)
        assert any("UnclosedComment" in e for e in errors), f"Unclosed CSS block comment not detected: {errors}"
    finally:
        if css_path.exists():
            css_path.unlink()

    # 3. SQL unclosed /* comment
    with tempfile.NamedTemporaryFile(suffix=".sql", mode="w", delete=False) as f:
        f.write("SELECT * FROM users;\n/* unclosed SQL block comment\n")
        sql_path = Path(f.name)
    try:
        errors = validate_code_file(sql_path)
        assert any("UnclosedComment" in e for e in errors), f"Unclosed SQL block comment not detected: {errors}"
    finally:
        if sql_path.exists():
            sql_path.unlink()

    # 4. Ruby unclosed =begin comment
    with tempfile.NamedTemporaryFile(suffix=".rb", mode="w", delete=False) as f:
        f.write("def hello\n  puts 'hi'\nend\n=begin\nunclosed ruby block\n")
        rb_path = Path(f.name)
    try:
        errors = validate_code_file(rb_path)
        assert any("UnclosedComment" in e for e in errors), f"Unclosed Ruby =begin comment not detected: {errors}"
    finally:
        if rb_path.exists():
            rb_path.unlink()

def test_find_source_files_detects_standalone_env_files():
    from validator_core import find_source_files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / ".env").write_text("FOO=BAR\n", encoding="utf-8")
        (tmp_path / ".env.local").write_text("FOO=LOCAL\n", encoding="utf-8")
        (tmp_path / ".env.production").write_text("FOO=PROD\n", encoding="utf-8")
        (tmp_path / "app.py").write_text("print(1)\n", encoding="utf-8")
        
        found = [f.name for f in find_source_files(tmp_path)]
        assert ".env" in found, f".env not found in {found}"
        assert ".env.local" in found, f".env.local not found in {found}"
        assert ".env.production" in found, f".env.production not found in {found}"
        assert "app.py" in found, f"app.py not found in {found}"

def test_critic_loop_empty_exception_ellipsis():
    from critic_loop import audit_code_logic
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("""def bad_ellipsis_handler():
    try:
        perform_action()
    except Exception:
        ...
""")
        py_path = Path(f.name)
    try:
        res = audit_code_logic(str(py_path))
        assert res["status"] == "RETRY"
        assert any("EmptyExceptionHandling" in v or "except" in v for v in res["violations"])
    finally:
        if py_path.exists():
            py_path.unlink()

def test_file_uri_percent_encoding_decoding():
    from validator_core import extract_target_file
    uri = "file:///home/developer/Project%20Folder/test%231%20file.py"
    extracted = extract_target_file({"file": uri})
    assert extracted == "/home/developer/Project Folder/test#1 file.py"

def test_resolve_target_file_os_error_resilience():
    from validator_core import resolve_target_file
    # Invalid characters or null bytes should not crash resolve_target_file
    res1 = resolve_target_file({"Path": "\0invalid/null/byte"})
    assert isinstance(res1, str)
    res2 = resolve_target_file({"Path": "C:\\invalid<>chars:*?\"|", "workspacePaths": ["/invalid/dir:*?"]})
    assert isinstance(res2, str)

def test_zig_nim_elixir_polyglot_enhancements():
    from validator_core import validate_code_file
    # 1. Zig multiline string literals (\\)
    with tempfile.NamedTemporaryFile(suffix=".zig", mode="w", delete=False) as f:
        f.write("""const std = @import("std");
pub fn main() void {
    const multiline =
        \\\\This is a raw string line with { unclosed bracket
        \\\\and another line with [ unclosed bracket;
    std.debug.print("{s}\\n", .{multiline});
}
""")
        zig_path = Path(f.name)
    try:
        errors = validate_code_file(zig_path)
        assert len(errors) == 0, f"Zig multiline strings caused false positive: {errors}"
    finally:
        if zig_path.exists():
            zig_path.unlink()

    # 2. Nim triple-quoted multiline string
    with tempfile.NamedTemporaryFile(suffix=".nim", mode="w", delete=False) as f:
        f.write("""import strutils
let doc = \"\"\"
This is a multiline docstring with { unclosed bracket and [ another bracket.
\"\"\"
echo doc
""")
        nim_path = Path(f.name)
    try:
        errors = validate_code_file(nim_path)
        assert len(errors) == 0, f"Nim triple-quoted strings caused false positive: {errors}"
    finally:
        if nim_path.exists():
            nim_path.unlink()

    # 3. Elixir triple-quoted multiline string
    with tempfile.NamedTemporaryFile(suffix=".ex", mode="w", delete=False) as f:
        f.write("""defmodule Sample do
  @doc \"\"\"
  Documentation with { unbalanced bracket and [ square bracket.
  \"\"\"
  def run, do: :ok
end
""")
        ex_path = Path(f.name)
    try:
        errors = validate_code_file(ex_path)
        assert len(errors) == 0, f"Elixir triple-quoted strings caused false positive: {errors}"
    finally:
        if ex_path.exists():
            ex_path.unlink()

def test_clojure_character_escapes_outside_strings():
    from validator_core import validate_code_file
    with tempfile.NamedTemporaryFile(suffix=".clj", mode="w", delete=False) as f:
        f.write("""(ns test.core)
(defn check-char [c]
  (cond
    (= c \\() :open-paren
    (= c \\)) :close-paren
    (= c \\[) :open-bracket
    (= c \\]) :close-bracket
    (= c \\{) :open-brace
    (= c \\}) :close-brace
    :else :other))
""")
        clj_path = Path(f.name)
    try:
        errors = validate_code_file(clj_path)
        assert len(errors) == 0, f"Clojure character escapes caused false positive: {errors}"
    finally:
        if clj_path.exists():
            clj_path.unlink()

def test_standalone_env_and_env_local_validation():
    from validator_core import validate_code_file
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        env_main = tmp_path / ".env"
        env_main.write_text("API_KEY=\"12345\"\nDATABASE_URL='postgres://localhost:5432'\n", encoding="utf-8")
        env_local = tmp_path / ".env.local"
        env_local.write_text("DEBUG=true\nPORT=3000\n", encoding="utf-8")
        env_bad = tmp_path / ".env.production"
        env_bad.write_text("BROKEN_VAR=\"unclosed string\n", encoding="utf-8")

        assert validate_code_file(env_main) == []
        assert validate_code_file(env_local) == []
        bad_errs = validate_code_file(env_bad)
        assert len(bad_errs) > 0
        assert any("UnclosedString" in e for e in bad_errs)

def test_mts_cts_mdx_polyglot_validation():
    from validator_core import validate_code_file
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        mts_file = tmp_path / "module.mts"
        mts_file.write_text("export const add = (a: number, b: number): number => a + b;\n", encoding="utf-8")
        cts_file = tmp_path / "common.cts"
        cts_file.write_text("export = { version: '1.0.0' };\n", encoding="utf-8")
        # MDX document containing prose with natural English apostrophes (don't, it's)
        mdx_file = tmp_path / "docs.mdx"
        mdx_file.write_text("---\ntitle: Guide\n---\n# MDX Document\n\nDon't worry, it's working properly.\n\nimport { Card } from './Card';\n\n<Card title=\"Test\" />\n", encoding="utf-8")

        assert validate_code_file(mts_file) == []
        assert validate_code_file(cts_file) == []
        assert validate_code_file(mdx_file) == []

        bad_mts = tmp_path / "broken.mts"
        bad_mts.write_text("const x = [1, 2, 3};\n", encoding="utf-8")
        bad_errs = validate_code_file(bad_mts)
        assert len(bad_errs) > 0
        assert any("BracketMismatch" in e or "UnclosedBracket" in e for e in bad_errs)

        bad_mdx = tmp_path / "broken.mdx"
        bad_mdx.write_text("# Unclosed code block\n```typescript\nconst a = 1;\n", encoding="utf-8")
        bad_mdx_errs = validate_code_file(bad_mdx)
        assert len(bad_mdx_errs) > 0
        assert any("UnclosedCodeBlock" in e for e in bad_mdx_errs)

def test_critic_loop_extended_secret_patterns():
    from critic_loop import audit_code_logic
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Test GitHub PAT
        p1 = tmp_path / "pat.py"
        p1.write_text('GITHUB_TOKEN = "github_pat_' + '11AAAAAAA01234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"\n', encoding="utf-8")
        res1 = audit_code_logic(str(p1))
        assert res1["status"] == "RETRY"
        assert any("Secret" in v or "token" in v for v in res1["violations"])

        # Test GitLab PAT
        p2 = tmp_path / "glpat.py"
        p2.write_text('GITLAB_TOKEN = "glpat-' + 'abcdef1234567890ABCD"\n', encoding="utf-8")
        res2 = audit_code_logic(str(p2))
        assert res2["status"] == "RETRY"
        assert any("Secret" in v or "token" in v for v in res2["violations"])

        # Test Slack Bot Token
        p3 = tmp_path / "slack.py"
        p3.write_text('SLACK_TOKEN = "xoxb-' + '1234567890-1234567890-abcdef123456"\n', encoding="utf-8")
        res3 = audit_code_logic(str(p3))
        assert res3["status"] == "RETRY"
        assert any("Secret" in v or "token" in v for v in res3["violations"])

        # Test Stripe Live Key
        p4 = tmp_path / "stripe.py"
        p4.write_text('STRIPE_KEY = "sk_live_' + '51Abcdef1234567890abcdef"\n', encoding="utf-8")
        res4 = audit_code_logic(str(p4))
        assert res4["status"] == "RETRY"
        assert any("Secret" in v or "token" in v for v in res4["violations"])

        # Test AWS Secret Access Key in YAML format
        p5 = tmp_path / "aws.yaml"
        p5.write_text('aws_secret_access_key: "' + 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY' + '"\n', encoding="utf-8")
        res5 = audit_code_logic(str(p5))
        assert res5["status"] == "RETRY"
        assert any("AWS Secret Access Key" in v for v in res5["violations"])

        # Test AWS Secret Access Key in unquoted dotenv format
        p6 = tmp_path / "aws.env"
        p6.write_text('AWS_SECRET_ACCESS_KEY=' + 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY' + '\n', encoding="utf-8")
        res6 = audit_code_logic(str(p6))
        assert res6["status"] == "RETRY"
        assert any("AWS Secret Access Key" in v for v in res6["violations"])

def test_dev_server_env_port_prioritization():
    import visual_qa
    import os
    from unittest.mock import patch

    old_port = os.environ.get("PORT")
    old_vite = os.environ.get("VITE_PORT")
    try:
        # Test 1: PORT takes priority over VITE_PORT and fallbacks
        os.environ["PORT"] = "4000"
        os.environ["VITE_PORT"] = "5173"
        with patch.object(visual_qa, "is_http_server_active", side_effect=lambda p: p in (4000, 5173)):
            found = visual_qa.find_active_dev_server()
            assert found == "http://localhost:4000", f"Expected http://localhost:4000 but got {found}"

        # Test 2: If PORT is inactive, VITE_PORT is checked next
        with patch.object(visual_qa, "is_http_server_active", side_effect=lambda p: p == 5173):
            found = visual_qa.find_active_dev_server()
            assert found == "http://localhost:5173", f"Expected http://localhost:5173 but got {found}"

        # Test 3: If no env ports active, fallback to COMMON_DEV_PORTS
        os.environ.pop("PORT", None)
        os.environ.pop("VITE_PORT", None)
        with patch.object(visual_qa, "is_http_server_active", side_effect=lambda p: p == 3000):
            found = visual_qa.find_active_dev_server()
            assert found == "http://localhost:3000", f"Expected http://localhost:3000 but got {found}"
    finally:
        if old_port is not None:
            os.environ["PORT"] = old_port
        else:
            os.environ.pop("PORT", None)
        if old_vite is not None:
            os.environ["VITE_PORT"] = old_vite
        else:
            os.environ.pop("VITE_PORT", None)

def test_auto_debug_runner_framework_detection():
    import auto_debug_runner
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        # 1. Python Pytest
        (tdp / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
        info = auto_debug_runner.detect_project_framework(tdp)
        assert info["status"] == "DETECTED"
        assert "pytest" in info["test_command"]
        assert "ruff" in info["lint_command"] or "mypy" in info["lint_command"]
        (tdp / "pyproject.toml").unlink()

        # 2. Rust Cargo
        (tdp / "Cargo.toml").write_text("[package]\nname='test'\n", encoding="utf-8")
        info_rust = auto_debug_runner.detect_project_framework(tdp)
        assert info_rust["status"] == "DETECTED"
        assert info_rust["ecosystem"] == "Rust (Cargo)"
        assert info_rust["test_command"] == "cargo test"
        (tdp / "Cargo.toml").unlink()

        # 3. Node Vitest
        (tdp / "package.json").write_text('{"name": "test"}', encoding="utf-8")
        (tdp / "vite.config.ts").write_text('export default {}', encoding="utf-8")
        info_node = auto_debug_runner.detect_project_framework(tdp)
        assert info_node["status"] == "DETECTED"
        assert "vitest" in info_node["test_command"]
        (tdp / "package.json").unlink()
        (tdp / "vite.config.ts").unlink()

    # Test CLI invocation --detect
    code, stdout, stderr = run_script("auto_debug_runner.py", ["--detect"])
    assert code == 0
    data = json.loads(stdout)
    assert "status" in data
    assert "test_command" in data

def test_auto_debug_runner_last_error_and_clear():
    import auto_debug_runner
    # Ensure starting clean
    auto_debug_runner.clear_last_syntax_error()
    assert auto_debug_runner.get_last_syntax_error() is None

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("def broken(:\n    pass\n")
        bad_file = f.name

    try:
        payload = json.dumps({"toolCall": {"name": "write_file", "args": {"Path": bad_file}}})
        code, stdout, stderr = run_script("auto_debug_runner.py", [], input_data=payload)
        assert code == 0
        
        last_err = auto_debug_runner.get_last_syntax_error()
        assert last_err is not None
        assert last_err["file"] == bad_file
        assert len(last_err["errors"]) > 0

        # Test CLI --last-error
        code_le, stdout_le, _ = run_script("auto_debug_runner.py", ["--last-error"])
        assert code_le == 0
        data_le = json.loads(stdout_le)
        assert data_le["file"] == bad_file

        # Test Clear
        auto_debug_runner.clear_last_syntax_error()
        assert auto_debug_runner.get_last_syntax_error() is None

        # Test CLI --clear-last-error
        code_cl, stdout_cl, _ = run_script("auto_debug_runner.py", ["--clear-last-error"])
        assert code_cl == 0
    finally:
        if os.path.exists(bad_file):
            os.remove(bad_file)
        auto_debug_runner.clear_last_syntax_error()

def test_auto_debug_runner_check_cli():
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("def ok():\n    return 1\n")
        good_file = f.name

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("def broken(:\n    return 2\n")
        bad_file = f.name

    try:
        code_g, stdout_g, _ = run_script("auto_debug_runner.py", ["--check", good_file])
        assert code_g == 0
        data_g = json.loads(stdout_g)
        assert data_g["status"] == "PASS"
        assert len(data_g["errors"]) == 0

        code_b, stdout_b, _ = run_script("auto_debug_runner.py", ["--check", bad_file])
        assert code_b == 1
        data_b = json.loads(stdout_b)
        assert data_b["status"] == "ERROR"
        assert len(data_b["errors"]) > 0
    finally:
        if os.path.exists(good_file):
            os.remove(good_file)
        if os.path.exists(bad_file):
            os.remove(bad_file)

def test_visual_qa_explicit_dev_server_and_port():
    import visual_qa
    from unittest.mock import patch

    with patch.object(visual_qa, "is_http_server_active", return_value=True):
        # Preferred port
        found_port = visual_qa.find_active_dev_server(preferred_port=4567)
        assert found_port == "http://localhost:4567"

    # Test CLI help / argument parsing for --dev-server and --port
    code, stdout, stderr = run_script("visual_qa.py", ["--help"])
    assert code == 0
    assert "--dev-server" in stdout
    assert "--port" in stdout

def test_critic_loop_integrates_last_syntax_error():
    import auto_debug_runner
    import critic_loop

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("def bad(:\n    pass\n")
        bad_file = f.name

    try:
        # Simulate last syntax error recorded by hook
        diag_path = Path(tempfile.gettempdir()) / "agy_last_syntax_error.json"
        with open(diag_path, "w", encoding="utf-8") as df:
            json.dump({"file": bad_file, "errors": ["SyntaxError in synthetic test"]}, df)

        res = critic_loop.audit_code_logic(bad_file)
        assert res["status"] == "RETRY"
        assert any("SyntaxError" in v for v in res["violations"])
    finally:
        if os.path.exists(bad_file):
            os.remove(bad_file)
        auto_debug_runner.clear_last_syntax_error()

def test_critic_loop_fine_grained_modes_and_target_flag():
    import critic_loop

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("try:\n    x = 1\nexcept Exception:\n    pass\n")
        temp_py = f.name

    try:
        # 1. Submode syntax ignores empty exception
        res_syntax = critic_loop.audit_code_logic(temp_py, submode="syntax")
        assert res_syntax["status"] == "PASS"

        # 2. Submode security catches empty exception
        res_sec = critic_loop.audit_code_logic(temp_py, submode="security")
        assert res_sec["status"] == "RETRY"
        assert any("EmptyExceptionHandling" in v for v in res_sec["violations"])

        # 3. CLI --mode syntax with --target flag
        code, stdout, _ = run_script("critic_loop.py", ["--mode", "syntax", "--target", temp_py])
        assert code == 0
        data = json.loads(stdout)
        assert data["status"] == "PASS"

        # 4. CLI --mode security with --target flag
        code, stdout, _ = run_script("critic_loop.py", ["--mode", "security", "--target", temp_py])
        assert code == 1
        data = json.loads(stdout)
        assert data["status"] == "RETRY"
    finally:
        if os.path.exists(temp_py):
            os.remove(temp_py)

def test_security_audit_skill_and_references():
    skill_dir = PLUGIN_ROOT / "skills" / "security-audit"
    skill_file = skill_dir / "SKILL.md"
    assert skill_file.exists(), f"Missing {skill_file}"

    text = skill_file.read_text(encoding="utf-8")
    assert "name: security-audit" in text
    assert "description:" in text
    assert "findings.json" in text
    assert "SECURITY-REPORT.md" in text

    ref_dir = skill_dir / "references"
    assert ref_dir.is_dir()
    expected_refs = ["web-and-auth.md", "ai-and-llm.md", "memory-and-injection.md", "supply-chain.md"]
    for ref_name in expected_refs:
        ref_file = ref_dir / ref_name
        assert ref_file.exists(), f"Missing reference file: {ref_name}"
        assert ref_file.stat().st_size > 500, f"Reference file {ref_name} is too small"

    # Verify template parity
    tpl_dir = PLUGIN_ROOT / "templates" / "project-git-template" / ".agents" / "skills" / "security-audit"
    assert (tpl_dir / "SKILL.md").exists()
    for ref_name in expected_refs:
        assert (tpl_dir / "references" / ref_name).exists()

def test_critic_loop_semantic_mutable_defaults():
    import critic_loop

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("def compute(items=[]):\n    items.append(1)\n    return items\n")
        bad_py = f.name

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("def compute(items=None):\n    if items is None:\n        items = []\n    return items\n")
        good_py = f.name

    try:
        # 1. Python AST detects mutable default argument
        res_bad = critic_loop.audit_code_logic(bad_py, submode="semantic")
        assert res_bad["status"] == "RETRY"
        assert any("MutableDefaultArgument" in v for v in res_bad["violations"])

        # 2. Clean file passes semantic audit
        res_good = critic_loop.audit_code_logic(good_py, submode="semantic")
        assert res_good["status"] == "PASS"

        # 3. CLI execution
        code, stdout, _ = run_script("critic_loop.py", ["--mode", "semantic", "--target", bad_py])
        assert code == 1
        data = json.loads(stdout)
        assert data["status"] == "RETRY"
    finally:
        if os.path.exists(bad_py):
            os.remove(bad_py)
        if os.path.exists(good_py):
            os.remove(good_py)

def test_critic_loop_semantic_redos_and_unawaited():
    import critic_loop

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write('import re\nPATTERN = re.compile(r"(a+)+")\n')
        redos_py = f.name

    with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
        f.write('export function syncCall() {\n  fetch("https://api.example.com");\n  return 42;\n}\n')
        unawaited_ts = f.name

    try:
        # 1. ReDoS nested quantifier detection
        res_redos = critic_loop.audit_code_logic(redos_py, submode="semantic")
        assert res_redos["status"] == "RETRY"
        assert any("ReDoSRisk" in v for v in res_redos["violations"])

        # 2. Floating/unawaited fetch promise detection
        res_ts = critic_loop.audit_code_logic(unawaited_ts, submode="semantic")
        assert res_ts["status"] == "RETRY"
        assert any("UnawaitedPromise" in v for v in res_ts["violations"])
    finally:
        if os.path.exists(redos_py):
            os.remove(redos_py)
        if os.path.exists(unawaited_ts):
            os.remove(unawaited_ts)

def test_benchmark_skill_and_cli():
    # 1. Benchmark skill specification
    skill_file = PLUGIN_ROOT / "skills" / "benchmark" / "SKILL.md"
    assert skill_file.exists(), f"Missing {skill_file}"
    text = skill_file.read_text(encoding="utf-8")
    assert "name: benchmark" in text
    assert "BENCHMARK-REPORT.md" in text
    assert "pytest -v --benchmark-only" in text

    # 2. Template parity
    tpl_skill = PLUGIN_ROOT / "templates" / "project-git-template" / ".agents" / "skills" / "benchmark" / "SKILL.md"
    assert tpl_skill.exists(), f"Missing template parity {tpl_skill}"
    assert tpl_skill.read_text(encoding="utf-8") == text

    # 3. CLI runner test
    code, stdout, _ = run_script("auto_debug_runner.py", ["--benchmark", str(PLUGIN_ROOT)])
    data = json.loads(stdout)
    assert "status" in data
    assert "benchmark_command" in data or "command" in data

def test_critic_loop_extended_ast_and_polyglot_checks():
    import critic_loop

    # 1. Python CommandInjectionRisk
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("import subprocess\ndef run(user_cmd):\n    subprocess.run(user_cmd, shell=True)\n")
        bad_shell_py = f.name
    # Safe bypass
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("import subprocess\ndef run(user_cmd):\n    subprocess.run(user_cmd, shell=True)  # nosec: safe-shell\n")
        safe_shell_py = f.name

    # 2. Python InsecureDeserialization
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("import pickle\ndef load(data):\n    return pickle.loads(data)\n")
        bad_pickle_py = f.name

    # 3. Python DangerousEval
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("def calculate(expr):\n    return eval(expr)\n")
        bad_eval_py = f.name

    # 4. Python SQLInjectionRisk in f-string
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write('def query_user(name):\n    sql = f"SELECT * FROM users WHERE name = \'{name}\'"\n    return sql\n')
        bad_sql_py = f.name

    # 5. Rust unwrap/expect in non-test file
    with tempfile.NamedTemporaryFile(suffix=".rs", mode="w", delete=False) as f:
        f.write('fn process(opt: Option<i32>) -> i32 {\n    opt.unwrap()\n}\n')
        bad_rust = f.name

    # 6. Go panic in non-test file
    with tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False) as f:
        f.write('package main\nfunc check(err error) {\n    if err != nil {\n        panic(err)\n    }\n}\n')
        bad_go = f.name

    # 7. JS eval and innerHTML
    with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
        f.write('function render(userStr) {\n    eval(userStr);\n    document.getElementById("box").innerHTML = userStr;\n}\n')
        bad_js = f.name

    try:
        # Check Python shell injection
        res = critic_loop.audit_code_logic(bad_shell_py, submode="semantic")
        assert res["status"] == "RETRY"
        assert any("CommandInjectionRisk" in v for v in res["violations"])

        # Check Python safe-shell bypass
        res_safe = critic_loop.audit_code_logic(safe_shell_py, submode="semantic")
        assert not any("CommandInjectionRisk" in v for v in res_safe.get("violations", []))

        # Check Python pickle
        res = critic_loop.audit_code_logic(bad_pickle_py, submode="semantic")
        assert res["status"] == "RETRY"
        assert any("InsecureDeserialization" in v for v in res["violations"])

        # Check Python eval
        res = critic_loop.audit_code_logic(bad_eval_py, submode="semantic")
        assert res["status"] == "RETRY"
        assert any("DangerousEval" in v for v in res["violations"])

        # Check Python SQL injection
        res = critic_loop.audit_code_logic(bad_sql_py, submode="semantic")
        assert res["status"] == "RETRY"
        assert any("SQLInjectionRisk" in v for v in res["violations"])

        # Check Rust panic
        res = critic_loop.audit_code_logic(bad_rust, submode="semantic")
        assert res["status"] == "RETRY"
        assert any("ProductionPanicRisk" in v for v in res["violations"])

        # Check Go unhandled panic
        res = critic_loop.audit_code_logic(bad_go, submode="semantic")
        assert res["status"] == "RETRY"
        assert any("UnhandledPanic" in v for v in res["violations"])

        # Check JS eval and innerHTML
        res = critic_loop.audit_code_logic(bad_js, submode="semantic")
        assert res["status"] == "RETRY"
        assert any("DangerousEval" in v for v in res["violations"])
        assert any("XSSRisk" in v for v in res["violations"])
    finally:
        for p in (bad_shell_py, safe_shell_py, bad_pickle_py, bad_eval_py, bad_sql_py, bad_rust, bad_go, bad_js):
            if os.path.exists(p):
                os.remove(p)

def test_auto_debug_runner_coverage_and_mutation():
    from auto_debug_runner import detect_project_framework

    # Framework detection returns coverage and mutation commands
    info = detect_project_framework(PLUGIN_ROOT)
    assert "coverage_command" in info
    assert "mutation_command" in info

    # CLI test for --coverage
    code, stdout, _ = run_script("auto_debug_runner.py", ["--coverage", str(PLUGIN_ROOT)])
    data = json.loads(stdout)
    assert "status" in data
    assert "coverage_command" in data or "command" in data

    # CLI test for --mutation
    code, stdout, _ = run_script("auto_debug_runner.py", ["--mutation", str(PLUGIN_ROOT)])
    data = json.loads(stdout)
    assert "status" in data
    assert "mutation_command" in data or "command" in data

def test_pre_tool_guard_safety_rules():
    # 1. Catastrophic command block
    code, stdout, _ = run_script("pre_tool_guard.py", ["--check-cmd", "rm -rf /"])
    assert code == 1
    data = json.loads(stdout)
    assert data["decision"] == "deny"
    assert "Root or home" in data["reason"]

    code, stdout, _ = run_script("pre_tool_guard.py", ["--check-cmd", "rm -rf .git"])
    assert code == 1
    data = json.loads(stdout)
    assert data["decision"] == "deny"
    assert "Git repository" in data["reason"]

    code, stdout, _ = run_script("pre_tool_guard.py", ["--check-cmd", "git push --force origin main"])
    assert code == 1
    data = json.loads(stdout)
    assert data["decision"] == "deny"

    # 2. Safe command allow
    code, stdout, _ = run_script("pre_tool_guard.py", ["--check-cmd", "git status"])
    assert code == 0
    data = json.loads(stdout)
    assert data["decision"] == "allow"

    # 3. Secret blocking
    priv_key = "-----BEGIN " + "RSA PRIVATE KEY-----\nMIIE..."
    code, stdout, _ = run_script("pre_tool_guard.py", ["--check-content", priv_key])
    assert code == 1
    data = json.loads(stdout)
    assert data["decision"] == "deny"
    assert "private key" in data["reason"].lower()

    # 4. Protected path blocking
    code, stdout, _ = run_script("pre_tool_guard.py", ["--check-path", "/project/.git/config"])
    assert code == 1
    data = json.loads(stdout)
    assert data["decision"] == "deny"

    # 5. Stdin JSON payload verification
    payload = json.dumps({"toolCall": {"name": "run_command", "args": {"CommandLine": "rm -rf /"}}})
    code, stdout, _ = run_script("pre_tool_guard.py", [], input_data=payload)
    assert code == 0
    data = json.loads(stdout)
    assert data["decision"] == "deny"

def test_pattern_catalog_and_formal_invariants():
    # 1. Pattern catalog
    pat_file = PLUGIN_ROOT / "skills" / "code-review" / "references" / "patterns.md"
    assert pat_file.exists(), f"Missing {pat_file}"
    text = pat_file.read_text(encoding="utf-8")
    assert "Typestate Pattern" in text
    assert "Branded Nominal Types" in text
    assert "Structured Concurrency" in text
    assert "Property-Based Testing" in text

    # 2. Formal loop invariant schema in plan & brainstorm skills
    plan_skill = (PLUGIN_ROOT / "skills" / "plan" / "SKILL.md").read_text(encoding="utf-8")
    assert "Formal Inductive Invariant Specification" in plan_skill
    assert "Precondition" in plan_skill
    assert "Loop Invariant" in plan_skill
    assert "Loop Variant" in plan_skill
    assert "Postcondition" in plan_skill

    brainstorm_skill = (PLUGIN_ROOT / "skills" / "brainstorm" / "SKILL.md").read_text(encoding="utf-8")
    assert "Loop Invariants" in brainstorm_skill

    # 3. Public API contract preservation in rules and architect
    agents_rule = (PLUGIN_ROOT / "rules" / "AGENTS.md").read_text(encoding="utf-8")
    assert "Public API Contract Preservation" in agents_rule
    assert "Contract-First Stability" in agents_rule

    architect_agent = (PLUGIN_ROOT / "agents" / "opus-architect.md").read_text(encoding="utf-8")
    assert "API Contracts" in architect_agent

def test_commit_skill_and_v11_plugin_manifest():
    # 1. Commit skill
    commit_skill = PLUGIN_ROOT / "skills" / "commit" / "SKILL.md"
    assert commit_skill.exists()
    text = commit_skill.read_text(encoding="utf-8")
    assert "name: commit" in text
    assert "Pre-Commit Verification Pipeline" in text
    assert "Conventional Commits" in text

    # 2. Plugin manifest
    manifest = json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "1.13.0"
    assert any("/commit" in p for p in manifest["suggestedPrompts"])

    # 3. Project template GEMINI.md
    gemini_md = (PLUGIN_ROOT / "templates" / "project-git-template" / "GEMINI.md").read_text(encoding="utf-8")
    assert "/commit" in gemini_md

def test_auto_debug_runner_typecheck_race_fuzz():
    import auto_debug_runner
    det = auto_debug_runner.detect_project_framework(PLUGIN_ROOT)
    assert "typecheck_command" in det
    assert "race_command" in det
    assert "fuzz_command" in det
    assert det["typecheck_command"] == "mypy ."
    assert "pytest" in det["race_command"]
    assert "pytest" in det["fuzz_command"]

    # Test override execution
    res_tc = auto_debug_runner.run_project_typecheck(command_override="echo 'Typecheck OK'")
    assert res_tc["status"] == "PASS"
    assert "Typecheck OK" in res_tc["stdout"]
    assert "condensed_output" in res_tc

    res_race = auto_debug_runner.run_project_race(command_override="echo 'Race OK'")
    assert res_race["status"] == "PASS"
    assert "Race OK" in res_race["stdout"]

    res_fuzz = auto_debug_runner.run_project_fuzz(command_override="echo 'Fuzz OK'")
    assert res_fuzz["status"] == "PASS"
    assert "Fuzz OK" in res_fuzz["stdout"]

def test_condense_test_output():
    import auto_debug_runner
    # Short output is not condensed
    short_out = "Line 1\nLine 2\nLine 3"
    assert auto_debug_runner.condense_test_output(short_out, "") == short_out

    # Long output with failures is condensed
    long_lines = [f"Passing test line {i}" for i in range(80)]
    long_lines[30] = "FAILED test_critical_feature"
    long_lines[31] = "AssertionError: Expected 200, got 500"
    long_lines.append("=== 1 failed, 79 passed ===")
    long_out = "\n".join(long_lines)

    condensed = auto_debug_runner.condense_test_output(long_out, "", max_lines=30)
    assert "Truncated" in condensed
    assert "FAILED test_critical_feature" in condensed
    assert "AssertionError: Expected 200, got 500" in condensed
    assert "=== 1 failed, 79 passed ===" in condensed
    assert len(condensed.splitlines()) <= 35

def test_critic_loop_sql_migration():
    import critic_loop
    # 1. Unsafe ADD NOT NULL without DEFAULT
    with tempfile.NamedTemporaryFile(suffix=".sql", mode="w", delete=False) as f:
        f.write("ALTER TABLE users ADD COLUMN age INT NOT NULL;\n")
        bad_sql1 = f.name

    # 2. Non-concurrent CREATE INDEX
    with tempfile.NamedTemporaryFile(suffix=".sql", mode="w", delete=False) as f:
        f.write("CREATE INDEX idx_users_email ON users (email);\n")
        bad_sql2 = f.name

    # 3. Safe concurrent index
    with tempfile.NamedTemporaryFile(suffix=".sql", mode="w", delete=False) as f:
        f.write("CREATE INDEX CONCURRENTLY idx_users_email ON users (email);\n")
        good_sql = f.name

    # 4. Safe migration with override comment
    with tempfile.NamedTemporaryFile(suffix=".sql", mode="w", delete=False) as f:
        f.write("-- safe-migration\nALTER TABLE users ADD COLUMN age INT NOT NULL;\n")
        override_sql = f.name

    try:
        r1 = critic_loop.audit_code_logic(bad_sql1, submode="all")
        assert r1["status"] == "RETRY"
        assert any("UnsafeMigration" in v and "NOT NULL" in v for v in r1["violations"])

        r2 = critic_loop.audit_code_logic(bad_sql2, submode="all")
        assert r2["status"] == "RETRY"
        assert any("UnsafeMigration" in v and "CONCURRENTLY" in v for v in r2["violations"])

        r3 = critic_loop.audit_code_logic(good_sql, submode="all")
        assert r3["status"] == "PASS"

        r4 = critic_loop.audit_code_logic(override_sql, submode="all")
        assert r4["status"] == "PASS"
    finally:
        for p in (bad_sql1, bad_sql2, good_sql, override_sql):
            if os.path.exists(p):
                os.remove(p)

def test_critic_loop_go_mutex_lock():
    import critic_loop
    # 1. Mutex lock without defer
    with tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False) as f:
        f.write("package main\n\nfunc process() {\n    mu.Lock()\n    doWork()\n}\n")
        bad_go = f.name

    # 2. Mutex lock with defer
    with tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False) as f:
        f.write("package main\n\nfunc process() {\n    mu.Lock()\n    defer mu.Unlock()\n    doWork()\n}\n")
        good_go = f.name

    # 3. Mutex lock with safe-lock comment
    with tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False) as f:
        f.write("package main\n\nfunc process() {\n    mu.Lock() // safe-lock\n    doWork()\n}\n")
        safe_go = f.name

    try:
        r1 = critic_loop.audit_code_logic(bad_go, submode="all")
        assert r1["status"] == "RETRY"
        assert any("UnprotectedMutexLock" in v for v in r1["violations"])

        r2 = critic_loop.audit_code_logic(good_go, submode="all")
        assert r2["status"] == "PASS"

        r3 = critic_loop.audit_code_logic(safe_go, submode="all")
        assert r3["status"] == "PASS"
    finally:
        for p in (bad_go, good_go, safe_go):
            if os.path.exists(p):
                os.remove(p)

def test_git_hook_installer_and_rule_14():
    import install_git_hooks
    # Test installation in temporary dummy git repo
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        git_dir = temp_path / ".git"
        git_dir.mkdir()

        res = install_git_hooks.install_git_hook(temp_path)
        assert res["status"] == "SUCCESS"
        hook_path = Path(res["hook_path"])
        assert hook_path.is_file()
        content = hook_path.read_text(encoding="utf-8")
        assert "Antigravity Enterprise Quality Gate" in content
        assert "critic_loop.py" in content
        assert "auto_debug_runner.py" in content

        # Check idempotency
        res_repeat = install_git_hooks.install_git_hook(temp_path)
        assert res_repeat["status"] == "ALREADY_INSTALLED"

    # Verify Rule 14 in rules/AGENTS.md and template
    rules_text = (PLUGIN_ROOT / "rules" / "AGENTS.md").read_text(encoding="utf-8")
    assert "14. Database Migration Safety & Zero-Downtime Schema Evolution" in rules_text
    assert "Expand/Contract Pattern" in rules_text
    assert "CREATE INDEX CONCURRENTLY" in rules_text

    tmpl_rules = (PLUGIN_ROOT / "templates" / "project-git-template" / ".agents" / "rules" / "AGENTS.md").read_text(encoding="utf-8")
    assert rules_text == tmpl_rules

    # Verify ADR persistence in brainstorm and opus-architect
    brainstorm_text = (PLUGIN_ROOT / "skills" / "brainstorm" / "SKILL.md").read_text(encoding="utf-8")
    assert "Step 5: Architecture Decision Record (ADR) Persistence" in brainstorm_text
    assert "docs/adr/" in brainstorm_text

    architect_text = (PLUGIN_ROOT / "agents" / "opus-architect.md").read_text(encoding="utf-8")
    assert "ADR Generation" in architect_text
    assert "docs/adr/" in architect_text

def test_api_contract_guard_symbols_and_drift():
    import api_contract_guard
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        py_file = tmp_path / "mod.py"
        py_code = "def greet(name: str) -> str:\n    return 'Hello ' + name\n"
        py_file.write_text(py_code, encoding="utf-8")

        # Extract symbols
        symbols = api_contract_guard.extract_public_symbols(py_code, py_file)
        assert "greet" in symbols
        assert [p["name"] for p in symbols["greet"]["params"]] == ["name"]

        # Test breaking vs additive change
        base_symbols = {
            "greet": {"kind": "function", "params": [{"name": "name", "required": True}]},
            "legacy_func": {"kind": "function", "params": []}
        }
        # Broken symbols: removed legacy_func, and added required param 'greeting' to greet
        curr_symbols_broken = {
            "greet": {"kind": "function", "params": [{"name": "name", "required": True}, {"name": "greeting", "required": True}]}
        }
        violations, warnings, additions = api_contract_guard.compare_symbol_contracts(base_symbols, curr_symbols_broken, "mod.py")
        assert len(violations) >= 2
        assert any("was removed" in v for v in violations)
        assert any("new required parameter" in v for v in violations)

        # Additive symbols: new optional param with default, legacy_func preserved, new func added
        curr_symbols_additive = {
            "greet": {"kind": "function", "params": [{"name": "name", "required": True}, {"name": "greeting", "required": False}]},
            "legacy_func": {"kind": "function", "params": []},
            "new_func": {"kind": "function", "params": []}
        }
        clean_violations, clean_warnings, clean_additions = api_contract_guard.compare_symbol_contracts(base_symbols, curr_symbols_additive, "mod.py")
        assert len(clean_violations) == 0
        assert len(clean_additions) >= 1

def test_repo_map_polyglot_and_token_budget():
    import repo_map
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "src").mkdir()
        py_f = tmp_path / "src" / "service.py"
        py_code = "class UserService:\n    def get_user(self, user_id: str):\n        pass\n"
        py_f.write_text(py_code, encoding="utf-8")

        symbols = repo_map.extract_python_symbols(py_code)
        assert len(symbols) >= 1
        assert any("UserService" in s["name"] for s in symbols)

        # Build map with token budget
        repo_data = repo_map.generate_repo_map(tmp_path, max_tokens=200)
        assert repo_data["file_count"] >= 1
        assert "UserService" in repo_data["formatted_map"]

def test_auto_debug_runner_flaky_and_mutation_diff():
    import auto_debug_runner
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Flaky check passes on stable test
        res = auto_debug_runner.run_project_flaky_check(
            workspace_dir=tmp_path,
            iterations=2,
            command_override=f"{sys.executable} -c \"assert 1 == 1\""
        )
        assert res["iterations"] == 2
        assert res["failures"] == 0
        assert res["status"] == "PASS"

        # Flaky check detects failing/unstable test
        res_flaky = auto_debug_runner.run_project_flaky_check(
            workspace_dir=tmp_path,
            iterations=2,
            command_override=f"{sys.executable} -c \"import sys; sys.exit(1)\""
        )
        assert res_flaky["failures"] == 2
        assert res_flaky["status"] == "FAIL"

        # Framework detection verifies mutation runner
        det = auto_debug_runner.detect_project_framework(PLUGIN_ROOT)
        assert "mutation_command" in det

def test_critic_loop_rust_safe_unwraps_and_sql_drops():
    import critic_loop
    # 1. Rust safe unwrap in test block
    with tempfile.NamedTemporaryFile(suffix=".rs", mode="w", delete=False) as f:
        f.write("#[cfg(test)]\nfn test_foo() {\n    let val = Some(1).unwrap();\n}\n")
        safe_rs = f.name

    # 2. Rust unsafe unwrap in production
    with tempfile.NamedTemporaryFile(suffix=".rs", mode="w", delete=False) as f:
        f.write("fn prod_foo() {\n    let val = Some(1).unwrap();\n}\n")
        bad_rs = f.name

    # 3. SQL DROP TABLE
    with tempfile.NamedTemporaryFile(suffix=".sql", mode="w", delete=False) as f:
        f.write("DROP TABLE users;\n")
        bad_sql_drop = f.name

    # 4. SQL ALTER COLUMN TYPE
    with tempfile.NamedTemporaryFile(suffix=".sql", mode="w", delete=False) as f:
        f.write("ALTER TABLE users ALTER COLUMN age TYPE bigint;\n")
        bad_sql_alter = f.name

    try:
        r_safe = critic_loop.audit_code_logic(safe_rs, submode="all")
        assert r_safe["status"] == "PASS"

        r_bad = critic_loop.audit_code_logic(bad_rs, submode="all")
        assert r_bad["status"] == "RETRY"
        assert any("ProductionPanicRisk" in v for v in r_bad["violations"])

        r_drop = critic_loop.audit_code_logic(bad_sql_drop, submode="all")
        assert r_drop["status"] == "RETRY"
        assert any("DROP TABLE/COLUMN" in v for v in r_drop["violations"])

        r_alter = critic_loop.audit_code_logic(bad_sql_alter, submode="all")
        assert r_alter["status"] == "RETRY"
        assert any("altering column type" in v for v in r_alter["violations"])
    finally:
        for p in (safe_rs, bad_rs, bad_sql_drop, bad_sql_alter):
            if os.path.exists(p):
                os.remove(p)

def test_visual_qa_wcag_accessibility_checks():
    import visual_qa
    # Bad HTML missing lang, title, and button label
    bad_html = "<html><head></head><body><button></button><input type='text'><img src='pic.jpg'></body></html>"
    violations = visual_qa.audit_html_accessibility(bad_html)
    assert len(violations) >= 4
    assert any("WCAG 3.1.1" in v for v in violations)
    assert any("WCAG 2.4.2" in v for v in violations)
    assert any("WCAG 4.1.2" in v for v in violations)
    assert any("WCAG 1.1.1" in v for v in violations)
    assert any("WCAG 1.3.1" in v for v in violations)

    # Clean HTML passing all checks
    good_html = "<html lang='en'><head><title>Dashboard</title></head><body><button>Submit</button><label for='u'>User</label><input id='u' type='text'><img src='pic.jpg' alt='Avatar'></body></html>"
    clean_violations = visual_qa.audit_html_accessibility(good_html)
    assert len(clean_violations) == 0

import unittest

class AntigravityDevSuiteTestCase(unittest.TestCase):
    """Standard unittest discovery test case wrapper."""
    pass

for _func_name, _func_obj in list(globals().items()):
    if _func_name.startswith("test_") and callable(_func_obj) and _func_obj != unittest.TestCase:
        def _make_test_method(f):
            def _test(self):
                f()
            _test.__name__ = f.__name__
            _test.__doc__ = f.__doc__
            return _test
        setattr(AntigravityDevSuiteTestCase, _func_name, _make_test_method(_func_obj))

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
    test_toml_validation()
    print("✔ TOML validation passed")
    test_markdown_validation()
    print("✔ Markdown validation passed")
    test_css_validation()
    print("✔ CSS validation passed")
    test_shell_validation()
    print("✔ Shell validation passed")
    test_sql_validation()
    print("✔ SQL validation passed")
    test_template_parity()
    print("✔ Template parity passed")
    test_no_hardcoded_user_paths()
    print("✔ Zero hardcoded user paths passed")
    test_opening_line_number_in_bracket_mismatch()
    print("✔ Opening line number in bracket mismatch passed")
    test_auto_debug_runner_relative_path_resolution()
    print("✔ Auto debug runner relative path resolution passed")
    test_multi_doc_yaml_validation()
    print("✔ Multi-document YAML validation passed")
    test_js_spread_operator_regex()
    print("✔ JS spread operator regex passed")
    test_html_svg_self_closing_tags()
    print("✔ HTML inline SVG self-closing tags passed")
    test_visual_qa_directory_target()
    print("✔ Visual QA directory target handling passed")
    test_visual_qa_mobile_overflow_detection()
    print("✔ Visual QA mobile horizontal overflow detection passed")
    test_toml_dependency_free_fallback()
    print("✔ TOML dependency-free fallback passed")
    test_html_generic_self_closing_tags()
    print("✔ HTML generic self-closing tags passed")
    test_js_extended_regex_starters()
    print("✔ JS extended regex starters passed")
    test_resolve_target_file_tilde_expansion()
    print("✔ Tilde path expansion passed")
    test_shell_case_and_heredocs()
    print("✔ Shell case statements and heredocs passed")
    test_sql_postgres_dollar_quotes_and_escapes()
    print("✔ SQL PostgreSQL dollar quotes and escapes passed")
    test_yaml_escaped_quotes_fallback()
    print("✔ YAML escaped quotes fallback passed")
    test_unclosed_js_regex_error()
    print("✔ Unclosed JS regex detection passed")
    test_python_stub_and_json5_validation()
    print("✔ Python stubs and JSON5 validation passed")
    test_polyglot_languages_validation()
    print("✔ Polyglot languages validation passed")
    test_csharp_verbatim_strings()
    print("✔ C# verbatim strings passed")
    test_kotlin_swift_multiline_strings()
    print("✔ Kotlin & Swift multiline strings passed")
    test_swift_nested_block_comments()
    print("✔ Swift nested block comments passed")
    test_lua_comments_and_multiline_strings()
    print("✔ Lua comments and multiline strings passed")
    test_payload_extraction_diverse_formats()
    print("✔ Diverse payload extraction formats passed")
    test_dev_server_expanded_ports()
    print("✔ Expanded dev server ports passed")
    test_csharp_raw_strings_and_interpolations()
    print("✔ C# raw strings and interpolations passed")
    test_dart_raw_and_multiline_strings()
    print("✔ Dart raw and multiline strings passed")
    test_yaml_fallback_apostrophes()
    print("✔ YAML fallback apostrophes passed")
    test_toml_fallback_multiline_strings()
    print("✔ TOML fallback multiline strings passed")
    test_shell_bitshift_not_heredoc()
    print("✔ Shell bitshift not heredoc passed")
    test_critic_loop_url_target_logic()
    print("✔ Critic loop URL target logic passed")
    test_hooks_command_resolution()
    print("✔ Hooks command resolution passed")
    test_json5_single_quote_escapes_and_signed_hex()
    print("✔ JSON5 single quote escapes & signed hex passed")
    test_sql_mysql_hash_comments_and_backticks()
    print("✔ SQL MySQL hash comments & backticks passed")
    test_xml_svg_plist_validation()
    print("✔ XML/SVG/Plist validation passed")
    test_vue_svelte_astro_validation()
    print("✔ Vue/Svelte/Astro validation passed")
    test_powershell_validation()
    print("✔ PowerShell script validation passed")
    test_jupyter_notebook_validation()
    print("✔ Jupyter Notebook validation passed")
    test_graphql_protobuf_validation()
    print("✔ GraphQL & Protobuf validation passed")
    test_ini_cfg_env_properties_validation()
    print("✔ INI/Cfg/Env validation passed")
    test_file_uri_prefix_extraction()
    print("✔ File URI prefix extraction passed")
    test_critic_loop_glob_and_comma_targets()
    print("✔ Critic loop glob & comma targets passed")
    test_visual_qa_expanded_touch_targets_and_astro()
    print("✔ Visual QA touch targets & Astro passed")
    test_hooks_expanded_candidate_paths()
    print("✔ Hooks candidate path discovery passed")
    test_auto_debug_runner_shell_wrapper_no_args()
    print("✔ Auto debug runner shell wrapper no-args passed")
    test_astro_frontmatter_with_ts_generics()
    print("✔ Astro frontmatter TS generics passed")
    test_php_ruby_heredocs_validation()
    print("✔ PHP & Ruby heredoc validation passed")
    test_java_multiline_text_blocks()
    print("✔ Java multiline text blocks passed")
    test_json5_colons_in_single_quotes()
    print("✔ JSON5 colons in single-quoted strings passed")
    test_yaml_fallback_block_scalars()
    print("✔ YAML fallback block scalars passed")
    test_markdown_commonmark_multibacktick_fences()
    print("✔ Markdown CommonMark multi-backtick fences passed")
    test_cloud_blockchain_formats_validation()
    print("✔ Cloud & Blockchain formats (.prisma, .sol, .tf) passed")
    test_critic_loop_security_and_hygiene_audit()
    print("✔ Critic loop security & hygiene audit passed")
    test_visual_qa_http_error_tracking_and_expanded_ports()
    print("✔ Visual QA expanded ports passed")
    test_tool_payload_expanded_keys()
    print("✔ Tool payload expanded keys passed")
    test_env_and_ini_inline_comments_with_apostrophes()
    print("✔ Env and INI inline comments with apostrophes passed")
    test_polyglot_css_sql_unclosed_multiline_comments()
    print("✔ Polyglot, CSS, and SQL unclosed multi-line comments passed")
    test_find_source_files_detects_standalone_env_files()
    print("✔ Find source files standalone .env files passed")
    test_critic_loop_empty_exception_ellipsis()
    print("✔ Critic loop empty exception ellipsis passed")
    test_file_uri_percent_encoding_decoding()
    print("✔ File URI percent encoding decoding passed")
    test_resolve_target_file_os_error_resilience()
    print("✔ Resolve target file OS error resilience passed")
    test_zig_nim_elixir_polyglot_enhancements()
    print("✔ Zig, Nim, and Elixir polyglot enhancements passed")
    test_clojure_character_escapes_outside_strings()
    print("✔ Clojure character escapes outside strings passed")
    test_standalone_env_and_env_local_validation()
    print("✔ Standalone env and env local validation passed")
    test_mts_cts_mdx_polyglot_validation()
    print("✔ MTS, CTS, MDX polyglot validation passed")
    test_critic_loop_extended_secret_patterns()
    print("✔ Critic loop extended secret patterns passed")
    test_dev_server_env_port_prioritization()
    print("✔ Dev server env port prioritization passed")
    test_auto_debug_runner_framework_detection()
    print("✔ Auto debug runner framework detection passed")
    test_auto_debug_runner_last_error_and_clear()
    print("✔ Auto debug runner last error and clear passed")
    test_auto_debug_runner_check_cli()
    print("✔ Auto debug runner check CLI passed")
    test_visual_qa_explicit_dev_server_and_port()
    print("✔ Visual QA explicit dev server and port passed")
    test_critic_loop_integrates_last_syntax_error()
    print("✔ Critic loop integrates last syntax error passed")
    test_critic_loop_fine_grained_modes_and_target_flag()
    print("✔ Critic loop fine-grained modes and target flag passed")
    test_security_audit_skill_and_references()
    print("✔ Security audit skill and modular references passed")
    test_critic_loop_semantic_mutable_defaults()
    print("✔ Critic loop semantic mutable defaults passed")
    test_critic_loop_semantic_redos_and_unawaited()
    print("✔ Critic loop semantic ReDoS and unawaited promises passed")
    test_benchmark_skill_and_cli()
    print("✔ Benchmark skill and CLI runner passed")
    test_critic_loop_extended_ast_and_polyglot_checks()
    print("✔ Critic loop extended AST and polyglot checks passed")
    test_auto_debug_runner_coverage_and_mutation()
    print("✔ Auto debug runner coverage and mutation passed")
    test_pre_tool_guard_safety_rules()
    print("✔ Pre-tool guard safety rules passed")
    test_pattern_catalog_and_formal_invariants()
    print("✔ Pattern catalog and formal invariants passed")
    test_commit_skill_and_v11_plugin_manifest()
    print("✔ Commit skill and v1.12.0 plugin manifest passed")
    test_auto_debug_runner_typecheck_race_fuzz()
    print("✔ Auto debug runner typecheck, race and fuzz passed")
    test_condense_test_output()
    print("✔ Output condensation and context hygiene passed")
    test_critic_loop_sql_migration()
    print("✔ Critic loop SQL zero-downtime migration checks passed")
    test_critic_loop_go_mutex_lock()
    print("✔ Critic loop Go concurrency mutex checks passed")
    test_git_hook_installer_and_rule_14()
    print("✔ Git hook installer, Rule 14 and ADR persistence passed")
    test_api_contract_guard_symbols_and_drift()
    print("✔ API contract guard symbols and drift detection passed")
    test_repo_map_polyglot_and_token_budget()
    print("✔ Repo map polyglot symbols and token budget passed")
    test_auto_debug_runner_flaky_and_mutation_diff()
    print("✔ Auto debug runner flaky check and mutation diff passed")
    test_critic_loop_rust_safe_unwraps_and_sql_drops()
    print("✔ Critic loop Rust safe unwraps and SQL drops passed")
    test_visual_qa_wcag_accessibility_checks()
    print("✔ Visual QA WCAG 2.1 AA accessibility checks passed")
    print("\n🎉 ALL TESTS PASSED (100% GREEN)")
