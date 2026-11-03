#!/usr/bin/env python3
"""Discipline checks of the Stop gate: the habits that separate careful work from fast work.

- `prove_tests`: the new or changed tests must FAIL on the base commit. A test that
  passes with and without the change proves nothing.
- `lint_changed_lines`: ESLint / Ruff findings, only on the lines the change touched,
  so agy never has to clean up a legacy file it did not write.
- `api_changes`: exported symbols removed or with changed signatures.
- `diff_hygiene`: comments and docstrings deleted, large deletions, nesting blow-ups.

The first two run the project's own tools. The last two reuse api_contract_guard.py
and diff_guard.py. The gate turns findings of `prove_tests`, `api_changes` and
`diff_hygiene` into a one-time review (agy must look and answer once); lint
findings on changed lines are failures.

Python 3.9+ standard library only. Works on macOS, Linux and Windows.
"""

from __future__ import annotations

import logging
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from base_worktree import Worktree, git  # noqa: E402

logger = logging.getLogger("discipline")

JS_LINT_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte"}
ESLINT_CONFIGS = (
    "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs", "eslint.config.ts",
    ".eslintrc", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.json", ".eslintrc.yml", ".eslintrc.yaml",
)
RUFF_CONFIGS = ("ruff.toml", ".ruff.toml")
# file:line:col: message  (ESLint "unix" format and Ruff "concise" format)
LINT_LINE_RE = re.compile(r"^(?P<file>.+?):(?P<line>\d+):(?P<col>\d+):\s*(?P<msg>.+)$")
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def resolve_sha(root: Path, base: str) -> str:
    code, out = git(["rev-parse", "--verify", f"{base or 'HEAD'}^{{commit}}"], root)
    lines = out.strip().splitlines()
    return lines[-1] if code == 0 and lines else ""


def run(cmd: str, cwd: Path, timeout: int) -> Tuple[int, str]:
    try:
        res = subprocess.run(  # nosec: project-configured command
            cmd, shell=True, cwd=str(cwd), capture_output=True, text=True,
            timeout=timeout, check=False, encoding="utf-8", errors="replace",
        )
        return res.returncode, (res.stdout or "") + ("\n" + res.stderr if res.stderr else "")
    except subprocess.TimeoutExpired:
        return 124, f"Timed out after {timeout}s: {cmd}"
    except OSError as e:
        return 127, f"Cannot run '{cmd}': {e}"


# --------------------------------------------------------------- prove tests

def _quote(path: str) -> str:
    if sys.platform == "win32":
        return f'"{path}"' if " " in path else path
    return shlex.quote(path)


def scoped_test_command(test_cmd: str, test_files: List[str]) -> str:
    """Restrict the test command to the changed test files when the runner allows it."""
    files = " ".join(_quote(f) for f in test_files)
    low = test_cmd.lower()
    if re.search(r"(^|\s|/)(pytest|py\.test)(\s|$)|-m\s+pytest", low):
        return f"{test_cmd} {files}"
    if re.search(r"\b(vitest|jest)\b", low):
        return f"{test_cmd} {files}"
    if re.search(r"\b(npm|pnpm|yarn)\b.*\btest\b", low):
        return f"{test_cmd} -- {files}"
    return test_cmd


def prove_tests(root: Path, base: str, test_files: List[str], test_cmd: str,
                out_dir: Path, timeout: int) -> Tuple[str, str]:
    """Run the changed tests against the base commit's production code.

    Returns ("proved", detail) when they fail there, ("unproved", detail) when they
    pass there, or ("skipped", reason)."""
    sha = resolve_sha(root, base)
    if not sha or not test_files or not test_cmd:
        return "skipped", "no base commit, test files or test command"
    try:
        with Worktree(root, sha, out_dir / "prove-worktree") as wt:
            for rel in test_files:
                src, dst = root / rel, wt.path / rel
                if not src.is_file():
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(str(src), str(dst))
            cmd = scoped_test_command(test_cmd, test_files)
            code, out = run(cmd, wt.path, timeout)
    except (RuntimeError, OSError) as e:
        return "skipped", str(e)
    if code == 124:
        return "skipped", out
    if code == 0:
        return "unproved", f"`{cmd}` passed on the base commit {sha[:10]}, before your change."
    return "proved", f"`{cmd}` fails on the base commit {sha[:10]} (exit {code}), as it should."


# ------------------------------------------------------------- changed lines

def changed_lines(root: Path, base: str, rel: str) -> Optional[Set[int]]:
    """Lines of `rel` added or modified since `base`. None means every line (new file)."""
    code, out = git(["diff", "-U0", "--no-color", base or "HEAD", "--", rel], root)
    if code != 0:
        return None
    if not out.strip():
        code2, tracked = git(["ls-files", "--error-unmatch", rel], root)
        return set() if code2 == 0 else None  # untracked file: every line is new
    lines: Set[int] = set()
    for line in out.splitlines():
        if line.startswith("new file mode"):
            return None
        m = HUNK_RE.match(line)
        if m:
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) is not None else 1
            lines.update(range(start, start + count))
    return lines


def _has_ruff_config(root: Path) -> bool:
    if any((root / c).is_file() for c in RUFF_CONFIGS):
        return True
    try:
        return "[tool.ruff" in (root / "pyproject.toml").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def _local_bin(root: Path, name: str) -> Optional[Path]:
    for cand in (root / "node_modules" / ".bin" / name, root / "node_modules" / ".bin" / f"{name}.cmd"):
        if cand.is_file():
            return cand
    return None


def linters_for(root: Path, files: List[str]) -> List[Tuple[str, str]]:
    """(name, command) for each linter the project already uses, scoped to `files`."""
    out: List[Tuple[str, str]] = []
    js = [f for f in files if Path(f).suffix.lower() in JS_LINT_EXTENSIONS]
    if js and _local_bin(root, "eslint") and any((root / c).is_file() for c in ESLINT_CONFIGS):
        out.append(("eslint", "npx --no-install eslint --format unix " + " ".join(_quote(f) for f in js)))
    py = [f for f in files if f.endswith((".py", ".pyi"))]
    if py and _has_ruff_config(root):
        ruff = shutil.which("ruff")
        base_cmd = _quote(ruff) if ruff else f"{_quote(sys.executable)} -m ruff"
        out.append(("ruff", f"{base_cmd} check --output-format concise --no-fix " + " ".join(_quote(f) for f in py)))
    return out


def lint_changed_lines(root: Path, base: str, files: List[str], timeout: int) -> Tuple[List[str], List[str]]:
    """Run the project's linters on the changed files and keep only findings on changed lines.
    Returns (findings, linters_run)."""
    findings: List[str] = []
    ran: List[str] = []
    cache: Dict[str, Optional[Set[int]]] = {}
    for name, cmd in linters_for(root, files):
        code, out = run(cmd, root, timeout)
        if code in (124, 127) or "No module named ruff" in out:
            continue  # the tool is not really available: not the agent's fault
        ran.append(name)
        for raw in out.splitlines():
            m = LINT_LINE_RE.match(raw.strip())
            if not m:
                continue
            path = Path(m.group("file"))
            try:
                rel = (path if path.is_absolute() else (root / path)).resolve().relative_to(root.resolve()).as_posix()
            except (ValueError, OSError):
                continue
            if rel not in cache:
                cache[rel] = changed_lines(root, base, rel)
            lines = cache[rel]
            if lines is None or int(m.group("line")) in lines:
                findings.append(f"{rel}:{m.group('line')}:{m.group('col')}: {m.group('msg')} ({name})")
    return findings, ran


# ------------------------------------------------------------- API and hygiene

def api_changes(root: Path, base: str, files: List[str]) -> List[str]:
    from api_contract_guard import audit_api_contract_drift
    report = audit_api_contract_drift(root, base_ref=base or "HEAD",
                                      specific_files=[root / f for f in files])
    return [str(v) for v in report.get("violations", [])]


def diff_hygiene(root: Path, base: str, files: List[str]) -> List[str]:
    from diff_guard import audit_diff_guard
    report = audit_diff_guard(root, specific_files=[root / f for f in files], base_ref=base or "HEAD")
    return [str(v) for v in report.get("violations", [])]


# ------------------------------------------------------------ changed-line coverage
# The test run is instrumented when the project's runner supports it, and the gate
# reports the changed production lines that no test executed. A missing coverage
# plugin is never the agent's fault: the plain command runs instead.

COVERAGE_MISSING_RE = re.compile(
    r"unrecognized arguments: --cov|no such option: --cov|Failed to load (?:custom )?coverage provider|"
    r"Cannot find (?:dependency|package|module) ['\"]?@vitest/coverage|MISSING DEPENDENCY.*coverage|"
    r"Unknown option [\"']?--?coverage",
    re.IGNORECASE,
)


def _js_runner(root: Path, cmd: str) -> str:
    low = cmd.lower()
    for name in ("vitest", "jest"):
        if re.search(rf"\b{name}\b", low):
            return name
    if re.search(r"\b(npm|pnpm|yarn)\b.*\btest\b", low):
        try:
            import json
            pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
            script = str((pkg.get("scripts") or {}).get("test", "")).lower()
        except (OSError, ValueError, AttributeError):
            return ""
        for name in ("vitest", "jest"):
            if re.search(rf"\b{name}\b", script):
                return f"npm-{name}"
    return ""


def coverage_command(root: Path, test_cmd: str, out_dir: Path) -> Optional[Tuple[str, str, Path]]:
    """(instrumented command, report kind, report path), or None when the runner is unknown."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if re.search(r"(^|\s|/)(pytest|py\.test)(\s|$)|-m\s+pytest", test_cmd.lower()):
        report = out_dir / "coverage.json"
        return (f"{test_cmd} --cov=. --cov-report=json:{_quote(str(report))}", "coverage.py", report)
    runner = _js_runner(root, test_cmd)
    report = out_dir / "coverage-final.json"
    d = _quote(str(out_dir))
    if runner.endswith("vitest"):
        flags = f"--coverage.enabled=true --coverage.reporter=json --coverage.reportsDirectory={d}"
    elif runner.endswith("jest"):
        flags = f"--coverage --coverageReporters=json --coverageDirectory={d}"
    else:
        return None
    sep = " -- " if runner.startswith("npm-") else " "
    return (test_cmd + sep + flags, "istanbul", report)


def coverage_plugin_missing(output: str) -> bool:
    return bool(COVERAGE_MISSING_RE.search(output))


def _rel(root: Path, name: str) -> str:
    p = Path(name)
    try:
        return (p if p.is_absolute() else root / p).resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return ""


def executed_lines(root: Path, kind: str, report: Path) -> Dict[str, Tuple[Set[int], Set[int]]]:
    """rel path -> (executed lines, executable lines never run)."""
    import json
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: Dict[str, Tuple[Set[int], Set[int]]] = {}
    if kind == "coverage.py":
        for name, info in (data.get("files") or {}).items():
            rel = _rel(root, name)
            if rel and isinstance(info, dict):
                out[rel] = (set(info.get("executed_lines") or []), set(info.get("missing_lines") or []))
        return out
    for name, info in data.items():
        rel = _rel(root, (info or {}).get("path") or name) if isinstance(info, dict) else ""
        if not rel:
            continue
        hit: Set[int] = set()
        miss: Set[int] = set()
        smap = info.get("statementMap") or {}
        for sid, count in (info.get("s") or {}).items():
            loc = (smap.get(sid) or {}).get("start") or {}
            if "line" in loc:
                (hit if count else miss).add(int(loc["line"]))
        out[rel] = (hit, miss - hit)
    return out


def _ranges(lines: List[int]) -> str:
    parts: List[str] = []
    start = prev = None
    for n in lines + [None]:  # type: ignore[list-item]
        if n is not None and prev is not None and n == prev + 1:
            prev = n
            continue
        if start is not None:
            parts.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = n
    return ", ".join(parts)


def uncovered_changed_lines(root: Path, base: str, prod: List[str], kind: str, report: Path) -> List[str]:
    """One line per production file whose changed lines no test executed."""
    cov = executed_lines(root, kind, report)
    if not cov:
        return []
    findings: List[str] = []
    for rel in prod:
        if rel not in cov:
            if kind == "coverage.py" and rel.endswith(".py"):
                findings.append(f"{rel}: no test imports this file")
            continue
        _, missing = cov[rel]
        changed = changed_lines(root, base, rel)
        lines = sorted(missing if changed is None else (missing & changed))
        if lines:
            findings.append(f"{rel}: lines {_ranges(lines)}")
    return findings
