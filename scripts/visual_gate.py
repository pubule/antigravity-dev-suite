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


class VisualOutcome:
    """Result of the visual step: failures (title, detail) and notes for the report."""

    def __init__(self) -> None:
        self.failures: List[Tuple[str, str]] = []
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

def _resolve_targets(root: Path, fe_files: List[str], vcfg: Dict[str, Any],
                     log_path: Path, outcome: VisualOutcome) -> Tuple[List[str], Optional[DevServer]]:
    """Pages to open, and the dev server the gate started (to stop afterwards)."""
    url = vcfg.get("url") if isinstance(vcfg.get("url"), str) else ""
    url = url.strip()
    dev_command = vcfg.get("dev_command") if isinstance(vcfg.get("dev_command"), str) else ""
    dev_command = dev_command.strip()
    startup = _int(vcfg.get("startup_timeout"), DEFAULT_STARTUP_TIMEOUT)
    routes = _routes(vcfg)

    if url:
        if server_answers(url):
            return [_join(url, r) for r in routes], None
        if not dev_command:
            outcome.fail("Visual QA: dev server not running",
                         f"Nothing answers at {url} (visual_qa.url in .agents/agy.json).\n"
                         "Start the dev server, then finish again. To let the gate start it, ask the user "
                         "to set \"visual_qa\": {\"dev_command\": \"npm run dev\"} in .agents/agy.json.")
            return [], None
        server = DevServer(dev_command, root, log_path)
        server.start()
        if _wait_for(lambda: server_answers(url), server, startup):
            outcome.notes.append(f"Visual QA started `{dev_command}` for {url}.")
            return [_join(url, r) for r in routes], server
        tail = server.log_tail()
        server.stop()
        outcome.fail("Visual QA: dev server did not start",
                     f"`{dev_command}` did not answer at {url} within {startup}s.\nLast output:\n{tail}")
        return [], None

    if dev_command:
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
            return [_join(base, r) for r in routes], server
        tail = server.log_tail()
        server.stop()
        outcome.fail("Visual QA: dev server did not start",
                     f"`{dev_command}` opened no new local port within {startup}s. "
                     "Ask the user to add \"url\" to the visual_qa block in .agents/agy.json.\n"
                     f"Last output:\n{tail}")
        return [], None

    static = static_html_targets(root, fe_files)
    if static:
        return static, None

    active = _active_ports()
    if active:
        base = f"http://localhost:{active[0]}"
        outcome.notes.append(f"Visual QA used the dev server already running on {base} (auto-detected).")
        return [_join(base, r) for r in routes], None

    outcome.fail(
        "Visual QA could not run: no page to open",
        "You changed frontend files:\n" + "\n".join(f"- {f}" for f in fe_files[:10]) +
        "\nNo dev server is running and no static HTML page changed.\n"
        "Start the project's dev server (for example `npm run dev`) and finish again.\n"
        "To make this automatic, ask the user to add to .agents/agy.json:\n"
        '  "visual_qa": {"url": "http://localhost:5173", "dev_command": "npm run dev", "routes": ["/"]}\n'
        "or \"visual_qa\": false when the project has no UI to check.",
    )
    return [], None


def run_visual_gate(root: Path, fe_files: List[str], vcfg: Dict[str, Any], out_base: Path) -> VisualOutcome:
    outcome = VisualOutcome()
    page_timeout = _int(vcfg.get("timeout"), DEFAULT_PAGE_TIMEOUT)
    targets, server = _resolve_targets(root, fe_files, vcfg, out_base / "dev-server.log", outcome)
    try:
        if not targets:
            return outcome
        outcome.ran = True
        problems: List[str] = []
        shots: List[str] = []
        for target in targets:
            label = target
            if not re.match(r"^https?://", target):
                try:
                    label = Path(target).resolve().relative_to(root.resolve()).as_posix()
                except (ValueError, OSError):
                    label = target  # outside the project: keep the full path
            out_dir = out_base / _slug(label)
            data = inspect_target(target, out_dir, page_timeout)
            if _browser_missing(data):
                outcome.fail("Visual QA could not run: Playwright or Chromium is missing", install_hint())
                return outcome
            for shot in (data.get("screenshots") or {}).values():
                shots.append(str(shot))
            if data.get("status") == "ERROR":
                problems.append(f"### {target}\nCould not inspect the page:\n" +
                                "\n".join(str(w) for w in (data.get("warnings") or [])[:5]))
                continue
            defects = page_defects(data)
            if defects:
                problems.append(f"### {target}\n" + "\n".join(f"- {d}" for d in defects[:15]))
        if shots:
            outcome.notes.append("Visual QA screenshots: " + ", ".join(shots))
        if problems:
            detail = "\n".join(problems)
            if shots:
                detail += ("\n\nOpen these screenshots and look at them before you fix the code "
                           "(desktop 1280x800, mobile 375x667):\n" + "\n".join(f"- {s}" for s in shots))
            outcome.fail("Visual QA found defects in the rendered page", detail)
        return outcome
    finally:
        if server is not None:
            server.stop()
