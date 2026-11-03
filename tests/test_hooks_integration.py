#!/usr/bin/env python3
"""Integration tests that feed the hooks payloads in the real Antigravity format.

Payload shapes follow https://antigravity.google/docs/hooks: tool names
write_to_file / replace_file_content / multi_replace_file_content / run_command,
arguments TargetFile / CodeContent / ReplacementContent / CommandLine, and Stop
payloads with terminationReason such as "model_stop".

Run with:  python tests/test_hooks_integration.py   (or pytest)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
HOOK = SCRIPTS / "agy_hook.py"
sys.path.insert(0, str(SCRIPTS))

REAL_FILE_TOOLS = ["write_to_file", "replace_file_content", "multi_replace_file_content"]


def run(args, payload=None, env=None, cwd=None):
    full_env = dict(os.environ)
    full_env.update(env or {})
    res = subprocess.run(
        [sys.executable, str(HOOK)] + args,
        input=json.dumps(payload) if payload is not None else "",
        capture_output=True, text=True, env=full_env, cwd=cwd, timeout=300,
    )
    return res


def run_json(args, payload, env=None):
    res = run(args, payload, env)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def git(repo, *args):
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t"] + list(args),
        cwd=str(repo), check=True, capture_output=True,
    )


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.env = {"HOME": str(self.home), "USERPROFILE": str(self.home), "GEMINI_HOME": str(self.home / ".gemini"),
                    # Acceptance criteria have their own tests (TestGuidance).
                    "AGY_CRITERIA": "0"}
        if "PLAYWRIGHT_BROWSERS_PATH" in os.environ:
            self.env["PLAYWRIGHT_BROWSERS_PATH"] = os.environ["PLAYWRIGHT_BROWSERS_PATH"]
        else:
            for cand in [
                Path.home() / "Library" / "Caches" / "ms-playwright",
                Path.home() / ".cache" / "ms-playwright",
                Path.home() / "AppData" / "Local" / "ms-playwright",
            ]:
                if cand.is_dir():
                    self.env["PLAYWRIGHT_BROWSERS_PATH"] = str(cand)
                    break
        for k in ("AGY_STOP_GATE_DISABLE", "AGY_REQUIRE_TESTS", "AGY_PRE_TOOL_GUARD", "AGY_AUTO_DEBUG", "AGY_VISUAL_QA"):
            os.environ.pop(k, None)
        self.repo = self.tmp / "proj"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        (self.repo / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")
        self.base = {"workspacePaths": [str(self.repo)], "conversationId": "conv-1"}

    def tearDown(self):
        self._tmp.cleanup()

    def stop(self, reason="model_stop", **extra):
        payload = dict(self.base, terminationReason=reason, executionNum=1, fullyIdle=True)
        payload.update(extra)
        return run_json(["stop"], payload, self.env)

    def write(self, rel, text):
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p


class TestHookRegistration(Base):
    def test_matchers_cover_real_tool_names(self):
        import setup_hooks
        entry = setup_hooks.build_entry()
        pre = entry["PreToolUse"][0]["matcher"]
        post = entry["PostToolUse"][0]["matcher"]
        for tool in REAL_FILE_TOOLS + ["run_command"]:
            self.assertTrue(re.fullmatch(pre, tool), tool)
        for tool in REAL_FILE_TOOLS + ["view_file", "grep_search", "run_command"]:
            self.assertTrue(re.fullmatch(post, tool), tool)
        self.assertGreaterEqual(entry["Stop"][0]["timeout"], 300)
        for event in ("SessionStart", "PreToolUse", "PostToolUse", "PreInvocation", "Stop"):
            self.assertIn(event, entry)

    def test_install_keeps_other_hooks_and_uninstall_removes_only_ours(self):
        hooks_file = self.home / ".gemini" / "config" / "hooks.json"
        hooks_file.parent.mkdir(parents=True)
        hooks_file.write_text(json.dumps({
            "my-linter": {"PostToolUse": [{"matcher": "run_command", "hooks": [{"command": "lint"}]}]},
            "antigravity-dev-suite-hooks": {"Stop": []},
        }), encoding="utf-8")
        env = dict(os.environ, **self.env)
        subprocess.run([sys.executable, str(SCRIPTS / "setup_hooks.py"), "install"], env=env, check=True, capture_output=True)
        data = json.loads(hooks_file.read_text(encoding="utf-8"))
        self.assertIn("my-linter", data)
        self.assertIn("antigravity-dev-suite", data)
        self.assertNotIn("antigravity-dev-suite-hooks", data)
        status = subprocess.run([sys.executable, str(SCRIPTS / "setup_hooks.py"), "status"], env=env, capture_output=True, text=True)
        self.assertEqual(status.returncode, 0, status.stdout)
        subprocess.run([sys.executable, str(SCRIPTS / "setup_hooks.py"), "uninstall"], env=env, check=True, capture_output=True)
        data = json.loads(hooks_file.read_text(encoding="utf-8"))
        self.assertEqual(list(data), ["my-linter"])

    def test_every_script_supports_python_39(self):
        for script in SCRIPTS.glob("*.py"):
            src = script.read_text(encoding="utf-8")
            if re.search(r"(->|:)\s*[\w\[\]]+\s*\|\s*[\w\[\]]+", src):
                self.assertIn("from __future__ import annotations", src, script.name)


class TestGuard(Base):
    def pre(self, name, args):
        return run_json(["pre-tool"], dict(self.base, toolCall={"name": name, "args": args}), self.env)

    def test_secret_in_each_real_write_tool_is_denied(self):
        key = "AKIA" + "ABCDEFGHIJKLMNOP"
        cases = [
            ("write_to_file", {"TargetFile": "a.py", "CodeContent": f"k='{key}'"}),
            ("replace_file_content", {"TargetFile": "a.py", "TargetContent": "x", "ReplacementContent": f"k='{key}'"}),
            ("multi_replace_file_content", {"TargetFile": "a.py", "ReplacementChunks": [{"ReplacementContent": f"k='{key}'"}]}),
        ]
        for name, args in cases:
            self.assertEqual(self.pre(name, args)["decision"], "deny", name)

    def test_gate_bypass_commands_are_denied(self):
        for cmd in [
            "git commit --no-verify -m wip",
            "git commit -nm wip",
            "AGY_STOP_GATE_DISABLE=1 git status",
            "echo '{\"status\":\"PASS\"}' > /tmp/agy_last_test_run.json",
            "rm .git/agy/state.json",
            "git config core.hooksPath /dev/null",
            "rm -fr /",
            "git push -f origin HEAD:main",
        ]:
            self.assertEqual(self.pre("run_command", {"CommandLine": cmd})["decision"], "deny", cmd)

    def test_normal_commands_are_allowed(self):
        for cmd in ["git status", "pytest -v", "git commit -m 'add feature'", "rm -rf build/", "git push origin feature"]:
            self.assertEqual(self.pre("run_command", {"CommandLine": cmd})["decision"], "allow", cmd)

    def test_gate_config_file_is_protected(self):
        out = self.pre("write_to_file", {"TargetFile": str(self.repo / ".agents" / "agy.json"), "CodeContent": "{}"})
        self.assertEqual(out["decision"], "deny")


class TestSyntaxFeedback(Base):
    def test_post_tool_error_reaches_model_until_fixed(self):
        bad = self.write("app.py", "def f(:\n    pass\n")
        post = dict(self.base, toolCall={"name": "write_to_file", "args": {"TargetFile": str(bad), "CodeContent": "x"}})
        self.assertEqual(run_json(["post-tool"], post, self.env), {})
        inj = run_json(["pre-invocation"], self.base, self.env)
        self.assertIn("injectSteps", inj)
        self.assertIn("app.py", inj["injectSteps"][0]["ephemeralMessage"])
        bad.write_text("def f():\n    pass\n", encoding="utf-8")
        self.assertEqual(run_json(["pre-invocation"], self.base, self.env), {})

    def test_relative_target_file_is_resolved_against_workspace(self):
        self.write("pkg/mod.py", "def f(:\n")
        post = dict(self.base, toolCall={"name": "replace_file_content", "args": {"TargetFile": "pkg/mod.py"}})
        run_json(["post-tool"], post, self.env)
        self.assertIn("injectSteps", run_json(["pre-invocation"], self.base, self.env))


class TestStopGate(Base):
    GOOD_TEST = (
        "import os, sys\n"
        "sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))\n"
        "from calc.ops import add\n\n"
        "def test_add() -> None:\n"
        "    assert add(2, 3) == 5\n"
    )

    def setUp(self):
        super().setUp()
        try:
            import pytest  # noqa: F401
            self.has_pytest = True
        except ImportError:
            self.has_pytest = False
        run_json(["session-start"], self.base, self.env)

    def test_clean_tree_allows(self):
        self.assertEqual(self.stop()["decision"], "allow")

    def test_model_stop_with_syntax_error_blocks(self):
        self.write("src/calc/ops.py", "def add(a, b:\n")
        out = self.stop("model_stop")
        self.assertEqual(out["decision"], "continue")
        self.assertIn("Syntax", out["reason"])
        self.assertIn("agy_hook.py", out["reason"])  # absolute re-run command

    def test_unknown_termination_reason_is_still_gated(self):
        self.write("src/calc/ops.py", "def add(a, b:\n")
        self.assertEqual(self.stop("NO_TOOL_CALL")["decision"], "continue")
        self.assertEqual(self.stop("something_new")["decision"], "continue")

    def test_max_steps_and_error_are_not_gated(self):
        self.write("src/calc/ops.py", "def add(a, b:\n")
        self.assertEqual(self.stop("max_steps_exceeded")["decision"], "allow")
        self.assertEqual(self.stop("error")["decision"], "allow")

    def test_new_directory_files_are_seen(self):
        # git status shows "?? src/" for a new directory; the gate must still see the files.
        self.write("src/deep/new/mod.py", "def f(:\n")
        self.assertEqual(self.stop()["decision"], "continue")

    def test_production_change_without_test_blocks(self):
        self.write("src/calc/ops.py", "def add(a: int, b: int) -> int:\n    return a + b\n")
        out = self.stop()
        self.assertEqual(out["decision"], "continue")
        self.assertIn("No test written", out["reason"])

    def test_forged_records_do_not_pass_the_gate(self):
        tmpdir = Path(tempfile.gettempdir())
        (tmpdir / "agy_last_test_run.json").write_text('{"status":"PASS"}', encoding="utf-8")
        (tmpdir / "agy_last_critic_run.json").write_text('{"status":"PASS","target":"."}', encoding="utf-8")
        try:
            self.write("src/calc/ops.py", "def add(a, b:\n")
            self.assertEqual(self.stop()["decision"], "continue")
        finally:
            for n in ("agy_last_test_run.json", "agy_last_critic_run.json"):
                (tmpdir / n).unlink()

    def test_failing_tests_block_then_fix_allows_and_is_cached(self):
        if not self.has_pytest:
            self.skipTest("pytest not installed")
        self.write("src/calc/__init__.py", "")
        self.write("src/calc/ops.py", "def add(a: int, b: int) -> int:\n    return a - b\n")
        self.write("tests/test_ops.py", self.GOOD_TEST)
        out = self.stop()
        self.assertEqual(out["decision"], "continue")
        self.assertIn("Tests failed", out["reason"])
        self.write("src/calc/ops.py", "def add(a: int, b: int) -> int:\n    return a + b  # fixed\n")
        self.assertEqual(self.stop()["decision"], "allow")
        self.assertEqual(self.stop()["decision"], "allow")

    def test_committing_does_not_escape_the_gate(self):
        if not self.has_pytest:
            self.skipTest("pytest not installed")
        self.write("src/calc/__init__.py", "")
        self.write("src/calc/ops.py", "def add(a: int, b: int) -> int:\n    return a * b\n")
        self.write("tests/test_ops.py", self.GOOD_TEST)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "wip")
        self.assertEqual(self.stop()["decision"], "continue")

    def test_block_limit_without_progress(self):
        self.write("src/calc/ops.py", "def add(a, b:\n")
        env = dict(self.env, AGY_STOP_GATE_MAX_BLOCKS="2")
        payload = dict(self.base, terminationReason="model_stop", executionNum=1, fullyIdle=True)
        self.assertEqual(run_json(["stop"], payload, env)["decision"], "continue")
        self.assertEqual(run_json(["stop"], payload, env)["decision"], "continue")
        self.assertEqual(run_json(["stop"], payload, env)["decision"], "allow")
        # Any change resets the counter.
        self.write("src/calc/ops.py", "def add(a, b,:\n")
        self.assertEqual(run_json(["stop"], payload, env)["decision"], "continue")

    def test_user_can_disable(self):
        self.write("src/calc/ops.py", "def add(a, b:\n")
        payload = dict(self.base, terminationReason="model_stop")
        self.assertEqual(run_json(["stop"], payload, dict(self.env, AGY_STOP_GATE_DISABLE="1"))["decision"], "allow")

    def test_check_cli_exit_codes(self):
        self.assertEqual(run(["check", str(self.repo)], env=self.env).returncode, 0)
        self.write("src/calc/ops.py", "def add(a, b:\n")
        res = run(["check", str(self.repo)], env=self.env)
        self.assertEqual(res.returncode, 1)
        self.assertIn("RESULT: FAIL", res.stdout)


def playwright_ready() -> bool:
    try:
        from agy_hook import visual_qa_status
        return visual_qa_status()[0]
    except Exception:
        return False


def free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


BROKEN_PAGE = (
    "<!doctype html><html lang=\"en\"><head><title>t</title></head><body>"
    "<div style=\"width:900px\">wide</div><script>throw new Error('boom')</script></body></html>\n"
)
CLEAN_PAGE = (
    "<!doctype html><html lang=\"en\"><head><meta name=\"viewport\" content=\"width=device-width\">"
    "<title>t</title></head><body><p>hello</p></body></html>\n"
)


class TestVisualGate(Base):
    def setUp(self):
        super().setUp()
        run_json(["session-start"], self.base, self.env)
        # No Python test suite here: only the visual step matters.
        (self.repo / "pytest.ini").unlink()
        self.write(".agents/agy.json", json.dumps({"require_tests": False}))
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "config")

    def config(self, cfg):
        cfg = dict(cfg, require_tests=False)
        self.write(".agents/agy.json", json.dumps(cfg))
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "config")
        run_json(["session-start"], dict(self.base, conversationId="conv-cfg"), self.env)
        self.base = dict(self.base, conversationId="conv-cfg")

    def test_frontend_file_selection(self):
        from visual_gate import frontend_files
        files = ["src/App.tsx", "src/App.test.tsx", "styles/a.css", "server/api.ts",
                 "e2e/home.spec.ts", "src/Button.stories.tsx", "index.html", "app.py"]
        self.assertEqual(frontend_files(files), ["src/App.tsx", "styles/a.css", "index.html"])

    def test_server_templates_are_not_opened_from_disk(self):
        from visual_gate import static_html_targets
        self.write("templates/page.html", "<html>{% block body %}{% endblock %}</html>")
        self.write("public/index.html", CLEAN_PAGE)
        targets = static_html_targets(self.repo, ["templates/page.html", "public/index.html"])
        self.assertEqual(len(targets), 1)
        self.assertTrue(targets[0].endswith("index.html"))

    def test_user_can_turn_visual_qa_off(self):
        self.config({"visual_qa": False})
        self.write("index.html", BROKEN_PAGE)
        self.assertEqual(self.stop()["decision"], "allow")

    def test_env_turns_visual_qa_off(self):
        self.write("index.html", BROKEN_PAGE)
        payload = dict(self.base, terminationReason="model_stop")
        self.assertEqual(run_json(["stop"], payload, dict(self.env, AGY_VISUAL_QA="0"))["decision"], "allow")

    def test_unreachable_url_blocks_with_instructions(self):
        self.config({"visual_qa": {"url": f"http://127.0.0.1:{free_port()}"}})
        self.write("src/App.tsx", "export const App = () => <p>hi</p>;\n")
        out = self.stop()
        self.assertEqual(out["decision"], "continue")
        self.assertIn("dev server not running", out["reason"])

    def test_pre_commit_mode_skips_the_browser(self):
        self.config({"visual_qa": {"url": f"http://127.0.0.1:{free_port()}"}})
        self.write("src/App.tsx", "export const App = () => <p>hi</p>;\n")
        res = run(["check", "--no-visual", str(self.repo)], env=self.env)
        self.assertEqual(res.returncode, 0, res.stdout)

    def test_broken_page_blocks_and_clean_page_passes(self):
        if not playwright_ready():
            self.skipTest("Playwright Chromium not available")
        self.write("index.html", BROKEN_PAGE)
        out = self.stop()
        self.assertEqual(out["decision"], "continue")
        self.assertIn("Visual QA found defects", out["reason"])
        self.assertIn("boom", out["reason"])
        self.assertIn("HorizontalOverflowDetected", out["reason"])
        self.assertIn("mobile_preview.png", out["reason"])
        self.write("index.html", CLEAN_PAGE)
        out = self.stop()
        # A new page passes the checks but is shown to agy once for review.
        self.assertNotIn("Visual QA found defects", out.get("reason", ""))
        self.assertEqual(self.stop()["decision"], "allow")

    def test_dev_command_is_started_and_stopped(self):
        if not playwright_ready():
            self.skipTest("Playwright Chromium not available")
        port = free_port()
        self.write("site/index.html", CLEAN_PAGE.replace("<p>", "<script src=\"/missing.js\"></script><p>"))
        py = f'"{sys.executable}"' if " " in sys.executable else sys.executable
        self.config({"visual_qa": {"url": f"http://127.0.0.1:{port}",
                                   "dev_command": f"{py} -m http.server {port} --bind 127.0.0.1 --directory site"}})
        self.write("site/app.css", "p { color: red; }\n")
        out = self.stop()
        self.assertEqual(out["decision"], "continue")
        self.assertIn("HTTP 404", out["reason"])
        from visual_qa import is_http_server_active
        time.sleep(0.5)
        self.assertFalse(is_http_server_active(port, "127.0.0.1"), "dev server left running")


class TestVisualBaseline(TestVisualGate):
    """Before/after comparison against the base commit (PR 2)."""

    def commit_all(self, msg="base"):
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", msg)
        run_json(["session-start"], dict(self.base, conversationId=msg), self.env)
        self.base = dict(self.base, conversationId=msg)

    def test_new_defects_ignores_positions_and_origins(self):
        from visual_gate import new_defects
        base = ["Page error: boom at http://localhost:5001/app.js:10:5", "Failed request: HTTP 404 on http://localhost:5001/a.png"]
        cur = ["Page error: boom at http://localhost:6002/app.js:12:9", "Failed request: HTTP 404 on http://localhost:6002/a.png",
               "Page error: fresh"]
        self.assertEqual(new_defects(cur, base), ["Page error: fresh"])

    def test_old_defects_do_not_block_new_ones_do(self):
        if not playwright_ready():
            self.skipTest("Playwright Chromium not available")
        self.write("index.html", CLEAN_PAGE.replace("<p>", "<script src=\"old-missing.js\"></script><p>"))
        self.commit_all()
        # Text-only edit: the old 404 is still there but must not block.
        self.write("index.html", CLEAN_PAGE.replace("<p>", "<script src=\"old-missing.js\"></script><p>").replace("hello", "hello!"))
        out = self.stop()
        self.assertNotIn("Visual QA found defects", out.get("reason", ""))
        self.write("index.html", BROKEN_PAGE)
        out = self.stop()
        self.assertEqual(out["decision"], "continue")
        self.assertIn("These defects are new", out["reason"])
        self.assertIn("boom", out["reason"])
        res = subprocess.run(["git", "worktree", "list"], cwd=str(self.repo), capture_output=True, text=True)
        self.assertEqual(len(res.stdout.strip().splitlines()), 1, res.stdout)

    def test_visual_change_needs_one_review_turn(self):
        if not playwright_ready():
            self.skipTest("Playwright Chromium not available")
        self.write("index.html", CLEAN_PAGE)
        self.commit_all()
        self.write("index.html", CLEAN_PAGE.replace("<p>hello</p>", "<p style=\"font-size:48px\">hello again</p>"))
        out = self.stop()
        self.assertEqual(out["decision"], "continue")
        self.assertIn("Visual changes to review", out["reason"])
        self.assertIn("desktop_diff.png", out["reason"])
        self.assertIn("All checks pass", out["reason"])
        self.assertEqual(self.stop()["decision"], "allow")

    def test_dev_server_baseline_keeps_real_node_modules(self):
        if not playwright_ready():
            self.skipTest("Playwright Chromium not available")
        self.write("site/index.html", CLEAN_PAGE)
        self.write("node_modules/pkg/index.js", "module.exports = 1;\n")
        self.write(".gitignore", "node_modules/\n")
        py = f'"{sys.executable}"' if " " in sys.executable else sys.executable
        self.write(".agents/agy.json", json.dumps({"require_tests": False, "visual_qa": {
            "dev_command": f"{py} -m http.server {{port}} --bind 127.0.0.1 --directory site"}}))
        self.commit_all()
        self.write("site/index.html", CLEAN_PAGE.replace("<p>", "<script src=\"/missing.js\"></script><p>"))
        out = self.stop()
        self.assertEqual(out["decision"], "continue")
        self.assertIn("These defects are new", out["reason"])
        self.assertIn("missing.js", out["reason"])
        self.assertTrue((self.repo / "node_modules" / "pkg" / "index.js").is_file())
        res = subprocess.run(["git", "worktree", "list"], cwd=str(self.repo), capture_output=True, text=True)
        self.assertEqual(len(res.stdout.strip().splitlines()), 1, res.stdout)


class TestDiscipline(Base):
    """PR 3: tests must fail without the change, lint on changed lines, API review, read before write."""

    def setUp(self):
        super().setUp()
        try:
            import pytest  # noqa: F401
            self.has_pytest = True
        except ImportError:
            self.has_pytest = False

    def commit_all(self, msg):
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", msg)
        conv = f"conv-{msg}"
        run_json(["session-start"], dict(self.base, conversationId=conv), self.env)
        self.base = dict(self.base, conversationId=conv)

    def calc(self, body):
        self.write("src/calc/__init__.py", "")
        self.write("src/calc/ops.py", body)

    TEST = TestStopGate.GOOD_TEST

    def test_scoped_test_command(self):
        from discipline import scoped_test_command
        self.assertEqual(scoped_test_command("pytest -v", ["tests/test_a.py"]), "pytest -v tests/test_a.py")
        self.assertEqual(scoped_test_command("npm test", ["a.test.ts"]), "npm test -- a.test.ts")
        self.assertEqual(scoped_test_command("cargo test", ["x.rs"]), "cargo test")

    def test_test_that_passes_on_old_code_needs_review(self):
        if not self.has_pytest:
            self.skipTest("pytest not installed")
        self.calc("def add(a: int, b: int) -> int:\n    return a + b\n")
        self.commit_all("base")
        self.calc("def add(a: int, b: int) -> int:\n    total = a + b\n    return total\n")
        self.write("tests/test_ops.py", self.TEST)
        out = self.stop()
        self.assertEqual(out["decision"], "continue")
        self.assertIn("Your tests pass without your change", out["reason"])
        self.assertEqual(self.stop()["decision"], "allow")  # one review turn only

    def test_test_that_fails_on_old_code_is_proof(self):
        if not self.has_pytest:
            self.skipTest("pytest not installed")
        self.calc("def add(a: int, b: int) -> int:\n    return a - b\n")
        self.commit_all("buggy")
        self.calc("def add(a: int, b: int) -> int:\n    return a + b\n")
        self.write("tests/test_ops.py", self.TEST)
        self.assertEqual(self.stop()["decision"], "allow")
        res = subprocess.run(["git", "worktree", "list"], cwd=str(self.repo), capture_output=True, text=True)
        self.assertEqual(len(res.stdout.strip().splitlines()), 1, res.stdout)

    def test_public_api_change_needs_review(self):
        self.calc("def add(a: int, b: int) -> int:\n    return a + b\n")
        self.commit_all("api")
        self.calc("def add(a: int) -> int:\n    return a\n")
        env = dict(self.env, AGY_REQUIRE_TESTS="0")
        payload = dict(self.base, terminationReason="model_stop")
        (self.repo / "pytest.ini").unlink()
        out = run_json(["stop"], payload, env)
        self.assertEqual(out["decision"], "continue")
        self.assertIn("Public API changed", out["reason"])
        self.assertIn("symbol_impact.py", out["reason"])

    def test_no_tests_collected_is_not_a_failure_without_test_files(self):
        if not self.has_pytest:
            self.skipTest("pytest not installed")
        self.calc("def add(a: int, b: int) -> int:\n    return a + b\n")
        env = dict(self.env, AGY_REQUIRE_TESTS="0")
        out = run_json(["stop"], dict(self.base, terminationReason="model_stop"), env)
        self.assertEqual(out["decision"], "allow", out.get("reason"))

    def test_test_file_pytest_cannot_see_fails(self):
        if not self.has_pytest:
            self.skipTest("pytest not installed")
        self.calc("def add(a: int, b: int) -> int:\n    return a + b\n")
        self.write("tests/ops_checks.py", self.TEST)
        out = self.stop()
        self.assertEqual(out["decision"], "continue")
        self.assertIn("pytest collected no tests", out["reason"])
        self.assertIn("tests/ops_checks.py", out["reason"])

    def test_changed_lines_without_test_coverage_need_review(self):
        helptext = subprocess.run(["pytest", "--help"], capture_output=True, text=True).stdout \
            if shutil.which("pytest") else ""
        if "--cov" not in helptext:
            self.skipTest("the pytest on PATH has no pytest-cov")
        self.calc("def add(a: int, b: int) -> int:\n    return a - b\n")
        self.commit_all("cov")
        self.calc(
            "def add(a: int, b: int) -> int:\n    return a + b\n\n\n"
            "def clamp(x: int) -> int:\n    if x < 0:\n        return 0\n    return x\n"
        )
        self.write("tests/test_ops.py", self.TEST)
        out = self.stop()
        self.assertEqual(out["decision"], "continue")
        self.assertIn("Changed lines that no test runs", out["reason"])
        self.assertIn("src/calc/ops.py: lines 6-8", out["reason"])
        self.assertEqual(self.stop()["decision"], "allow")

    def test_coverage_helpers(self):
        from discipline import coverage_command, coverage_plugin_missing, executed_lines
        self.assertTrue(coverage_plugin_missing("pytest: error: unrecognized arguments: --cov=."))
        self.assertTrue(coverage_plugin_missing("MISSING DEPENDENCY  Cannot find dependency '@vitest/coverage-v8'"))
        self.assertFalse(coverage_plugin_missing("1 failed, 3 passed"))
        out = self.tmp / "cov"
        self.assertIn("--cov=.", coverage_command(self.repo, "uv run pytest -q", out)[0])
        self.assertIsNone(coverage_command(self.repo, "cargo test", out))
        self.write("package.json", json.dumps({"scripts": {"test": "vitest run"}}))
        cmd, kind, _ = coverage_command(self.repo, "npm test", out)
        self.assertIn("npm test -- --coverage.enabled=true", cmd)
        self.assertEqual(kind, "istanbul")
        report = self.tmp / "coverage-final.json"
        report.write_text(json.dumps({str(self.repo / "src" / "a.ts"): {
            "path": str(self.repo / "src" / "a.ts"),
            "statementMap": {"0": {"start": {"line": 1}}, "1": {"start": {"line": 4}}},
            "s": {"0": 3, "1": 0}}}), encoding="utf-8")
        self.assertEqual(executed_lines(self.repo, "istanbul", report), {"src/a.ts": ({1}, {4})})

    def test_changed_lines(self):
        from discipline import changed_lines
        self.write("a.py", "x = 1\ny = 2\nz = 3\n")
        self.commit_all("lines")
        self.write("a.py", "x = 1\ny = 20\nz = 3\nw = 4\n")
        self.assertEqual(changed_lines(self.repo, "HEAD", "a.py"), {2, 4})
        self.write("new.py", "a = 1\n")
        self.assertIsNone(changed_lines(self.repo, "HEAD", "new.py"))

    def test_lint_blocks_only_on_changed_lines(self):
        import shutil as _sh
        if not _sh.which("ruff"):
            self.skipTest("ruff not installed")
        self.write("ruff.toml", "[lint]\nselect = ['F401']\n")
        self.write("src/legacy.py", "import os\nimport sys\n\nVALUE = 1\n")
        self.commit_all("lint")
        env = dict(self.env, AGY_REQUIRE_TESTS="0")
        payload = dict(self.base, terminationReason="model_stop")
        (self.repo / "pytest.ini").unlink()
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "no-pytest")
        # A change far from the old unused imports must not be blamed for them.
        self.write("src/legacy.py", "import os\nimport sys\n\nVALUE = 2\n")
        self.assertEqual(run_json(["stop"], payload, env)["decision"], "allow")
        # A new unused import on a changed line blocks.
        self.write("src/legacy.py", "import os\nimport sys\nimport json\n\nVALUE = 2\n")
        out = run_json(["stop"], payload, env)
        self.assertEqual(out["decision"], "continue")
        self.assertIn("Lint findings on the lines you changed", out["reason"])
        self.assertIn("json", out["reason"])
        self.assertNotIn("`os`", out["reason"])


class TestLoopBreaker(Base):
    def test_same_failure_gets_debug_protocol_then_escalation_then_allow(self):
        env = dict(self.env, AGY_REQUIRE_TESTS="0")
        payload = dict(self.base, terminationReason="model_stop")
        reasons = []
        for i in range(1, 5):
            # A different broken edit each time, with the same error.
            self.write("app.py", f"X = {i}\ndef f(:\n    pass\n")
            out = run_json(["stop"], payload, env)
            self.assertEqual(out["decision"], "continue", i)
            reasons.append(out["reason"])
        self.assertNotIn("Same failure as last time", reasons[0])
        self.assertIn("Same failure as last time (attempt 2)", reasons[1])
        self.assertIn("hypotheses", reasons[2])
        self.assertIn("You are stuck", reasons[3])
        # Stopping again, with or without a new edit, is allowed.
        self.assertEqual(run_json(["stop"], payload, env)["decision"], "allow")
        self.write("app.py", "X = 9\ndef f(:\n    pass\n")
        self.assertEqual(run_json(["stop"], payload, env)["decision"], "allow")

    def test_a_different_failure_or_a_pass_resets_the_count(self):
        env = dict(self.env, AGY_REQUIRE_TESTS="0")
        payload = dict(self.base, terminationReason="model_stop")
        self.write("app.py", "def f(:\n    pass\n")
        run_json(["stop"], payload, env)
        self.write("app.py", "X = 1\ndef f(:\n    pass\n")
        self.assertIn("attempt 2", run_json(["stop"], payload, env)["reason"])
        self.write("app.py", "def f():\n    return [\n")
        self.assertNotIn("Same failure", run_json(["stop"], payload, env)["reason"])


class TestGuidance(Base):
    def pre_invocation(self, **extra):
        return run_json(["pre-invocation"], dict(self.base, **extra), self.env)

    def messages(self, out):
        return [s["ephemeralMessage"] for s in out.get("injectSteps", [])]

    def test_guided_start_once_per_conversation(self):
        self.write("src/billing/invoice.py", "def total_amount(lines):\n    return sum(lines)\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "code")
        self.env["AGY_CRITERIA"] = "1"
        msgs = self.messages(self.pre_invocation())
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("Guided Start", msgs[0])
        self.assertIn(".agy/criteria.md", msgs[0])
        self.assertIn("invoice.py", msgs[0])  # the repository map
        self.assertEqual(self.pre_invocation(), {})
        self.assertIn("Guided Start", self.messages(self.pre_invocation(conversationId="other"))[0])
        exclude = (self.repo / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        self.assertIn(".agy/", exclude)
        self.write(".agy/criteria.md", "- [ ] x\n")
        status = subprocess.run(["git", "status", "--porcelain"], cwd=str(self.repo), capture_output=True, text=True)
        self.assertNotIn(".agy", status.stdout)

    def test_language_rules_injected_once_when_files_change(self):
        self.pre_invocation()
        self.assertEqual(self.pre_invocation(), {})
        self.write("app.py", "X = 1\n")
        msgs = self.messages(self.pre_invocation())
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("[Antigravity Rules: languages/python]", msgs[0])
        self.assertEqual(self.pre_invocation(), {})
        self.write("web/app.ts", "export const x = 1;\n")
        self.write("db/migrations/001_init.sql", "CREATE TABLE t (id int);\n")
        names = " ".join(self.messages(self.pre_invocation()))
        self.assertIn("languages/typescript", names)
        self.assertIn("database/migrations", names)
        self.assertNotIn("languages/python", names)

    def test_rule_glob_matching(self):
        from guidance import _matches
        self.assertTrue(_matches("a.py", "**/*.py"))
        self.assertTrue(_matches("src/a/b.py", "**/*.py"))
        self.assertTrue(_matches("app/migrations/0001.py", "**/migrations/**"))
        self.assertFalse(_matches("app/migration.py", "**/migrations/**"))

    def test_acceptance_criteria_at_stop(self):
        env = dict(self.env, AGY_CRITERIA="1", AGY_REQUIRE_TESTS="0")
        payload = dict(self.base, terminationReason="model_stop")
        run_json(["session-start"], self.base, env)
        self.write("settings.json", '{"retries": 3}\n')
        out = run_json(["stop"], payload, env)
        self.assertEqual(out["decision"], "continue")
        self.assertIn("No acceptance criteria", out["reason"])
        crit = self.write(".agy/criteria.md", "- [x] retries is 3 — evidence: settings.json\n- [ ] errors are logged\n")
        out = run_json(["stop"], payload, env)
        self.assertEqual(out["decision"], "continue")
        self.assertIn("Acceptance criteria not met", out["reason"])
        self.assertIn("errors are logged", out["reason"])
        self.assertNotIn("retries is 3", out["reason"])
        crit.write_text("- [x] retries is 3 — evidence: settings.json\n- [x] errors are logged\n", encoding="utf-8")
        out = run_json(["stop"], payload, env)
        self.assertIn("ticked without evidence", out["reason"])
        crit.write_text("- [x] retries is 3 — evidence: settings.json\n- [x] errors are logged -> test_log\n", encoding="utf-8")
        self.assertEqual(run_json(["stop"], payload, env)["decision"], "allow")

    def test_criteria_from_an_earlier_conversation_are_stale(self):
        env = dict(self.env, AGY_CRITERIA="1", AGY_REQUIRE_TESTS="0")
        crit = self.write(".agy/criteria.md", "- [x] old task — evidence: done\n")
        old = time.time() - 3600
        os.utime(str(crit), (old, old))
        run_json(["session-start"], self.base, env)
        self.write("settings.json", '{"retries": 3}\n')
        out = run_json(["stop"], dict(self.base, terminationReason="model_stop"), env)
        self.assertIn("from an earlier task", out["reason"])


class TestSecondOpinion(Base):
    """A fake reviewer API on localhost: the hook must send the diff and turn findings into a review."""

    def serve(self, reply):
        import http.server
        import threading
        seen = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                seen["path"] = self.path
                seen["headers"] = {k.lower(): v for k, v in self.headers.items()}
                seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                data = json.dumps(reply).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}", seen

    def setup_project(self, provider, url):
        self.write(".agents/agy.json", json.dumps({"second_opinion": {"provider": provider, "url": url}}))
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "cfg")
        self.write("settings.json", '{"retries": 3}\n')
        return dict(self.env, AGY_REQUIRE_TESTS="0", NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost")

    def test_anthropic_findings_become_a_review(self):
        finding = {"summary": "One bug.", "findings": [
            {"severity": "major", "file": "settings.json", "line": 1, "issue": "retries must be 5", "fix": "set 5"},
            {"severity": "minor", "file": "settings.json", "line": 1, "issue": "nit", "fix": "x"}]}
        url, seen = self.serve({"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(finding)}]})
        env = dict(self.setup_project("anthropic", url), ANTHROPIC_API_KEY="test-key")
        out = run_json(["stop"], dict(self.base, terminationReason="model_stop"), env)
        self.assertEqual(out["decision"], "continue")
        self.assertIn("Second opinion: 1 problem(s)", out["reason"])
        self.assertIn("retries must be 5", out["reason"])
        self.assertNotIn("nit", out["reason"])
        self.assertEqual(seen["headers"].get("x-api-key"), "test-key")
        self.assertEqual(seen["body"]["model"], "claude-opus-5-5")
        self.assertEqual(seen["body"]["output_config"]["format"]["type"], "json_schema")
        self.assertIn('+{"retries": 3}', seen["body"]["messages"][0]["content"])
        self.assertEqual(run_json(["stop"], dict(self.base, terminationReason="model_stop"), env)["decision"], "allow")

    def test_gemini_clean_review_allows(self):
        reply = {"candidates": [{"content": {"parts": [{"text": '{"summary": "Fine.", "findings": []}'}]}}]}
        url, seen = self.serve(reply)
        env = dict(self.setup_project("gemini", url + "/{model}"), GEMINI_API_KEY="g-key")
        out = run_json(["stop"], dict(self.base, terminationReason="model_stop"), env)
        self.assertEqual(out["decision"], "allow")
        self.assertEqual(seen["headers"].get("x-goog-api-key"), "g-key")
        self.assertEqual(seen["path"], "/gemini-2.5-pro")

    def test_no_key_or_refusal_never_blocks(self):
        url, _ = self.serve({"stop_reason": "refusal", "content": []})
        env = self.setup_project("anthropic", url)
        env.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("ANTHROPIC_API_KEY", None)
        self.assertEqual(run_json(["stop"], dict(self.base, terminationReason="model_stop"), env)["decision"], "allow")
        self.write("settings.json", '{"retries": 4}\n')
        env["ANTHROPIC_API_KEY"] = "k"
        self.assertEqual(run_json(["stop"], dict(self.base, terminationReason="model_stop"), env)["decision"], "allow")


class TestGateStats(Base):
    def test_verdicts_are_logged_and_summarised(self):
        env = dict(self.env, AGY_REQUIRE_TESTS="0")
        payload = dict(self.base, terminationReason="model_stop")
        self.write("app.py", "def f(:\n    pass\n")
        self.assertEqual(run_json(["stop"], payload, env)["decision"], "continue")
        self.write("app.py", "def f():\n    pass\n")
        out = run_json(["stop"], payload, env)
        self.assertEqual(out["decision"], "allow", out.get("reason"))
        res = run(["stats", str(self.repo)], env=env)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("2 verdict(s) in 1 conversation(s)", res.stdout)
        self.assertIn("pass 1", res.stdout)
        self.assertIn("block 1", res.stdout)
        self.assertIn("Syntax errors", res.stdout)
        self.assertIn("attempts to pass: 2.0", res.stdout)
        data = json.loads(run(["stats", str(self.repo), "--json", "--days", "1"], env=env).stdout)
        self.assertEqual(data["verdicts"], {"block": 1, "pass": 1})
        self.assertEqual(data["first_try_pass_rate"], 0.0)

    def test_no_log_yet(self):
        res = run(["stats", str(self.repo)], env=self.env)
        self.assertIn("No stop gate verdicts recorded yet", res.stdout)


class TestReadBeforeWrite(Base):
    def tool(self, hook, name, args, **extra):
        payload = dict(self.base, toolCall={"name": name, "args": args})
        payload.update(extra)
        return run_json([hook], payload, self.env)

    def test_edit_of_unread_file_is_denied_after_reads_are_seen(self):
        a = self.write("src/a.py", "A = 1\n")
        b = self.write("src/b.py", "B = 1\n")
        edit_b = {"TargetFile": str(b), "TargetContent": "B = 1", "ReplacementContent": "B = 2"}
        # Fail open: before any read tool reached PostToolUse, edits are allowed.
        self.assertEqual(self.tool("pre-tool", "replace_file_content", edit_b)["decision"], "allow")
        self.tool("post-tool", "view_file", {"AbsolutePath": str(a)})
        out = self.tool("pre-tool", "replace_file_content", edit_b)
        self.assertEqual(out["decision"], "deny")
        self.assertIn("src/b.py", out["reason"])
        edit_a = {"TargetFile": str(a), "TargetContent": "A = 1", "ReplacementContent": "A = 2"}
        self.assertEqual(self.tool("pre-tool", "replace_file_content", edit_a)["decision"], "allow")
        # Paths shown in a tool result count as seen too (grep output).
        self.tool("post-tool", "grep_search", {"Query": "B ="}, toolResult={"output": "src/b.py:1: B = 1"})
        self.assertEqual(self.tool("pre-tool", "replace_file_content", edit_b)["decision"], "allow")

    def test_new_files_and_other_conversations(self):
        a = self.write("src/a.py", "A = 1\n")
        self.tool("post-tool", "view_file", {"AbsolutePath": str(a)})
        new = {"TargetFile": str(self.repo / "src" / "new.py"), "CodeContent": "N = 1\n"}
        self.assertEqual(self.tool("pre-tool", "write_to_file", new)["decision"], "allow")
        other = dict(self.base, conversationId="other",
                     toolCall={"name": "replace_file_content",
                               "args": {"TargetFile": str(a), "TargetContent": "A", "ReplacementContent": "B"}})
        # Another conversation has seen no read yet: fail open.
        self.assertEqual(run_json(["pre-tool"], other, self.env)["decision"], "allow")


class TestDoctor(Base):
    def test_doctor_end_to_end(self):
        env = dict(os.environ, **self.env)
        subprocess.run([sys.executable, str(SCRIPTS / "setup_hooks.py"), "install"], env=env, check=True, capture_output=True)
        res = run(["doctor"], env=self.env)
        self.assertEqual(res.returncode, 0, res.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
