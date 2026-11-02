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
import subprocess
import sys
import tempfile
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
        self.env = {"HOME": str(self.home), "USERPROFILE": str(self.home), "GEMINI_HOME": str(self.home / ".gemini")}
        for k in ("AGY_STOP_GATE_DISABLE", "AGY_REQUIRE_TESTS", "AGY_PRE_TOOL_GUARD", "AGY_AUTO_DEBUG"):
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
        for tool in REAL_FILE_TOOLS:
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


class TestDoctor(Base):
    def test_doctor_end_to_end(self):
        env = dict(os.environ, **self.env)
        subprocess.run([sys.executable, str(SCRIPTS / "setup_hooks.py"), "install"], env=env, check=True, capture_output=True)
        res = run(["doctor"], env=self.env)
        self.assertEqual(res.returncode, 0, res.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
