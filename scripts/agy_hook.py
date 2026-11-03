#!/usr/bin/env python3
"""Single entry point for every Antigravity lifecycle hook of the dev suite.

Usage (the installer writes these commands into ~/.gemini/config/hooks.json):

    python agy_hook.py session-start   # SessionStart: remember the base commit
    python agy_hook.py pre-tool        # PreToolUse: safety guard and bypass blocker
    python agy_hook.py post-tool       # PostToolUse: syntax probe of the written file
    python agy_hook.py pre-invocation  # PreInvocation: guided start, language rules, syntax errors
    python agy_hook.py stop            # Stop: run the verification gate
    python agy_hook.py check [DIR]     # Run the same gate by hand (exit 1 on failure)
    python agy_hook.py check --no-visual [DIR]  # Same, without the browser step and reviews
    python agy_hook.py doctor          # Self-test of the installation
    python agy_hook.py stats [DIR] [--days N] [--json]  # Stop gate statistics

Design rules:
- The Stop gate runs the checks itself. It never trusts a record written by the agent.
- Feedback reaches the model only through the Stop "reason" and PreInvocation
  "injectSteps"; PostToolUse output must be "{}".
- An internal error never silently allows the stop: it blocks with the error text,
  bounded by the per-fingerprint block limit so a broken gate cannot loop forever.
- Python 3.9+ standard library only. Works on macOS, Linux and Windows.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

logger = logging.getLogger("agy_hook")

FILE_WRITE_TOOLS = ("write_to_file", "replace_file_content", "multi_replace_file_content")
SHELL_TOOLS = ("run_command",)

# Stop reasons where blocking makes no sense (the agent cannot act on it).
NON_GATED_TERMINATIONS = {"max_steps_exceeded", "error"}

CODE_EXTENSIONS = {
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte",
    ".rs", ".go", ".c", ".cpp", ".cc", ".h", ".hpp", ".cs", ".java",
    ".kt", ".swift", ".php", ".rb", ".sql", ".sh", ".html", ".css", ".scss",
    ".json", ".yaml", ".yml", ".toml",
}
# Languages where a production change must come with a test change.
TESTABLE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte",
    ".rs", ".go", ".cs", ".java", ".kt", ".swift", ".php", ".rb",
}
TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|__tests__|spec|specs|testing)/"
    r"|(^|/)test_[^/]+$"
    r"|_test\.[A-Za-z0-9]+$"
    r"|\.(test|spec)\.[A-Za-z0-9]+$"
    r"|_spec\.rb$"
    r"|Tests?\.(java|kt|cs|swift)$"
    r"|(^|/)conftest\.py$"
)
# Production files that never need their own test.
DEFAULT_TEST_EXEMPT = [
    "*.config.*", "*/migrations/*", "migrations/*", "setup.py", "manage.py",
    "*/__init__.py", "__init__.py", "*.d.ts", "docs/*", "examples/*", "scripts/*",
]
RUST_INLINE_TEST_RE = re.compile(r"#\[cfg\(test\)\]|#\[test\]")

# Tool caches that must never count as changes.
IGNORED_DIRS = {".agy_cache", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", "dist", "build", "target", ".next", "coverage"}
IGNORED_SUFFIXES = (".pyc", ".pyo", ".log")

MAX_REASON_CHARS = 6000
MAX_SECTION_CHARS = 1800


# --------------------------------------------------------------------------- io

def emit(obj: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj))
    sys.stdout.write("\n")
    sys.stdout.flush()


def read_payload() -> Dict[str, Any]:
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return {}
        raw = sys.stdin.read()
    except (OSError, UnicodeDecodeError, ValueError):
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def env_flag(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() not in ("0", "false", "off", "no", "")


def self_command(sub: str) -> str:
    """Absolute command line that runs this script, for messages to the model."""
    try:
        from setup_hooks import _quote
    except Exception:
        def _quote(x: str) -> str:
            return f'"{x}"' if " " in x else x
    return f"{_quote(sys.executable or 'python3')} {_quote(str(Path(__file__).resolve()))} {sub}"


def debug_dump(event: str, payload: Dict[str, Any]) -> None:
    """With AGY_HOOK_DEBUG=1, append raw payloads to ~/.gemini/agy-hook-debug.log."""
    if not env_flag("AGY_HOOK_DEBUG", False):
        return
    try:
        log = Path.home() / ".gemini" / "agy-hook-debug.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.time(), "event": event, "payload": payload}) + "\n")
    except OSError as err:
        logger.debug("Failed writing hook debug log: %s", err)


# -------------------------------------------------------------------------- git

def _git_env() -> Dict[str, str]:
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["LC_ALL"] = "C"
    return env


def git(args: List[str], cwd: Path, timeout: int = 20) -> Tuple[int, str]:
    try:
        res = subprocess.run(
            ["git"] + args, cwd=str(cwd), capture_output=True, text=True,
            env=_git_env(), timeout=timeout, check=False,
            encoding="utf-8", errors="replace",
        )
        return res.returncode, res.stdout
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def git_root(ws: Path) -> Optional[Path]:
    code, out = git(["rev-parse", "--show-toplevel"], ws)
    if code != 0 or not out.strip():
        return None
    return Path(out.strip()).resolve()


def git_head(root: Path) -> str:
    code, out = git(["rev-parse", "HEAD"], root)
    return out.strip() if code == 0 else ""


def workspace_of(payload: Dict[str, Any]) -> Path:
    paths = payload.get("workspacePaths") or []
    if isinstance(paths, list):
        for p in paths:
            if isinstance(p, str) and p.strip():
                cand = Path(p).expanduser()
                if cand.is_dir():
                    return cand.resolve()
    return Path.cwd().resolve()


def project_root(ws: Path) -> Path:
    return git_root(ws) or ws


# ------------------------------------------------------------------------ state

def state_dir(root: Path) -> Path:
    """Per-project state outside the work tree: <git-dir>/agy or ~/.gemini/agy-state/<hash>."""
    code, out = git(["rev-parse", "--absolute-git-dir"], root)
    if code == 0 and out.strip():
        d = Path(out.strip()) / "agy"
    else:
        h = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]
        d = Path.home() / ".gemini" / "agy-state" / h
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        logger.debug("Failed creating state directory: %s", err)
    return d


def load_state(root: Path) -> Dict[str, Any]:
    f = state_dir(root) / "state.json"
    try:
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(root: Path, state: Dict[str, Any]) -> None:
    f = state_dir(root) / "state.json"
    tmp = f.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1)
        os.replace(str(tmp), str(f))
    except OSError as err:
        logger.debug("Failed saving state: %s", err)


def _trim_dict(d: Dict[str, Any], keep: int) -> Dict[str, Any]:
    if len(d) <= keep:
        return d
    items = sorted(d.items(), key=lambda kv: (kv[1] or {}).get("t", 0) if isinstance(kv[1], dict) else 0)
    return dict(items[-keep:])


# ----------------------------------------------------------------- config

def load_project_config(root: Path) -> Dict[str, Any]:
    """Optional .agents/agy.json, edited by the user (the agent is blocked from writing it)."""
    f = root / ".agents" / "agy.json"
    try:
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


# --------------------------------------------------------------- changed files

def _parse_porcelain_z(out: str) -> List[str]:
    files: List[str] = []
    entries = out.split("\0")
    i = 0
    while i < len(entries):
        e = entries[i]
        i += 1
        if len(e) < 4:
            continue
        status, path = e[:2], e[3:]
        if "R" in status or "C" in status:
            i += 1  # skip the original path of a rename/copy
        files.append(path)
    return files


def changed_files(root: Path, base: str = "") -> List[str]:
    """Relative paths of existing files changed in the work tree, staged, untracked
    (including files inside new directories) or committed since `base`."""
    found: List[str] = []
    code, out = git(["status", "--porcelain", "-z", "-uall"], root)
    if code == 0:
        found.extend(_parse_porcelain_z(out))
    if base:
        head = git_head(root)
        if head and head != base:
            code, out = git(["diff", "--name-only", "-z", base, head], root)
            if code == 0:
                found.extend(p for p in out.split("\0") if p)
    seen = set()
    result: List[str] = []
    for rel in found:
        rel = rel.strip().replace("\\", "/")
        if not rel or rel in seen:
            continue
        seen.add(rel)
        if rel.endswith(IGNORED_SUFFIXES) or any(part in IGNORED_DIRS for part in rel.split("/")[:-1]):
            continue
        if (root / rel).is_file():
            result.append(rel)
    return sorted(result)


def is_code(rel: str) -> bool:
    return Path(rel).suffix.lower() in CODE_EXTENSIONS


def is_test(rel: str) -> bool:
    return bool(TEST_PATH_RE.search(rel))


def needs_test(rel: str, exempt: List[str]) -> bool:
    if Path(rel).suffix.lower() not in TESTABLE_EXTENSIONS or is_test(rel):
        return False
    return not any(fnmatch.fnmatch(rel, pat) for pat in exempt)


def fingerprint(root: Path, files: List[str], extra: str = "") -> str:
    h = hashlib.sha256()
    h.update(git_head(root).encode())
    h.update(extra.encode())
    for rel in files:
        h.update(rel.encode("utf-8"))
        try:
            h.update(hashlib.sha256((root / rel).read_bytes()).digest())
        except OSError:
            h.update(b"missing")
    return h.hexdigest()


# ---------------------------------------------------------------------- checks

def _shorten(text: str, limit: int = MAX_SECTION_CHARS) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    head = text[: limit // 3]
    tail = text[-(2 * limit // 3):]
    return f"{head}\n[... {len(text) - limit} characters cut ...]\n{tail}"


def run_shell(cmd: str, cwd: Path, timeout: int, env: Optional[Dict[str, str]] = None) -> Tuple[int, str]:
    try:
        res = subprocess.run(
            cmd, shell=True, cwd=str(cwd), capture_output=True, text=True,  # nosec: user-configured command
            timeout=timeout, check=False, encoding="utf-8", errors="replace",
            env=dict(os.environ, **env) if env else None,
        )
        out = (res.stdout or "") + ("\n" + res.stderr if res.stderr else "")
        return res.returncode, out
    except subprocess.TimeoutExpired:
        return 124, f"Timed out after {timeout}s: {cmd}"
    except OSError as e:
        return 127, f"Cannot run '{cmd}': {e}"


def _condense(out: str) -> str:
    try:
        from auto_debug_runner import condense_test_output
        return condense_test_output(out, "", max_lines=40)
    except Exception:
        return _shorten(out)


def _local_bin(root: Path, name: str) -> Optional[Path]:
    for cand in (root / "node_modules" / ".bin" / name, root / "node_modules" / ".bin" / f"{name}.cmd"):
        if cand.is_file():
            return cand
    return None


def resolve_commands(root: Path, cfg: Dict[str, Any]) -> Dict[str, str]:
    """Test / typecheck / lint commands: project config first, then safe auto-detection.
    Auto-detection only picks tools that are already installed in the project."""
    cmds: Dict[str, str] = {}
    for key in ("test", "typecheck", "lint"):
        val = cfg.get(f"{key}_command")
        if isinstance(val, str) and val.strip():
            cmds[key] = val.strip()
    if "test" not in cmds:
        try:
            from auto_debug_runner import detect_project_framework
            det = detect_project_framework(root)
            if det.get("status") == "DETECTED" and det.get("test_command"):
                cmds["test"] = det["test_command"]
        except Exception as err:
            logger.debug("Failed detecting project test command: %s", err)
    if "typecheck" not in cmds and cfg.get("typecheck_command") is None:
        if (root / "tsconfig.json").is_file() and _local_bin(root, "tsc"):
            cmds["typecheck"] = "npx --no-install tsc --noEmit"
    return {k: v for k, v in cmds.items() if v}


class CheckResult:
    def __init__(self) -> None:
        self.failures: List[Tuple[str, str]] = []
        self.reviews: List[Tuple[str, str]] = []  # agy must look once; they do not fail the gate
        self.notes: List[str] = []
        self.ran: List[str] = []
        self.coverage: Optional[Tuple[str, Path]] = None  # (report kind, report path)

    @property
    def ok(self) -> bool:
        return not self.failures

    def fail(self, title: str, detail: str) -> None:
        self.failures.append((title, _shorten(detail)))


def run_checks(root: Path, files: List[str], cfg: Dict[str, Any], visual: bool = True, base: str = "") -> CheckResult:
    """The verification gate. Cheap checks first; tests only when the code parses.
    `visual=False` skips the browser step (used by the git pre-commit hook)."""
    result = CheckResult()
    code_files = [f for f in files if is_code(f)]
    if not code_files:
        result.notes.append("No code files changed.")
        return result

    # 1. Syntax and structure of every changed file.
    try:
        from validator_core import validate_code_file
        syntax_errors: List[str] = []
        for rel in code_files:
            for err in validate_code_file(root / rel) or []:
                syntax_errors.append(f"{rel}: {err}")
        result.ran.append("syntax")
        if syntax_errors:
            result.fail("Syntax errors", "\n".join(syntax_errors))
    except Exception as e:  # validator crash must be visible
        result.fail("Syntax validator crashed", f"{e}\n{traceback.format_exc(limit=3)}")

    # 2. Static critic, restricted to the changed files.
    if cfg.get("critic", True):
        try:
            from critic_loop import audit_code_logic
            targets = ",".join(str(root / rel) for rel in code_files)
            # "security" = secrets + semantic AST checks; syntax is covered above.
            report = audit_code_logic(targets, submode="security", use_cache=False)
            result.ran.append("critic")
            viols = list(report.get("violations", []))
            if report.get("status") != "PASS" and viols:
                result.fail("Static critic violations", "\n".join(viols[:40]))
        except Exception as e:
            result.fail("Static critic crashed", f"{e}\n{traceback.format_exc(limit=3)}")

    # 3. Test-first: production code changes need test changes.
    require_tests = cfg.get("require_tests", True) and env_flag("AGY_REQUIRE_TESTS", True)
    exempt = DEFAULT_TEST_EXEMPT + [p for p in cfg.get("test_exempt", []) if isinstance(p, str)]
    prod = [f for f in code_files if needs_test(f, exempt)]
    tests = [f for f in code_files if is_test(f)]
    if require_tests:
        # Rust keeps unit tests inline: a changed #[cfg(test)] block counts.
        if prod and not tests:
            inline = [f for f in prod if f.endswith(".rs") and RUST_INLINE_TEST_RE.search(_read(root / f))]
            if not inline:
                result.fail(
                    "No test written for the change",
                    "Production files changed without any new or changed test file:\n"
                    + "\n".join(f"- {f}" for f in prod[:15])
                    + "\nWrite a test that fails without your change and passes with it.",
                )
        result.ran.append("test-first")

    if result.failures and any(t.startswith("Syntax") for t, _ in result.failures):
        result.notes.append("Tests skipped until the syntax errors are fixed.")
        return result

    # 4. Typecheck, lint and tests.
    timeout = int(cfg.get("test_timeout", os.environ.get("AGY_TEST_TIMEOUT", 600)))
    cmds = resolve_commands(root, cfg)
    for key, title in (("typecheck", "Typecheck failed"), ("lint", "Lint failed"), ("test", "Tests failed")):
        cmd = cmds.get(key)
        if not cmd:
            continue
        if key == "test" and visual and prod and require_tests and cfg.get("coverage", True) \
                and env_flag("AGY_COVERAGE", True):
            code, out = run_tests_with_coverage(root, cmd, timeout, result)
        else:
            code, out = run_shell(cmd, root, timeout)
        result.ran.append(key)
        if key == "test" and code == 5 and PYTEST_RE.search(cmd):
            _no_tests_collected(cmd, tests, result)
        elif code != 0:
            result.fail(f"{title} (`{cmd}`, exit {code})", _condense(out))
    if "test" not in cmds:
        result.notes.append(
            "No test command found. Set \"test_command\" in .agents/agy.json to enable the test gate."
        )

    # 4b. Lint on the changed lines only, with the linters the project already has.
    if "lint" not in cmds and cfg.get("lint_changed_lines", True):
        try:
            from discipline import lint_changed_lines
            findings, linters = lint_changed_lines(root, base, code_files, timeout)
            result.ran.extend(f"lint:{n}" for n in linters)
            if findings:
                result.fail("Lint findings on the lines you changed", "\n".join(findings[:40]))
        except Exception as e:
            result.fail("Lint step crashed", f"{e}\n{traceback.format_exc(limit=3)}")

    # 5. Visual QA: open the changed UI in a browser (desktop + mobile).
    if visual:
        run_visual_step(root, code_files, cfg, result, base)

    # 6. Second-look reviews: only when everything else passes (skipped with the browser
    # step by the fast pre-commit mode).
    if result.ok and visual:
        run_reviews(root, code_files, prod, tests, cmds.get("test", ""), cfg, result, base, timeout)
    return result


def run_tests_with_coverage(root: Path, cmd: str, timeout: int, result: CheckResult) -> Tuple[int, str]:
    """Run the tests instrumented for coverage when the runner supports it; otherwise,
    or when the coverage plugin is missing, run the plain command."""
    try:
        from discipline import coverage_command, coverage_plugin_missing
        spec = coverage_command(root, cmd, state_dir(root) / "coverage")
    except Exception as err:
        logger.debug("Coverage setup failed: %s", err)
        spec = None
    if spec is None:
        return run_shell(cmd, root, timeout)
    cov_cmd, kind, report = spec
    try:
        report.unlink(missing_ok=True)
    except OSError as err:
        logger.debug("Failed unlinking coverage report: %s", err)
    # Keep coverage's data file out of the work tree, or it would count as a change.
    code, out = run_shell(cov_cmd, root, timeout, env={"COVERAGE_FILE": str(report.parent / ".coverage")})
    if code != 0 and coverage_plugin_missing(out):
        result.notes.append(
            "Coverage plugin not installed: changed-line coverage skipped "
            "(pytest-cov for pytest, @vitest/coverage-v8 for vitest).")
        return run_shell(cmd, root, timeout)
    if report.is_file():
        result.coverage = (kind, report)
    return code, out


PYTEST_RE = re.compile(r"(^|\s|/)(pytest|py\.test)(\s|$)|-m\s+pytest", re.IGNORECASE)


def _no_tests_collected(cmd: str, tests: List[str], result: CheckResult) -> None:
    """pytest exit 5 = "no tests collected". Not a failure for a project without tests,
    but a test file agy wrote that pytest cannot see proves nothing."""
    py_tests = [t for t in tests if t.endswith(".py")]
    if py_tests:
        result.fail(
            f"pytest collected no tests (`{cmd}`, exit 5)",
            "You changed these test files, but pytest found no test in them:\n"
            + "\n".join(f"- {t}" for t in py_tests[:15])
            + "\nName the files test_*.py or *_test.py, the functions test_*, and the classes "
            "Test* (without __init__). Check testpaths/python_files in pytest.ini or pyproject.toml.",
        )
    else:
        result.notes.append(f"`{cmd}` collected no tests (exit 5): nothing to run yet.")


def run_reviews(root: Path, code_files: List[str], prod: List[str], tests: List[str], test_cmd: str,
                cfg: Dict[str, Any], result: CheckResult, base: str, timeout: int) -> None:
    """Findings that may be intended (a renamed API, a refactor test): agy must look once."""
    if cfg.get("api_guard", True):
        _review_api(root, code_files, result, base)
    if cfg.get("diff_guard", True):
        _review_diff(root, code_files, result, base)
    if cfg.get("prove_tests", True) and prod and tests and test_cmd:
        _review_tests(root, tests, test_cmd, result, base, timeout)
    if result.coverage and prod:
        _review_coverage(root, prod, result, base)


def _review_coverage(root: Path, prod: List[str], result: CheckResult, base: str) -> None:
    try:
        from discipline import uncovered_changed_lines
        kind, report = result.coverage  # type: ignore[misc]
        findings = uncovered_changed_lines(root, base, prod, kind, report)
    except Exception as e:
        result.notes.append(f"Coverage review skipped: {e}")
        return
    result.ran.append("coverage")
    if findings:
        result.reviews.append((
            "Changed lines that no test runs",
            "\n".join(f"- {f}" for f in findings[:20]) +
            "\nAdd tests that execute these lines (error paths and branches too). If a line cannot be "
            "tested sensibly, say which one and why in your answer.",
        ))


def _review_api(root: Path, code_files: List[str], result: CheckResult, base: str) -> None:
    try:
        from discipline import api_changes
        changes = api_changes(root, base, code_files)
    except Exception as e:
        result.notes.append(f"API guard skipped: {e}")
        return
    result.ran.append("api-guard")
    if changes:
        result.reviews.append((
            "Public API changed",
            "\n".join(f"- {c}" for c in changes[:20]) +
            "\nFind every caller first: python3 ~/.gemini/config/plugins/antigravity-dev-suite/scripts/"
            "symbol_impact.py <symbol>. Update the callers, or keep the old signature "
            "(optional new parameters, a deprecated alias). Say which callers you checked.",
        ))


def _review_diff(root: Path, code_files: List[str], result: CheckResult, base: str) -> None:
    try:
        from discipline import diff_hygiene
        hygiene = diff_hygiene(root, base, code_files)
    except Exception as e:
        result.notes.append(f"Diff guard skipped: {e}")
        return
    result.ran.append("diff-guard")
    if hygiene:
        result.reviews.append((
            "Deleted comments, docstrings or large blocks",
            "\n".join(f"- {h}" for h in hygiene[:20]) +
            "\nRestore what you removed by accident. For each intended removal, say why.",
        ))


def _review_tests(root: Path, tests: List[str], test_cmd: str, result: CheckResult, base: str, timeout: int) -> None:
    try:
        from discipline import prove_tests
        status, detail = prove_tests(root, base, tests, test_cmd, state_dir(root), timeout)
    except Exception as e:
        result.notes.append(f"Test proof skipped: {e}")
        return
    result.ran.append("prove-tests")
    if status == "unproved":
        result.reviews.append((
            "Your tests pass without your change",
            detail + "\nChanged tests:\n" + "\n".join(f"- {t}" for t in tests[:15]) +
            "\nA test for a fix or a feature must fail on the old code. Make the test check the "
            "behaviour you changed (RED first). Only for a pure refactor is a passing test correct: "
            "then say so in your answer.",
        ))
    elif status == "proved":
        result.notes.append(detail)
    else:
        result.notes.append(f"Test proof skipped: {detail}")


def run_visual_step(root: Path, code_files: List[str], cfg: Dict[str, Any], result: CheckResult, base: str = "") -> None:
    try:
        from visual_gate import frontend_files, run_visual_gate, visual_config
        fe = frontend_files(code_files)
        vcfg = visual_config(cfg)
        if not fe:
            return
        if vcfg is None:
            result.notes.append("Visual QA turned off for this project.")
            return
        outcome = run_visual_gate(root, fe, vcfg, state_dir(root) / "visual", base=base)
        if outcome.ran:
            result.ran.append("visual-qa")
        result.notes.extend(outcome.notes)
        for title, detail in outcome.failures:
            result.fail(title, detail)
        for title, detail in outcome.review:
            result.reviews.append((title, _shorten(detail, 4000)))
    except Exception as e:
        result.fail("Visual QA step crashed", f"{e}\n{traceback.format_exc(limit=3)}")


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def format_report(result: CheckResult, files: List[str]) -> str:
    lines = [
        "[Antigravity Stop Gate] The task is NOT complete. The automatic checks failed on "
        f"{len(files)} changed file(s). Fix every problem below, then finish again. "
        "Do not disable, skip or weaken checks or tests.",
        "",
    ]
    for title, detail in result.failures:
        lines.append(f"## {title}")
        lines.append(detail)
        lines.append("")
    for title, detail in result.reviews:
        lines.append(f"## {title}")
        lines.append(detail)
        lines.append("")
    lines.append(f"Re-run all checks yourself with: {self_command('check')}")
    text = "\n".join(lines)
    if len(text) > MAX_REASON_CHARS:
        text = text[: MAX_REASON_CHARS - 200] + "\n[... report cut ...]\n" + lines[-1]
    return text


def format_review(result: CheckResult) -> str:
    lines = [
        "[Antigravity Stop Gate] All checks pass, but parts of your change need a second look. "
        "Review each point below before you finish: this is required once for these changes.",
        "",
    ]
    for title, detail in result.reviews:
        lines.append(f"## {title}")
        lines.append(detail)
        lines.append("")
    lines.append("When the changes are what you intended, finish again. If you edit files, the checks run again.")
    text = "\n".join(lines)
    if len(text) > MAX_REASON_CHARS:
        text = text[: MAX_REASON_CHARS - 200] + "\n[... report cut ...]\n" + lines[-1]
    return text


# -------------------------------------------------------------------- handlers

def ensure_session(root: Path, state: Dict[str, Any], payload: Dict[str, Any]) -> bool:
    """Remember the commit a conversation started from. Returns True if state changed."""
    sessions = state.get("sessions", {})
    conv = str(payload.get("conversationId") or "default")
    if conv in sessions:
        return False
    sessions[conv] = {"base": git_head(root), "t": time.time()}
    state["sessions"] = _trim_dict(sessions, 30)
    return True


def handle_session_start(payload: Dict[str, Any]) -> Dict[str, Any]:
    root = git_root(workspace_of(payload))
    if root:
        state = load_state(root)
        if ensure_session(root, state, payload):
            save_state(root, state)
    return {}


def handle_pre_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not env_flag("AGY_PRE_TOOL_GUARD", True):
        return {"decision": "allow"}
    from pre_tool_guard import inspect_tool_call
    tool = payload.get("toolCall") or {}
    name = tool.get("name", "") if isinstance(tool, dict) else ""
    args = tool.get("args", {}) if isinstance(tool, dict) else {}
    allowed, reason = inspect_tool_call(name, args if isinstance(args, dict) else {})
    if not allowed:
        return {"decision": "deny", "reason": f"[Antigravity Pre-Tool Guard] {reason}"}
    unread = unread_edit_target(payload, name)
    if unread:
        return {"decision": "deny", "reason": (
            f"[Antigravity Pre-Tool Guard] You are editing {unread} but you have not opened it in this "
            "conversation. Read the file first (view_file), at least the part you change and its callers. "
            "Then make the edit again.")}
    return {"decision": "allow"}


# ------------------------------------------------------------ read before write

READ_TOOL_NAMES = {"view_file", "view_file_outline", "view_code_item", "grep_search",
                   "find_by_name", "list_dir", "codebase_search"}
EDIT_TOOLS = ("replace_file_content", "multi_replace_file_content")
PATH_TOKEN_RE = re.compile(r"[A-Za-z]:[\\/][^\s\"'<>|*?]+|[^\s\"'<>|*?:,()\[\]{}]+\.[A-Za-z0-9]{1,8}")
MAX_SEEN_PATHS = 600


def _norm(p: Path) -> str:
    s = str(p)
    return s.lower() if os.name == "nt" else s


def _paths_in(payload: Dict[str, Any], ws: Path) -> List[str]:
    """Existing files mentioned anywhere in a tool call or its result."""
    try:
        text = json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        return []
    text = text.replace("\\\\", "\\")  # JSON-escaped Windows separators
    found: List[str] = []
    for tok in PATH_TOKEN_RE.findall(text)[:400]:
        tok = tok.strip(".;")
        cand = Path(tok).expanduser()
        if not cand.is_absolute():
            cand = ws / cand
        try:
            if cand.is_file():
                found.append(_norm(cand.resolve()))
        except (OSError, ValueError):
            continue
    return found


def record_seen(payload: Dict[str, Any]) -> None:
    """PostToolUse: remember which files agy has seen in this conversation."""
    tool = payload.get("toolCall") or {}
    name = tool.get("name", "") if isinstance(tool, dict) else ""
    ws = workspace_of(payload)
    root = git_root(ws)
    if root is None:
        return
    paths = _paths_in(payload, ws)
    state = load_state(root)
    seen = state.get("seen", {})
    conv = str(payload.get("conversationId") or "default")
    entry = seen.get(conv) or {"paths": [], "reads": 0}
    known = set(entry.get("paths", []))
    for p in paths:
        if p not in known:
            entry["paths"].append(p)
            known.add(p)
    entry["paths"] = entry["paths"][-MAX_SEEN_PATHS:]
    if name in READ_TOOL_NAMES:
        entry["reads"] = int(entry.get("reads", 0)) + 1  # proof that read tools reach this hook
    entry["t"] = time.time()
    seen[conv] = entry
    state["seen"] = _trim_dict(seen, 30)
    save_state(root, state)


def unread_edit_target(payload: Dict[str, Any], name: str) -> str:
    """The file an edit targets when agy never saw it in this conversation, else ''.
    Fails open: no verdict until a read tool has reached PostToolUse at least once."""
    if not env_flag("AGY_READ_BEFORE_WRITE", True):
        return ""
    if name not in EDIT_TOOLS and name != "write_to_file":
        return ""
    path = _target_file(payload)
    if path is None or not path.is_file():
        return ""  # a new file needs no reading
    if name == "write_to_file" and path.stat().st_size == 0:
        return ""
    root = git_root(path.parent)
    if root is None:
        return ""
    if load_project_config(root).get("read_before_write", True) is False:
        return ""
    entry = (load_state(root).get("seen") or {}).get(str(payload.get("conversationId") or "default")) or {}
    if int(entry.get("reads", 0)) < 1:
        return ""
    if _norm(path) in set(entry.get("paths", [])):
        return ""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _target_file(payload: Dict[str, Any]) -> Optional[Path]:
    try:
        from validator_core import resolve_target_file
        target = resolve_target_file(payload)
    except Exception:
        target = ""
    if not target:
        return None
    p = Path(target).expanduser()
    if not p.is_absolute():
        p = workspace_of(payload) / p
    return p.resolve()


def handle_post_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        record_seen(payload)
    except Exception as err:  # never break the tool flow for bookkeeping
        logger.debug("record_seen failed: %s", err)
    if not env_flag("AGY_AUTO_DEBUG", True):
        return {}
    tool = payload.get("toolCall") or {}
    if not isinstance(tool, dict) or tool.get("name") not in FILE_WRITE_TOOLS:
        return {}
    path = _target_file(payload)
    if not path or not path.is_file() or not is_code(path.name):
        return {}
    from validator_core import validate_code_file
    errors = validate_code_file(path) or []
    root = project_root(path.parent)
    state = load_state(root)
    diags = state.get("diagnostics", {})
    if errors:
        diags[str(path)] = {"errors": errors[:10], "t": time.time()}
    else:
        diags.pop(str(path), None)
    state["diagnostics"] = _trim_dict(diags, 50)
    save_state(root, state)
    return {}


def handle_pre_invocation(payload: Dict[str, Any]) -> Dict[str, Any]:
    ws = workspace_of(payload)
    root = project_root(ws)
    state = load_state(root)
    msgs: List[str] = []
    if git_root(root):
        # Fallback when SessionStart did not fire: the first model call records the base.
        changed = ensure_session(root, state, payload)
        guide = guidance_messages(root, state, payload)
        if changed or guide:
            save_state(root, state)
        msgs = guide
    diags = state.get("diagnostics", {})
    if not diags:
        return {"injectSteps": [{"ephemeralMessage": m} for m in msgs]} if msgs else {}
    from validator_core import validate_code_file
    open_issues: List[str] = []
    for path_str in list(diags):
        p = Path(path_str)
        errors = validate_code_file(p) if p.is_file() else []
        if errors:
            diags[path_str]["errors"] = errors[:10]
            open_issues.append(f"{path_str}:\n  " + "\n  ".join(errors[:5]))
        else:
            diags.pop(path_str, None)
    state["diagnostics"] = diags
    save_state(root, state)
    if open_issues:
        msgs.insert(0, _shorten(
            "[Antigravity Auto-Debug] Your last edit left syntax errors. Fix them before anything else:\n"
            + "\n".join(open_issues), 3000))
    return {"injectSteps": [{"ephemeralMessage": m} for m in msgs]} if msgs else {}


def guidance_messages(root: Path, state: Dict[str, Any], payload: Dict[str, Any]) -> List[str]:
    """Guided start on the first model call, then each language's rules the first time
    a file of that language changes. Updates the session in `state`."""
    conv = str(payload.get("conversationId") or "default")
    sess = (state.get("sessions") or {}).get(conv)
    if not isinstance(sess, dict):
        return []
    cfg = load_project_config(root)
    msgs: List[str] = []
    try:
        from guidance import rules_for, start_message
        if not sess.get("guided"):
            sess["guided"] = True
            if env_flag("AGY_GUIDED_START", True):
                cfg_start = dict(cfg, criteria=criteria_enabled(cfg))
                text = start_message(root, cfg_start)
                if text:
                    msgs.append(text)
        if cfg.get("language_rules", True):
            injected = list(sess.get("rules") or [])
            for name, text in rules_for(root, changed_files(root, sess.get("base", "")), injected):
                msgs.append(text)
                injected.append(name)
            if injected:
                sess["rules"] = injected
    except Exception as err:  # guidance is a help: never break the model call
        logger.debug("Guidance failed: %s", err)
    return msgs


def criteria_enabled(cfg: Dict[str, Any]) -> bool:
    return bool(cfg.get("criteria", True)) and env_flag("AGY_CRITERIA", True)


def apply_criteria(root: Path, cfg: Dict[str, Any], result: CheckResult, session_start: float) -> None:
    if not criteria_enabled(cfg):
        return
    try:
        from guidance import check_criteria
        failures, reviews = check_criteria(root, {"criteria": True}, session_start)
    except Exception as e:
        result.notes.append(f"Criteria check skipped: {e}")
        return
    result.ran.append("criteria")
    for title, detail in failures:
        result.fail(title, detail)
    result.reviews.extend(reviews)


def apply_second_opinion(root: Path, cfg: Dict[str, Any], files: List[str], base: str, result: CheckResult) -> None:
    """A stronger model reviews the diff once everything else passes (opt-in, needs an API key)."""
    if not env_flag("AGY_SECOND_OPINION", True):
        return
    try:
        from second_opinion import format_findings, review, settings
        conf = settings(cfg)
        if conf is None:
            return
        from guidance import criteria_fingerprint
        status, findings, note = review(root, base, files, criteria_fingerprint(root), cfg)
    except Exception as e:
        result.notes.append(f"Second opinion skipped: {e}")
        return
    if note:
        result.notes.append(note)
    if status in ("ok", "issues"):
        result.ran.append("second-opinion")
    if findings:
        result.reviews.append((f"Second opinion: {len(findings)} problem(s)", format_findings(conf["model"], findings)))


def gate_extra(root: Path, cfg: Dict[str, Any]) -> str:
    """Everything besides the changed files that changes the gate's verdict."""
    extra = json.dumps(cfg, sort_keys=True)
    if criteria_enabled(cfg):
        from guidance import criteria_fingerprint
        extra += "\0" + criteria_fingerprint(root)
    return extra


def evaluate_stop(payload: Dict[str, Any]) -> Dict[str, Any]:
    if env_flag("AGY_STOP_GATE_DISABLE", False):
        return {"decision": "allow"}
    reason = str(payload.get("terminationReason") or "")
    if reason in NON_GATED_TERMINATIONS:
        return {"decision": "allow"}

    ws = workspace_of(payload)
    root = git_root(ws)
    if root is None:
        # Without git we cannot know what changed; nothing to gate.
        return {"decision": "allow"}

    state = load_state(root)
    conv = str(payload.get("conversationId") or "default")
    sess = state.get("sessions", {}).get(conv) or {}
    base = sess.get("base", "")
    files = changed_files(root, base)
    if not any(is_code(f) for f in files):
        return {"decision": "allow"}

    cfg = load_project_config(root)
    extra = gate_extra(root, cfg)
    fp = fingerprint(root, files, extra)
    cache = state.get("checks", {})
    cached = cache.get(fp)
    if cached and cached.get("ok"):
        return {"decision": "allow"}

    t0 = time.time()

    def log(verdict: str, result: Optional[CheckResult] = None, why: str = "") -> None:
        log_verdict(root, conv, verdict, files, t0, result, why)

    blocks = state.get("blocks", {})
    count = int((blocks.get(fp) or {}).get("n", 0))
    max_blocks = int(os.environ.get("AGY_STOP_GATE_MAX_BLOCKS", "4"))
    if count >= max_blocks:
        # The agent stopped repeatedly without changing anything: stop looping,
        # but leave a trace the statusline and the next session can show.
        log("gave_up", why="block limit")
        return _give_up(root, state, fp, files, "block limit reached without progress")

    if cached and not cached.get("ok") and cached.get("report"):
        if ((state.get("loops") or {}).get(conv) or {}).get("escalated"):
            log("gave_up", why="stuck")
            return _give_up(root, state, fp, files, "stuck on the same failure; agy was told to ask the user")
        report = cached["report"]
        log("block", why="unchanged")
    else:
        result = run_checks(root, files, cfg, base=base)
        apply_criteria(root, cfg, result, float(sess.get("t") or 0))
        if result.ok:
            apply_second_opinion(root, cfg, files, base, result)
        if result.ok and result.reviews:
            # Checks pass, but the UI changed: give agy one turn with the before/after images.
            # The next stop on the same content is allowed.
            cache[fp] = {"ok": True, "t": time.time()}
            state["checks"] = _trim_dict(cache, 20)
            state.pop("gave_up", None)
            reset_loop(state, conv)
            save_state(root, state)
            log("review", result)
            return {"decision": "continue", "reason": format_review(result)}
        if result.ok:
            cache[fp] = {"ok": True, "t": time.time()}
            # Test runs may touch tracked files (snapshots, lock files): remember both states.
            files_after = changed_files(root, base)
            cache[fingerprint(root, files_after, extra)] = {"ok": True, "t": time.time()}
            state["checks"] = _trim_dict(cache, 20)
            state.pop("gave_up", None)
            reset_loop(state, conv)
            save_state(root, state)
            log("pass", result)
            return {"decision": "allow"}
        report = format_report(result, files)
        report, stuck = loop_breaker(state, conv, result, report)
        if stuck:
            log("gave_up", result, why="stuck")
            return _give_up(root, state, fp, files, "stuck on the same failure; agy was told to ask the user")
        cache[fp] = {"ok": False, "report": report, "t": time.time()}
        state["checks"] = _trim_dict(cache, 20)
        log("block", result)

    blocks[fp] = {"n": count + 1, "t": time.time()}
    state["blocks"] = _trim_dict(blocks, 20)
    save_state(root, state)
    return {"decision": "continue", "reason": report}


def log_verdict(root: Path, conv: str, verdict: str, files: List[str], t0: float,
                result: Optional[CheckResult] = None, why: str = "") -> None:
    """One line per gate verdict in <state-dir>/gate-log.jsonl, for `agy_hook.py stats`."""
    entry: Dict[str, Any] = {"t": round(time.time(), 1), "conv": conv, "verdict": verdict,
                             "files": len(files), "seconds": round(time.time() - t0, 1)}
    if why:
        entry["why"] = why
    if result is not None:
        entry["ran"] = result.ran
        entry["failures"] = [t for t, _ in result.failures]
        entry["reviews"] = [t for t, _ in result.reviews]
    try:
        from gate_stats import append
        append(state_dir(root), entry)
    except Exception as err:
        logger.debug("Gate log failed: %s", err)


def _give_up(root: Path, state: Dict[str, Any], fp: str, files: List[str], why: str) -> Dict[str, Any]:
    state["gave_up"] = {"fingerprint": fp, "t": time.time(), "files": files[:20], "why": why}
    save_state(root, state)
    sys.stderr.write(f"[Antigravity Stop Gate] Allowing stop: {why}.\n")
    return {"decision": "allow"}


# ---------------------------------------------------------------- loop breaker
# A fast model that fails the same way twice tends to keep guessing. After 2
# identical failures the gate asks for a debug protocol; at LOOP_ESCALATE it asks
# agy to stop and explain the problem to the user, and the stop after that is allowed.

LOOP_DEBUG_AT = 2
LOOP_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

DEBUG_PROTOCOL = (
    "## Same failure as last time (attempt {n})\n"
    "Your last fix did not change the result. Stop guessing and debug:\n"
    "1. Reproduce: run the failing command alone and read the whole output, not just the last line.\n"
    "2. Read the code path the error points to from the entry point, not just the failing line.\n"
    "3. Write down 2 or 3 hypotheses for the root cause. Check each one with a print, a log or a "
    "small test BEFORE you edit.\n"
    "4. Change one thing, re-run, compare. Revert changes that did not help.\n"
    "Do not weaken the test or the check to get past it."
)

ESCALATION = (
    "[Antigravity Stop Gate] You are stuck: the same failure came back {n} times.\n"
    "Stop changing code. In your answer to the user, write:\n"
    "- the exact failure (command and error),\n"
    "- what you tried each time and what happened,\n"
    "- your best hypothesis for the cause,\n"
    "- what you need from the user (a decision, information, access).\n"
    "Then finish: the gate will let you stop this time.\n\n"
)


def failure_signature(result: CheckResult) -> str:
    """Same checks failing with the same messages, ignoring numbers (lines, timings)."""
    text = "\n".join(f"{t}\n{d[:600]}" for t, d in result.failures)
    return hashlib.sha256(LOOP_NUMBER_RE.sub("N", text).encode("utf-8")).hexdigest()[:16]


def loop_breaker(state: Dict[str, Any], conv: str, result: CheckResult, report: str) -> Tuple[str, bool]:
    """Returns (report, stuck). `stuck` means agy was already told to ask for help."""
    loops = state.get("loops", {})
    sig = failure_signature(result)
    prev = loops.get(conv) or {}
    if prev.get("sig") == sig:
        if prev.get("escalated"):
            return report, True
        n = int(prev.get("n", 1)) + 1
    else:
        n = 1
    escalate_at = max(LOOP_DEBUG_AT + 1, int(os.environ.get("AGY_LOOP_ESCALATE", "4")))
    entry = {"sig": sig, "n": n, "t": time.time()}
    if n >= escalate_at:
        entry["escalated"] = True
        report = ESCALATION.format(n=n) + report
    elif n >= LOOP_DEBUG_AT:
        report = report.rstrip() + "\n\n" + DEBUG_PROTOCOL.format(n=n)
    loops[conv] = entry
    state["loops"] = _trim_dict(loops, 30)
    return report, False


def reset_loop(state: Dict[str, Any], conv: str) -> None:
    (state.get("loops") or {}).pop(conv, None)


def handle_stop(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return evaluate_stop(payload)
    except Exception as e:
        # Fail closed, but bounded: count internal errors like normal blocks.
        try:
            root = project_root(workspace_of(payload))
            state = load_state(root)
            n = int(state.get("internal_errors", 0)) + 1
            state["internal_errors"] = n
            save_state(root, state)
            if n > int(os.environ.get("AGY_STOP_GATE_MAX_BLOCKS", "4")):
                state["internal_errors"] = 0
                save_state(root, state)
                return {"decision": "allow"}
        except Exception as err:
            logger.debug("Failed updating stop gate internal errors: %s", err)
        return {
            "decision": "continue",
            "reason": (
                "[Antigravity Stop Gate] The verification gate crashed, so the work is unverified. "
                f"Run the checks by hand and report the result: {self_command('check')}\n"
                f"Error: {e}"
            ),
        }


# --------------------------------------------------------------------- CLI

def cli_check(target: str, visual: bool = True) -> int:
    ws = Path(target or ".").expanduser().resolve()
    root = git_root(ws)
    if root is None:
        print(f"Not a git repository: {ws}")
        return 2
    state = load_state(root)
    files = changed_files(root, "")
    cfg = load_project_config(root)
    print(f"Project: {root}")
    print(f"Changed files ({len(files)}): " + (", ".join(files[:20]) or "none"))
    # Compare the UI against HEAD: the work-tree changes are what is being checked.
    result = run_checks(root, files, cfg, visual=visual, base="HEAD")
    if any(is_code(f) for f in files):
        apply_criteria(root, cfg, result, 0.0)
    for note in result.notes:
        print(f"Note: {note}")
    if result.ok and result.reviews:
        print(format_review(result))
    print(f"Checks run: {', '.join(result.ran) or 'none'}")
    if result.ok and visual:
        fp = fingerprint(root, files, gate_extra(root, cfg))
        cache = state.get("checks", {})
        cache[fp] = {"ok": True, "t": time.time()}
        state["checks"] = _trim_dict(cache, 20)
        save_state(root, state)
    if result.ok:
        print("RESULT: PASS")
        return 0
    print(format_report(result, files))
    print("RESULT: FAIL")
    return 1


def cli_stats(args: List[str]) -> int:
    """agy_hook.py stats [DIR] [--days N] [--json]"""
    days: Optional[int] = None
    rest: List[str] = []
    it = iter(args)
    for a in it:
        if a == "--days":
            days = int(next(it, "0") or 0) or None
        elif a.startswith("--days="):
            days = int(a.split("=", 1)[1] or 0) or None
        elif a != "--json":
            rest.append(a)
    ws = Path(rest[0] if rest else ".").expanduser().resolve()
    root = git_root(ws)
    if root is None:
        print(f"Not a git repository: {ws}")
        return 2
    from gate_stats import cli
    return cli(state_dir(root), days, "--json" in args)


def cli_doctor() -> int:
    """Verify interpreter, installed hooks and the real payload path end to end."""
    import tempfile
    ok = True

    def line(flag: bool, msg: str) -> None:
        nonlocal ok
        ok = ok and flag
        print(("  OK   " if flag else "  FAIL ") + msg)

    print("Antigravity Dev Suite doctor")
    line(sys.version_info >= (3, 9), f"Python {sys.version.split()[0]} at {sys.executable} (needs 3.9+)")
    code, _ = git(["--version"], Path.cwd())
    line(code == 0, "git available")
    try:
        from setup_hooks import hooks_file, installed_status
        st = installed_status()
        line(st["installed"], f"hooks registered in {hooks_file()}")
        line(st["paths_ok"], "hook commands point to existing files")
    except Exception as e:
        line(False, f"hook configuration readable ({e})")

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        git(["init", "-q"], repo)
        git(["-c", "user.email=a@b", "-c", "user.name=agy", "commit", "-q", "--allow-empty", "-m", "init"], repo)
        (repo / "app.py").write_text("def f(:\n", encoding="utf-8")
        payload = {"workspacePaths": [str(repo)], "conversationId": "doctor"}
        handle_session_start(payload)
        post = dict(payload, toolCall={"name": "write_to_file", "args": {"TargetFile": str(repo / "app.py"), "CodeContent": "def f(:\n"}})
        handle_post_tool(post)
        inj = handle_pre_invocation(payload)
        line(bool(inj.get("injectSteps")), "syntax error is fed back to the model (PreInvocation)")
        stop = handle_stop(dict(payload, terminationReason="model_stop", executionNum=1, fullyIdle=True))
        line(stop.get("decision") == "continue", "stop gate blocks a broken change (terminationReason=model_stop)")
        guard = handle_pre_tool(dict(payload, toolCall={"name": "run_command", "args": {"CommandLine": "git commit --no-verify -m x"}}))
        line(guard.get("decision") == "deny", "guard blocks 'git commit --no-verify'")
        dummy_secret = "AKIA" + "ABCDEFGHIJKLMNOP"
        secret = handle_pre_tool(dict(payload, toolCall={"name": "write_to_file", "args": {"TargetFile": "a.py", "CodeContent": f"k='{dummy_secret}'"}}))
        line(secret.get("decision") == "deny", "guard blocks a secret written with write_to_file")
    # Visual QA is optional: report it, but do not fail the doctor for it.
    pw = visual_qa_status()
    print(("  OK   " if pw[0] else "  WARN ") + pw[1])
    print("RESULT: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def visual_qa_status() -> Tuple[bool, str]:
    """Can this interpreter launch headless Chromium through Playwright?"""
    probe = (
        "from playwright.sync_api import sync_playwright\n"
        "with sync_playwright() as p:\n"
        "    b = p.chromium.launch(headless=True, args=['--no-sandbox'])\n"
        "    b.close()\n"
    )
    try:
        res = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                             timeout=60, check=False, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"Playwright Chromium check failed to run ({e})"
    if res.returncode == 0:
        return True, "Playwright + Chromium ready (visual QA of frontend changes)"
    try:
        from visual_gate import install_hint
        hint = install_hint().splitlines()
    except Exception:
        hint = []
    return False, "Playwright/Chromium missing: frontend changes will be blocked until installed.\n         " + "\n         ".join(hint[1:3])


HANDLERS = {
    "session-start": handle_session_start,
    "pre-tool": handle_pre_tool,
    "post-tool": handle_post_tool,
    "pre-invocation": handle_pre_invocation,
    "stop": handle_stop,
}

SAFE_DEFAULTS = {
    "session-start": {},
    "pre-tool": {"decision": "allow"},
    "post-tool": {},
    "pre-invocation": {},
}


def main(argv: List[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd == "check":
        rest = [a for a in argv[1:] if a != "--no-visual"]
        return cli_check(rest[0] if rest else ".", visual="--no-visual" not in argv[1:])
    if cmd == "doctor":
        return cli_doctor()
    if cmd == "stats":
        return cli_stats(argv[1:])
    handler = HANDLERS.get(cmd)
    if handler is None:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        return 2
    payload = read_payload()
    debug_dump(cmd, payload)
    if cmd == "stop":
        emit(handler(payload))
        return 0
    try:
        emit(handler(payload))
    except Exception as e:
        sys.stderr.write(f"[agy_hook] {cmd} failed: {e}\n")
        emit(SAFE_DEFAULTS[cmd])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
