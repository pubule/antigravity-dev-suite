#!/usr/bin/env python3
"""UI flows: short user journeys that agy writes and the Stop gate runs in Chromium.

Opening a page shows that it renders. A flow shows that it works: agy clicks, types
and checks the result, the way a person tries a change before saying it is done.

A flow is a JSON file in `.agy/flows/` (or in the folder named by
`visual_qa.flows_dir` in `.agents/agy.json`, for flows the team commits):

    {
      "name": "login shows the dashboard",
      "route": "/login",                      # or "file": "public/index.html" for static pages
      "viewport": "desktop",                  # or "mobile", or {"width": 390, "height": 844}
      "steps": [
        {"fill": "#email", "value": "ada@example.com"},
        {"fill": "#password", "value": "secret"},
        {"click": "role=button[name='Sign in']"},
        {"expect_url": "/dashboard"},
        {"expect_text": "Welcome, Ada"},
        {"expect_visible": "[data-testid=logout]"},
        {"screenshot": "dashboard"}
      ]
    }

Selectors use Playwright syntax: CSS, `text=Save`, `role=button[name='Save']`,
`[data-testid=x]`. Actions: goto, click, dblclick, fill, press, select, check, uncheck,
hover, wait (ms), wait_for, viewport, screenshot. Checks: expect_text, expect_no_text
(optional "selector"), expect_visible, expect_hidden, expect_url, expect_count
(+ "count"), expect_value (+ "value"), expect_enabled, expect_disabled.

A flow fails on the first step that fails, and on any JS exception, console error or
failed same-origin request while it runs. Screenshots go to the output folder; a
failing step always gets one.

    python ui_flows.py run FLOW.json --base-url http://localhost:5173 --output-dir DIR [--root DIR]

prints a JSON result. Exit codes: 0 pass, 1 fail, 3 Playwright or Chromium missing.

Python 3.9+; needs the `playwright` package (installed with the suite).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

FLOWS_REL = ".agy/flows"
STEP_TIMEOUT_MS = 8000
MAX_WAIT_MS = 10000
MAX_FLOWS = 12
VIEWPORTS = {"desktop": {"width": 1280, "height": 800}, "mobile": {"width": 375, "height": 667}}
ACTIONS = ("goto", "click", "dblclick", "fill", "press", "select", "check", "uncheck", "hover",
           "wait", "wait_for", "viewport", "screenshot", "expect_text", "expect_no_text",
           "expect_visible", "expect_hidden", "expect_url", "expect_count", "expect_value",
           "expect_enabled", "expect_disabled")


# ------------------------------------------------------------------ discovery

def flow_dirs(root: Path, vcfg: Optional[Dict[str, Any]] = None) -> List[Path]:
    dirs = [root / FLOWS_REL]
    extra = (vcfg or {}).get("flows_dir")
    if isinstance(extra, str) and extra.strip():
        dirs.append(root / extra.strip())
    return dirs


def find_flows(root: Path, vcfg: Optional[Dict[str, Any]] = None) -> List[Path]:
    found: List[Path] = []
    for d in flow_dirs(root, vcfg):
        if d.is_dir():
            found.extend(sorted(p for p in d.glob("*.json") if p.is_file()))
    return found[:MAX_FLOWS]


def flows_fingerprint(root: Path, vcfg: Optional[Dict[str, Any]] = None) -> str:
    """Part of the gate fingerprint: writing or editing a flow must re-run the gate."""
    parts: List[str] = []
    for p in find_flows(root, vcfg):
        try:
            parts.append(p.name + "\0" + p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\0".join(parts)


def load_flow(path: Path) -> Tuple[Optional[Dict[str, Any]], str]:
    """(flow, error). Validates the shape so agy gets a precise message, not a stack trace."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return None, f"cannot read {path.name}: {e}"
    if not isinstance(data, dict):
        return None, f"{path.name}: the flow must be a JSON object"
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        return None, f"{path.name}: \"steps\" must be a non-empty list"
    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            return None, f"{path.name}: step {i} must be an object"
        names = [k for k in step if k in ACTIONS]
        if len(names) != 1:
            return None, (f"{path.name}: step {i} must have exactly one action of: " + ", ".join(ACTIONS)
                          + f" (got {sorted(step)})")
    if not any(next(k for k in s if k in ACTIONS).startswith("expect") for s in steps):
        return None, f"{path.name}: a flow needs at least one expect_* step, or it checks nothing"
    return data, ""


# --------------------------------------------------------------------- runner

def _join(base: str, route: str) -> str:
    if not route:
        return base
    if re.match(r"^https?://", route):
        return route
    return base.rstrip("/") + "/" + route.lstrip("/")


def _origin(url: str) -> str:
    try:
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}" if p.netloc else ""
    except ValueError:
        return ""


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")[:60] or "flow"


def start_url(flow: Dict[str, Any], base_url: str, root: Path) -> Tuple[str, str]:
    """(url, error)."""
    if isinstance(flow.get("file"), str):
        f = (root / flow["file"]).resolve()
        if not f.is_file():
            return "", f"file not found: {flow['file']}"
        return f.as_uri(), ""
    if not base_url:
        return "", "no dev server URL to open the route on (add \"file\" for a static page)"
    route = flow.get("route") if isinstance(flow.get("route"), str) else "/"
    return _join(base_url, route), ""


def run_flow(flow_path: Path, base_url: str, out_dir: Path, root: Path) -> Tuple[int, Dict[str, Any]]:
    result: Dict[str, Any] = {
        "flow": flow_path.name, "name": "", "status": "PASS", "steps_run": 0, "failed_step": None,
        "error": "", "page_errors": [], "console_errors": [], "http_errors": [], "screenshots": [],
    }
    flow, err = load_flow(flow_path)
    if flow is None:
        result.update(status="INVALID", error=err)
        return 1, result
    result["name"] = str(flow.get("name") or flow_path.stem)
    url, err = start_url(flow, base_url, root)
    if err:
        result.update(status="ERROR", error=err)
        return 1, result
    try:
        from playwright.sync_api import expect, sync_playwright
    except ImportError:
        result.update(status="SKIPPED_DEPENDENCY", error="Playwright is not installed")
        return 3, result

    out_dir.mkdir(parents=True, exist_ok=True)
    origin = _origin(url)
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            except Exception as e:  # browser binary missing
                result.update(status="SKIPPED_DEPENDENCY", error=str(e)[:500])
                return 3, result
            try:
                vp = flow.get("viewport", "desktop")
                size = vp if isinstance(vp, dict) else VIEWPORTS.get(str(vp), VIEWPORTS["desktop"])
                page = browser.new_page(viewport={"width": int(size.get("width", 1280)),
                                                  "height": int(size.get("height", 800))})
                page.set_default_timeout(STEP_TIMEOUT_MS)
                page.on("pageerror", lambda e: result["page_errors"].append(str(e)))
                page.on("console", lambda m: result["console_errors"].append(m.text)
                        if m.type == "error" else None)

                def on_response(resp: Any) -> None:
                    if resp.status >= 400 and origin and _origin(resp.url) == origin \
                            and not resp.url.rstrip("/").endswith("favicon.ico"):
                        result["http_errors"].append(f"HTTP {resp.status} on {resp.url}")

                page.on("response", on_response)
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                try:
                    page.wait_for_load_state("networkidle", timeout=4000)
                except Exception:
                    pass  # long-polling apps never go idle; the steps wait for their own elements
                base_for_goto = base_url or url
                for i, step in enumerate(flow["steps"], 1):
                    action = next(k for k in step if k in ACTIONS)
                    try:
                        _do(page, expect, action, step, base_for_goto, out_dir, result, i)
                    except Exception as e:
                        msg = str(e).strip().splitlines()
                        result.update(status="FAIL", failed_step=i,
                                      error=f"step {i} {json.dumps(step)}: " + " ".join(msg[:6])[:700])
                        shot = out_dir / f"step{i}_failed.png"
                        try:
                            page.screenshot(path=str(shot), full_page=True)
                            result["screenshots"].append(str(shot))
                        except Exception:
                            pass
                        break
                    result["steps_run"] = i
                if result["status"] == "PASS":
                    page.wait_for_timeout(200)  # late errors from the last action
                    final = out_dir / "final.png"
                    page.screenshot(path=str(final), full_page=True)
                    result["screenshots"].append(str(final))
            finally:
                browser.close()
    except Exception as e:
        result.update(status="ERROR", error=f"Playwright error: {e}"[:800])
        return 1, result
    if result["status"] == "PASS" and (result["page_errors"] or result["console_errors"] or result["http_errors"]):
        result["status"] = "FAIL"
        result["error"] = "the steps passed, but the page reported errors while the flow ran"
    return (0 if result["status"] == "PASS" else 1), result


def _do(page: Any, expect: Any, action: str, step: Dict[str, Any], base: str, out_dir: Path,
        result: Dict[str, Any], i: int) -> None:
    val = step[action]
    sel = step.get("selector")
    if action == "goto":
        page.goto(_join(base, str(val)), wait_until="domcontentloaded")
    elif action == "click":
        page.locator(str(val)).first.click()
    elif action == "dblclick":
        page.locator(str(val)).first.dblclick()
    elif action == "fill":
        page.locator(str(val)).first.fill(str(step.get("value", "")))
    elif action == "press":
        if sel:
            page.locator(str(sel)).first.press(str(val))
        else:
            page.keyboard.press(str(val))
    elif action == "select":
        page.locator(str(val)).first.select_option(str(step.get("value", "")))
    elif action == "check":
        page.locator(str(val)).first.check()
    elif action == "uncheck":
        page.locator(str(val)).first.uncheck()
    elif action == "hover":
        page.locator(str(val)).first.hover()
    elif action == "wait":
        page.wait_for_timeout(min(int(val), MAX_WAIT_MS))
    elif action == "wait_for":
        page.locator(str(val)).first.wait_for(state="visible")
    elif action == "viewport":
        size = val if isinstance(val, dict) else VIEWPORTS.get(str(val), VIEWPORTS["desktop"])
        page.set_viewport_size({"width": int(size.get("width", 1280)), "height": int(size.get("height", 800))})
    elif action == "screenshot":
        shot = out_dir / f"step{i}_{_slug(str(val))}.png"
        page.screenshot(path=str(shot), full_page=True)
        result["screenshots"].append(str(shot))
    elif action == "expect_text":
        expect(page.locator(str(sel or "body")).first).to_contain_text(str(val))
    elif action == "expect_no_text":
        expect(page.locator(str(sel or "body")).first).not_to_contain_text(str(val))
    elif action == "expect_visible":
        expect(page.locator(str(val)).first).to_be_visible()
    elif action == "expect_hidden":
        expect(page.locator(str(val)).first).to_be_hidden()
    elif action == "expect_url":
        expect(page).to_have_url(re.compile(re.escape(str(val))))
    elif action == "expect_count":
        expect(page.locator(str(val))).to_have_count(int(step.get("count", 0)))
    elif action == "expect_value":
        expect(page.locator(str(val)).first).to_have_value(str(step.get("value", "")))
    elif action == "expect_enabled":
        expect(page.locator(str(val)).first).to_be_enabled()
    elif action == "expect_disabled":
        expect(page.locator(str(val)).first).to_be_disabled()


# ----------------------------------------------------------------- gate side

def run_flows(root: Path, flows: List[Path], base_url: str, out_dir: Path,
              timeout: int) -> List[Dict[str, Any]]:
    """Run each flow in a child process (crash and hang isolation)."""
    results: List[Dict[str, Any]] = []
    for path in flows:
        cmd = [sys.executable, str(Path(__file__).resolve()), "run", str(path), "--base-url", base_url,
               "--output-dir", str(out_dir / _slug(path.stem)), "--root", str(root)]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False,
                                 encoding="utf-8", errors="replace")
            data = json.loads(res.stdout) if res.stdout.strip() else {}
            if not isinstance(data, dict) or not data:
                data = {"flow": path.name, "status": "ERROR",
                        "error": (res.stdout + res.stderr).strip()[-800:] or f"exit {res.returncode}"}
        except subprocess.TimeoutExpired:
            data = {"flow": path.name, "status": "ERROR", "error": f"timed out after {timeout}s"}
        except (OSError, ValueError) as e:
            data = {"flow": path.name, "status": "ERROR", "error": str(e)}
        results.append(data)
    return results


def format_failure(r: Dict[str, Any]) -> str:
    lines = [f"### {r.get('flow')} ({r.get('name') or ''}): {r.get('status')}", str(r.get("error") or "")]
    for key, label in (("page_errors", "JS exception"), ("console_errors", "Console error"),
                       ("http_errors", "Failed request")):
        for item in (r.get(key) or [])[:5]:
            lines.append(f"- {label}: {str(item)[:300]}")
    for s in r.get("screenshots") or []:
        lines.append(f"- screenshot: {s}")
    return "\n".join(line for line in lines if line)


FLOW_EXAMPLE = (
    '{"name": "<what the user does>", "route": "/<page>", "steps": [\n'
    '  {"click": "role=button[name=\'Add\']"},\n'
    '  {"fill": "#title", "value": "Milk"},\n'
    '  {"press": "Enter", "selector": "#title"},\n'
    '  {"expect_text": "Milk", "selector": "ul.items"},\n'
    '  {"expect_count": "ul.items li", "count": 1}\n'
    "]}"
)


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Run one UI flow in Chromium.")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("flow")
    r.add_argument("--base-url", default="")
    r.add_argument("--output-dir", default=".agy/flow-shots")
    r.add_argument("--root", default=".")
    args = ap.parse_args(argv)
    if args.cmd != "run":
        ap.print_help()
        return 2
    code, result = run_flow(Path(args.flow).resolve(), args.base_url, Path(args.output_dir).resolve(),
                            Path(args.root).resolve())
    print(json.dumps(result, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
