#!/usr/bin/env python3
"""Visual QA step of the Stop gate: open the changed UI in Chromium and block on defects.

The gate calls `run_visual_gate()` when the change touches frontend files.
It finds a page to open, runs `visual_qa.py` on it at 1280x800 and 375x667, and
turns JS errors, console errors, failed requests, mobile overflow and WCAG
violations into a gate failure.

Where the page comes from (first match wins):
1. `visual_qa.url` in `.agents/agy.json`. When that server does not answer and
   `visual_qa.dev_command` is set, the gate starts the command, waits for the
   server, and stops it after the check.
2. `visual_qa.dev_command` without a URL: the gate starts it and uses the first
   new local dev port that opens.
3. Changed static HTML files (not server templates): opened directly from disk.
4. A dev server that already runs on a common local port.

Before/after: the gate opens the same pages on the base commit (a detached
`git worktree`, with a `dev_command` that has a `{port}` placeholder for dev servers).
Only defects the base commit did not have block. Pages whose screenshots changed
are listed with before, after and diff images, and agy must review them once.

When none of these works, or Playwright/Chromium is missing, the gate fails with
the exact fix. It never skips in silence. Turn the step off with
`"visual_qa": false` in `.agents/agy.json` or `AGY_VISUAL_QA=0`.

Python 3.9+ standard library only. Works on macOS, Linux and Windows.
"""

from __future__ import annotations

import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

SCRIPTS_DIR = Path(__file__).resolve().parent
VISUAL_QA = SCRIPTS_DIR / "visual_qa.py"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

logger = logging.getLogger("visual_gate")

FRONTEND_EXTENSIONS = {
    ".tsx", ".jsx", ".vue", ".svelte", ".astro",
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
}
STATIC_HTML_EXTENSIONS = {".html", ".htm"}
# Server-side template syntax: such files cannot be opened from disk.
TEMPLATE_SYNTAX_RE = re.compile(r"\{%|\{\{|<%|<\?php|\{#")

DEFAULT_PAGE_TIMEOUT = 90
DEFAULT_STARTUP_TIMEOUT = 90
MAX_PAGES = 8
DEFAULT_DIFF_THRESHOLD = 0.001  # share of pixels that must change before agy has to review


class VisualOutcome:
    """Result of the visual step: failures (title, detail) and notes for the report."""

    def __init__(self) -> None:
        self.failures: List[Tuple[str, str]] = []
        self.review: List[Tuple[str, str]] = []  # not failures: agy must look once, then may finish
        self.notes: List[str] = []
        self.ran = False

    def fail(self, title: str, detail: str) -> None:
        self.failures.append((title, detail))


def _is_test_path(rel: str) -> bool:
    return bool(re.search(r"(^|/)(tests?|__tests__|spec|specs|e2e|stories)/|\.(test|spec|stories)\.[A-Za-z0-9]+$", rel))


def frontend_files(files: List[str]) -> List[str]:
    """Changed files that render in a browser (tests and stories excluded)."""
    return [f for f in files if Path(f).suffix.lower() in FRONTEND_EXTENSIONS and not _is_test_path(f)]


def visual_config(cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The `visual_qa` block of .agents/agy.json, or None when the user turned it off."""
    if os.environ.get("AGY_VISUAL_QA", "").strip().lower() in ("0", "false", "off", "no"):
        return None
    raw = cfg.get("visual_qa", {})
    if raw is False:
        return None
    if isinstance(raw, dict):
        if raw.get("enabled") is False:
            return None
        return raw
    return {}


def _int(val: Any, default: int) -> int:
    try:
        return max(1, int(val))
    except (TypeError, ValueError):
        return default


def _routes(vcfg: Dict[str, Any]) -> List[str]:
    routes = vcfg.get("routes")
    if not isinstance(routes, list) or not routes:
        return ["/"]
    out: List[str] = []
    for r in routes:
        if isinstance(r, str) and r.strip():
            r = r.strip()
            out.append(r if r.startswith("/") else "/" + r)
    return out[:MAX_PAGES] or ["/"]


def _join(base: str, route: str) -> str:
    return base.rstrip("/") + route


def _host_port(url: str) -> Tuple[str, int]:
    p = urlparse(url)
    port = p.port or (443 if p.scheme == "https" else 80)
    return (p.hostname or "localhost"), port


def server_answers(url: str) -> bool:
    from visual_qa import is_http_server_active
    host, port = _host_port(url)
    return is_http_server_active(port, host)


def _candidate_ports() -> List[int]:
    from visual_qa import COMMON_DEV_PORTS
    ports: List[int] = []
    for key in ("PORT", "VITE_PORT", "DEV_PORT", "SERVER_PORT"):
        val = os.environ.get(key, "").strip()
        if val.isdigit():
            ports.append(int(val))
    return ports + [p for p in COMMON_DEV_PORTS if p not in ports]


def _active_ports() -> List[int]:
    from visual_qa import is_http_server_active
    return [p for p in _candidate_ports() if is_http_server_active(p)]


def static_html_targets(root: Path, fe_files: List[str]) -> List[str]:
    """Changed HTML files that a browser can open from disk."""
    out: List[str] = []
    for rel in fe_files:
        if Path(rel).suffix.lower() not in STATIC_HTML_EXTENSIONS:
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if TEMPLATE_SYNTAX_RE.search(text):
            continue
        out.append(str((root / rel).resolve()))
    return out[:MAX_PAGES]


# ------------------------------------------------------------------ dev server

class DevServer:
    """A dev server process started by the gate, stopped with its whole process tree."""

    def __init__(self, command: str, root: Path, log_path: Path) -> None:
        self.command = command
        self.root = root
        self.log_path = log_path
        self.proc: Optional[subprocess.Popen] = None

    def start(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        kwargs: Dict[str, Any] = {}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            kwargs["start_new_session"] = True
        env = dict(os.environ)
        env.setdefault("BROWSER", "none")  # stop CRA/Vite from opening a browser window
        env.setdefault("CI", "1")
        # The child keeps its own copy of the log handle; ours closes right after the spawn.
        with open(self.log_path, "w", encoding="utf-8", errors="replace") as log:
            self.proc = subprocess.Popen(  # nosec: user-configured command from .agents/agy.json
                self.command, shell=True, cwd=str(self.root), stdout=log,
                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env, **kwargs,
            )

    def exited(self) -> bool:
        return self.proc is not None and self.proc.poll() is not None

    def log_tail(self, lines: int = 25) -> str:
        try:
            text = self.log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return "\n".join(text.strip().splitlines()[-lines:])

    def stop(self) -> None:
        proc = self.proc
        if proc is None:
            return
        try:
            if proc.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                   capture_output=True, check=False, timeout=30)
                else:
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                    except (ProcessLookupError, PermissionError):
                        proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    if os.name != "nt":
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except (ProcessLookupError, PermissionError):
                            proc.kill()
                    else:
                        proc.kill()
                    proc.wait(timeout=10)
        except (OSError, subprocess.SubprocessError) as err:
            logger.debug("Dev server stop failed (process may be gone): %s", err)


def _wait_for(predicate, server: DevServer, timeout: int) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        if server.exited():
            return False
        time.sleep(0.5)
    return predicate()


# ---------------------------------------------------------------- page checks

def _slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")
    return (s or "root")[-60:]


def _python_cmd() -> str:
    exe = sys.executable or "python3"
    return f'"{exe}"' if " " in exe else exe


def install_hint() -> str:
    py = _python_cmd()
    return (f"Install Playwright for the interpreter that runs the hooks:\n"
            f"  {py} -m pip install playwright\n"
            f"  {py} -m playwright install chromium\n"
            "Or turn the visual step off for this project with \"visual_qa\": false in .agents/agy.json.")


def inspect_target(target: str, out_dir: Path, timeout: int) -> Dict[str, Any]:
    """Run visual_qa.py in a child process (crash and hang isolation) and parse its JSON."""
    cmd = [sys.executable, str(VISUAL_QA), target, "--output-dir", str(out_dir), "--fail-on-skip"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False,
                             encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return {"status": "ERROR", "warnings": [f"Visual QA timed out after {timeout}s on {target}"]}
    except OSError as e:
        return {"status": "ERROR", "warnings": [f"Cannot run visual_qa.py: {e}"]}
    try:
        data = json.loads(res.stdout)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError as err:
        logger.debug("visual_qa.py printed non-JSON output: %s", err)
    tail = (res.stdout + "\n" + res.stderr).strip()[-1500:]
    return {"status": "ERROR", "warnings": [f"visual_qa.py exit {res.returncode}, unreadable output:\n{tail}"]}


def page_defects(data: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for key, label in (("page_errors", "Page error"), ("console_errors", "Console error"),
                       ("http_errors", "Failed request"), ("a11y_violations", "Accessibility")):
        for item in data.get(key) or []:
            out.append(f"{label}: {item}")
    return out


def _browser_missing(data: Dict[str, Any]) -> bool:
    text = " ".join(str(w) for w in data.get("warnings") or [])
    return data.get("status") == "SKIPPED_DEPENDENCY" or "Executable doesn't exist" in text \
        or "playwright install" in text


# ------------------------------------------------------------------- the step

class Page:
    """One page to inspect. `label` is stable across runs (a route or a project-relative
    file); `target` is what visual_qa.py opens now (a URL or an absolute file path)."""

    def __init__(self, label: str, target: str, route: str = "") -> None:
        self.label = label
        self.target = target
        self.route = route


class Plan:
    """How the current pages were found, and how to rebuild them on the base commit."""

    def __init__(self) -> None:
        self.pages: List[Page] = []
        self.server: Optional[DevServer] = None
        self.kind = ""            # "static" | "url" | "auto"
        self.port_command = ""    # dev_command with a {port} placeholder: baseline possible
        self.routes: List[str] = []


def free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _str(vcfg: Dict[str, Any], key: str) -> str:
    val = vcfg.get(key)
    return val.strip() if isinstance(val, str) else ""


def _url_pages(base: str, routes: List[str]) -> List[Page]:
    return [Page(r, _join(base, r), r) for r in routes]


def _start_and_wait(command: str, cwd: Path, url: str, startup: int, log_path: Path) -> Tuple[Optional[DevServer], str]:
    server = DevServer(command, cwd, log_path)
    server.start()
    if _wait_for(lambda: server_answers(url), server, startup):
        return server, ""
    tail = server.log_tail()
    server.stop()
    return None, f"`{command}` did not answer at {url} within {startup}s.\nLast output:\n{tail}"


def _resolve_plan(root: Path, fe_files: List[str], vcfg: Dict[str, Any],
                  log_path: Path, outcome: VisualOutcome) -> Plan:
    """Pages to open now, and the dev server the gate started (to stop afterwards)."""
    plan = Plan()
    url = _str(vcfg, "url")
    dev_command = _str(vcfg, "dev_command")
    startup = _int(vcfg.get("startup_timeout"), DEFAULT_STARTUP_TIMEOUT)
    routes = _routes(vcfg)
    plan.routes = routes
    if "{port}" in dev_command:
        plan.port_command = dev_command
        if not url:
            url = f"http://localhost:{free_port()}"
        dev_command = dev_command.replace("{port}", str(_host_port(url)[1]))

    if url:
        plan.kind = "url"
        if server_answers(url):
            plan.pages = _url_pages(url, routes)
            return plan
        if not dev_command:
            outcome.fail("Visual QA: dev server not running",
                         f"Nothing answers at {url} (visual_qa.url in .agents/agy.json).\n"
                         "Start the dev server, then finish again. To let the gate start it, ask the user "
                         "to set \"visual_qa\": {\"dev_command\": \"npm run dev -- --port {port}\"} in .agents/agy.json.")
            return plan
        server, err = _start_and_wait(dev_command, root, url, startup, log_path)
        if server is None:
            outcome.fail("Visual QA: dev server did not start", err)
            return plan
        outcome.notes.append(f"Visual QA started `{dev_command}` for {url}.")
        plan.server = server
        plan.pages = _url_pages(url, routes)
        return plan

    if dev_command:
        plan.kind = "url"
        before = set(_active_ports())
        server = DevServer(dev_command, root, log_path)
        server.start()
        found: List[int] = []

        def new_port() -> bool:
            found[:] = [p for p in _active_ports() if p not in before]
            return bool(found)

        if _wait_for(new_port, server, startup):
            base = f"http://localhost:{found[0]}"
            outcome.notes.append(f"Visual QA started `{dev_command}` on {base}.")
            plan.server = server
            plan.pages = _url_pages(base, routes)
            return plan
        tail = server.log_tail()
        server.stop()
        outcome.fail("Visual QA: dev server did not start",
                     f"`{dev_command}` opened no new local port within {startup}s. "
                     "Ask the user to add \"url\" to the visual_qa block in .agents/agy.json, "
                     "or a {port} placeholder to dev_command.\n"
                     f"Last output:\n{tail}")
        return plan

    static = static_html_targets(root, fe_files)
    if static:
        plan.kind = "static"
        for target in static:
            rel = Path(target).resolve().relative_to(root.resolve()).as_posix()
            plan.pages.append(Page(rel, target))
        return plan

    active = _active_ports()
    if active:
        plan.kind = "auto"
        base = f"http://localhost:{active[0]}"
        outcome.notes.append(f"Visual QA used the dev server already running on {base} (auto-detected).")
        plan.pages = _url_pages(base, routes)
        return plan

    outcome.fail(
        "Visual QA could not run: no page to open",
        "You changed frontend files:\n" + "\n".join(f"- {f}" for f in fe_files[:10]) +
        "\nNo dev server is running and no static HTML page changed.\n"
        "Start the project's dev server (for example `npm run dev`) and finish again.\n"
        "To make this automatic, ask the user to add to .agents/agy.json:\n"
        '  "visual_qa": {"dev_command": "npm run dev -- --port {port}", "routes": ["/"]}\n'
        "or \"visual_qa\": false when the project has no UI to check.",
    )
    return plan


# ------------------------------------------------------------------- baseline

ENV_FILES = (".env", ".env.local", ".env.development", ".env.development.local")
_NORMALIZE_RE = re.compile(r"https?://[^/\s]+|file://\S+?(?=[\s:]|$)|:\d+:\d+|\b\d+(\.\d+)?(px|ms|s)?\b")


def _normalize(defect: str) -> str:
    """Make a defect comparable across runs: drop origins, file URLs, positions and numbers."""
    return _NORMALIZE_RE.sub("#", defect)


def new_defects(current: List[str], baseline: List[str]) -> List[str]:
    """Defects of the current page that the base commit did not have (count-aware)."""
    remaining: Dict[str, int] = {}
    for d in baseline:
        key = _normalize(d)
        remaining[key] = remaining.get(key, 0) + 1
    out: List[str] = []
    for d in current:
        key = _normalize(d)
        if remaining.get(key, 0) > 0:
            remaining[key] -= 1
        else:
            out.append(d)
    return out


def _git(args: List[str], cwd: Path, timeout: int = 120) -> Tuple[int, str]:
    try:
        res = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True,
                             timeout=timeout, check=False, encoding="utf-8", errors="replace")
        return res.returncode, (res.stdout or "") + (res.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def _link_dir(target: Path, link: Path) -> bool:
    """Directory link that works without admin rights: symlink on POSIX, junction on Windows."""
    try:
        if os.name == "nt":
            res = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                                 capture_output=True, check=False, timeout=30)
            return res.returncode == 0
        os.symlink(str(target), str(link), target_is_directory=True)
        return True
    except (OSError, subprocess.SubprocessError) as err:
        logger.debug("Cannot link %s: %s", link, err)
        return False


def _unlink_dir(link: Path) -> None:
    """Remove a directory link without touching what it points to."""
    try:
        if os.name == "nt":
            os.rmdir(str(link))  # removes a junction, never its target
        elif link.is_symlink():
            link.unlink()
    except OSError as err:
        logger.debug("Cannot remove link %s: %s", link, err)


class Worktree:
    """Detached checkout of the base commit, with the project's node_modules and .env files."""

    def __init__(self, root: Path, base: str, path: Path) -> None:
        self.root = root
        self.base = base
        self.path = path
        self.links: List[Path] = []

    def __enter__(self) -> "Worktree":
        self.remove()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        code, out = _git(["worktree", "add", "--detach", "--force", str(self.path), self.base], self.root)
        if code != 0:
            raise RuntimeError(f"git worktree add failed: {out.strip()[-500:]}")
        nm = self.root / "node_modules"
        if nm.is_dir() and not (self.path / "node_modules").exists():
            if _link_dir(nm, self.path / "node_modules"):
                self.links.append(self.path / "node_modules")
        for name in ENV_FILES:
            src = self.root / name
            dst = self.path / name
            if src.is_file() and not dst.exists():
                try:
                    dst.write_bytes(src.read_bytes())
                except OSError as err:
                    logger.debug("Cannot copy %s: %s", name, err)
        return self

    def __exit__(self, *exc: Any) -> None:
        self.remove()

    def remove(self) -> None:
        for link in self.links:
            _unlink_dir(link)
        self.links = []
        if self.path.exists():
            # A link left by an interrupted run: remove the link itself first, so that
            # "git worktree remove" can never delete the project's real node_modules.
            _unlink_dir(self.path / "node_modules")
            _git(["worktree", "remove", "--force", str(self.path)], self.root)
        _git(["worktree", "prune"], self.root)


def _baseline_cache(out_base: Path, sha: str) -> Path:
    return out_base / "baseline" / sha[:12]


def _load_cached(cache: Path, label: str) -> Optional[Dict[str, Any]]:
    f = cache / _slug(label) / "result.json"
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _store(cache: Path, label: str, data: Dict[str, Any]) -> None:
    d = cache / _slug(label)
    try:
        d.mkdir(parents=True, exist_ok=True)
        (d / "result.json").write_text(json.dumps(data), encoding="utf-8")
    except OSError as err:
        logger.debug("Cannot store baseline result: %s", err)


def capture_baseline(root: Path, base: str, plan: Plan, vcfg: Dict[str, Any],
                     out_base: Path, outcome: VisualOutcome) -> Dict[str, Dict[str, Any]]:
    """Inspect the same pages on the base commit. Returns {label: visual_qa result};
    a label missing from the result means the page did not exist at the base commit."""
    if plan.kind not in ("static", "url") or (plan.kind == "url" and not plan.port_command):
        outcome.notes.append(
            "No before/after comparison: give dev_command a {port} placeholder in .agents/agy.json "
            "so the gate can run the base commit on its own port.")
        return {}
    code, sha = _git(["rev-parse", "--verify", f"{base or 'HEAD'}^{{commit}}"], root)
    sha = sha.strip().splitlines()[-1] if code == 0 and sha.strip() else ""
    if not sha:
        outcome.notes.append("No before/after comparison: the base commit is unknown.")
        return {}
    cache = _baseline_cache(out_base, sha)
    results: Dict[str, Dict[str, Any]] = {}
    missing = []
    for page in plan.pages:
        cached = _load_cached(cache, page.label)
        if cached is not None:
            if cached.get("status") != "ABSENT":
                results[page.label] = cached
        else:
            missing.append(page)
    if not missing:
        return results

    timeout = _int(vcfg.get("timeout"), DEFAULT_PAGE_TIMEOUT)
    startup = _int(vcfg.get("startup_timeout"), DEFAULT_STARTUP_TIMEOUT)
    try:
        with Worktree(root, sha, out_base / "baseline-worktree") as wt:
            server: Optional[DevServer] = None
            base_url = ""
            try:
                if plan.kind == "url":
                    port = free_port()
                    base_url = f"http://localhost:{port}"
                    command = plan.port_command.replace("{port}", str(port))
                    server, err = _start_and_wait(command, wt.path, base_url, startup,
                                                  out_base / "baseline-server.log")
                    if server is None:
                        outcome.notes.append("No before/after comparison: the base commit did not start.\n" + err)
                        return results
                for page in missing:
                    if plan.kind == "static":
                        target = wt.path / page.label
                        if not target.is_file():
                            _store(cache, page.label, {"status": "ABSENT"})
                            continue
                        target_str = str(target)
                    else:
                        target_str = _join(base_url, page.route or "/")
                    data = inspect_target(target_str, cache / _slug(page.label), timeout)
                    if data.get("status") in ("SUCCESS", "FAIL"):
                        _store(cache, page.label, data)
                        results[page.label] = data
            finally:
                if server is not None:
                    server.stop()
    except RuntimeError as e:
        outcome.notes.append(f"No before/after comparison: {e}")
    return results


def screenshot_diff(before: str, after: str, out: Path, timeout: int) -> Optional[Dict[str, Any]]:
    cmd = [sys.executable, str(VISUAL_QA), "--diff", before, after, "--diff-out", str(out)]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False,
                             encoding="utf-8", errors="replace")
        data = json.loads(res.stdout)
        return data if isinstance(data, dict) and data.get("status") == "OK" else None
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as err:
        logger.debug("Screenshot diff failed: %s", err)
        return None


def _float(val: Any, default: float) -> float:
    try:
        return max(0.0, float(val))
    except (TypeError, ValueError):
        return default


def run_visual_gate(root: Path, fe_files: List[str], vcfg: Dict[str, Any], out_base: Path,
                    base: str = "") -> VisualOutcome:
    outcome = VisualOutcome()
    page_timeout = _int(vcfg.get("timeout"), DEFAULT_PAGE_TIMEOUT)
    threshold = _float(vcfg.get("diff_threshold"), DEFAULT_DIFF_THRESHOLD)
    plan = _resolve_plan(root, fe_files, vcfg, out_base / "dev-server.log", outcome)
    current: Dict[str, Dict[str, Any]] = {}
    try:
        if not plan.pages:
            return outcome
        outcome.ran = True
        for page in plan.pages:
            data = inspect_target(page.target, out_base / "current" / _slug(page.label), page_timeout)
            if _browser_missing(data):
                outcome.fail("Visual QA could not run: Playwright or Chromium is missing", install_hint())
                return outcome
            current[page.label] = data
    finally:
        if plan.server is not None:
            plan.server.stop()

    baseline = capture_baseline(root, base, plan, vcfg, out_base, outcome) if vcfg.get("compare", True) else {}

    problems: List[str] = []
    changes: List[str] = []
    shots: List[str] = []
    failing_shots: List[str] = []
    for page in plan.pages:
        data = current[page.label]
        page_shots = data.get("screenshots") or {}
        shots.extend(str(s) for s in page_shots.values())
        if data.get("status") == "ERROR":
            problems.append(f"### {page.target}\nCould not inspect the page:\n" +
                            "\n".join(str(w) for w in (data.get("warnings") or [])[:5]))
            continue
        defects = page_defects(data)
        before = baseline.get(page.label)
        if before is not None:
            fresh = new_defects(defects, page_defects(before))
            old = len(defects) - len(fresh)
            if old:
                outcome.notes.append(f"{page.label}: {old} defect(s) already present on the base commit (not blocking).")
            defects = fresh
        if defects:
            problems.append(f"### {page.target}\n" + "\n".join(f"- {d}" for d in defects[:15]))
            failing_shots.extend(str(s) for s in page_shots.values())
        if before is None:
            if baseline or plan.kind == "static":
                changes.append(f"### {page.label}: new page (not on the base commit)\n" +
                               "\n".join(f"- after: {s}" for s in page_shots.values()))
            continue
        before_shots = before.get("screenshots") or {}
        for view in ("desktop", "mobile"):
            a, b = before_shots.get(view), page_shots.get(view)
            if not a or not b or not Path(a).is_file() or not Path(b).is_file():
                continue
            diff = screenshot_diff(a, b, out_base / "diff" / _slug(page.label) / f"{view}_diff.png", page_timeout)
            if diff is None or diff.get("ratio", 0) <= threshold:
                continue
            rows = diff.get("rows") or [0, 0]
            size = ""
            if diff.get("sizeA") != diff.get("sizeB"):
                size = f", page size {diff['sizeA'][0]}x{diff['sizeA'][1]} -> {diff['sizeB'][0]}x{diff['sizeB'][1]}"
            changes.append(
                f"### {page.label} ({view}): {diff['ratio'] * 100:.1f}% of pixels changed, rows {rows[0]}-{rows[1]}{size}\n"
                f"- before: {a}\n- after: {b}\n- diff (changed pixels in red): {diff.get('diff', '')}")

    if shots:
        outcome.notes.append("Visual QA screenshots: " + ", ".join(shots))
    if problems:
        detail = "\n".join(problems)
        if baseline:
            detail = "These defects are new: the base commit did not have them.\n" + detail
        if failing_shots:
            detail += ("\n\nOpen these screenshots and look at them before you fix the code "
                       "(desktop 1280x800, mobile 375x667):\n" + "\n".join(f"- {s}" for s in failing_shots))
        outcome.fail("Visual QA found defects in the rendered page", detail)
    if changes:
        outcome.review.append((
            "Visual changes to review",
            "Your change altered these pages. Open each before, after and diff image and look at them.\n"
            "For every page, say in one sentence what changed and whether you meant it. "
            "Fix any change you did not intend, such as a page you did not mean to touch, shifted layout, "
            "cut text or overlapping elements.\n\n" + "\n\n".join(changes),
        ))
    return outcome
