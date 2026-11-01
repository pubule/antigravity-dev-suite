#!/usr/bin/env python3
"""
Enterprise Playwright Visual QA Runner for Antigravity & Gemini
Captures desktop (1280x800) and mobile (375x667) screenshots, JS console errors, and page defects.
Compatible with macOS, Linux, and Windows 10/11.
"""

import sys
import os
import json
import socket
import argparse
import tempfile
import re
from pathlib import Path

COMMON_DEV_PORTS = [
    5173, 5174, 5175, 5176, 5177, 5178, 5179,
    3000, 3001, 3002, 3003, 3004, 3005,
    4173,  # Vite preview
    8080, 8081, 8000, 8001, 8002, 8888,
    4200, 5000, 4321, 8088, 19006
]

def is_http_server_active(port: int, host: str = "localhost") -> bool:
    """Fast non-blocking socket probe to verify if the port is actively listening across IPv4 and IPv6."""
    # 1. Try standard dual-stack host resolution first
    try:
        with socket.create_connection((host, port), timeout=0.04):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        # Host probe unreached; fall back to candidate IP addresses
        _fallback_needed = True

    # 2. Explicit dual-stack fallback for environments where localhost resolution is IPv4 or IPv6 only
    for candidate_ip in ("127.0.0.1", "::1"):
        try:
            with socket.create_connection((candidate_ip, port), timeout=0.04):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            continue

    return False

def find_active_dev_server(preferred_port: int | None = None) -> str:
    """Finds first active local development HTTP server rapidly."""
    if preferred_port and 1 <= preferred_port <= 65535:
        if is_http_server_active(preferred_port):
            return f"http://localhost:{preferred_port}"

    env_ports = []
    for env_key in ("PORT", "VITE_PORT", "DEV_PORT", "SERVER_PORT"):
        val = os.environ.get(env_key, "").strip()
        if val.isdigit():
            p = int(val)
            if 1 <= p <= 65535 and p not in env_ports:
                env_ports.append(p)

    for port in env_ports:
        if is_http_server_active(port):
            return f"http://localhost:{port}"

    for port in COMMON_DEV_PORTS:
        if is_http_server_active(port):
            return f"http://localhost:{port}"
    return ""

def extract_route_from_source(file_path: Path) -> str:
    """Extracts @route annotation from source file comments if present (e.g. // @route /dashboard)."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            head = f.read(2048)
        m = re.search(r"@route\s+([/\w\-\?&=]+)", head)
        if m:
            return m.group(1).strip()
    except (OSError, UnicodeDecodeError):
        m = None
    return ""

def audit_html_accessibility(html_content: str) -> list[str]:
    """Evaluates HTML content for critical WCAG 2.1 AA accessibility violations."""
    violations: list[str] = []

    # 1. <html> lang attribute (WCAG 3.1.1)
    html_match = re.search(r'<html\b([^>]*)>', html_content, re.IGNORECASE)
    if not html_match or not re.search(r'\blang\s*=', html_match.group(1), re.IGNORECASE):
        violations.append("MissingLangAttribute: <html> element missing 'lang' attribute (WCAG 3.1.1).")

    # 2. <title> presence and content (WCAG 2.4.2)
    title_match = re.search(r'<title\b[^>]*>(.*?)</title>', html_content, re.IGNORECASE | re.DOTALL)
    if not title_match or not title_match.group(1).strip():
        violations.append("MissingPageTitle: document <title> is missing or empty (WCAG 2.4.2).")

    # 3. <img> missing alt attribute (WCAG 1.1.1)
    for img in re.finditer(r'<img\b([^>]*)>', html_content, re.IGNORECASE):
        attrs = img.group(1)
        if not re.search(r'\balt\s*=', attrs, re.IGNORECASE):
            violations.append("MissingAltText: <img> element missing alt attribute (WCAG 1.1.1).")
            break

    # 4. Button accessible name (WCAG 4.1.2)
    for btn in re.finditer(r'<button\b([^>]*)>(.*?)</button>', html_content, re.IGNORECASE | re.DOTALL):
        attrs, inner = btn.group(1), btn.group(2).strip()
        has_aria = bool(re.search(r'\b(aria-label|aria-labelledby|title)\s*=', attrs, re.IGNORECASE))
        has_inner = bool(inner and not re.match(r'^\s*$', inner))
        has_icon = bool(re.search(r'<(svg|img)\b', inner, re.IGNORECASE))
        if not has_aria and not has_inner and not has_icon:
            violations.append("EmptyButtonLabel: button lacks text content or aria-label (WCAG 4.1.2).")
            break

    # 5. Form inputs without label (WCAG 1.3.1)
    for inp in re.finditer(r'<input\b([^>]*)>', html_content, re.IGNORECASE):
        attrs = inp.group(1)
        type_match = re.search(r'\btype\s*=\s*["\']?([^"\'\s>]+)', attrs, re.IGNORECASE)
        inp_type = type_match.group(1).lower() if type_match else "text"
        if inp_type in ("hidden", "submit", "button", "reset"):
            continue
        has_aria = bool(re.search(r'\b(aria-label|aria-labelledby|title)\s*=', attrs, re.IGNORECASE))
        id_match = re.search(r'\bid\s*=\s*["\']([^"\']+)["\']', attrs, re.IGNORECASE)
        has_for_label = False
        if id_match:
            inp_id = id_match.group(1)
            has_for_label = bool(re.search(rf'<label\b[^>]*\bfor\s*=\s*["\']{re.escape(inp_id)}["\']', html_content, re.IGNORECASE))
        if not has_aria and not has_for_label:
            violations.append("UnlabelledFormInput: input element lacks associated <label> or aria-label (WCAG 1.3.1).")
            break

    return violations

def capture_visual_artifacts(target: str, output_dir: str, test_mode: bool = False, route: str = "", dev_server: str = "", port: int | None = None) -> int:
    result = {
        "target": target,
        "status": "SUCCESS",
        "dev_server_detected": None,
        "screenshots": {},
        "console_errors": [],
        "page_errors": [],
        "a11y_violations": [],
        "a11y_warnings": [],
        "warnings": []
    }
    
    out_path = Path(output_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)
    temp_synthetic_file: Path | None = None
    
    try:
        # Check test mode
        if test_mode:
            temp_html = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8")
            temp_html.write("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Antigravity Visual QA Test</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 2rem; background: #0f172a; color: #f8fafc; }
        .card { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 1.5rem; max-width: 600px; margin: 0 auto; }
        .badge { background: #10b981; color: #022c22; padding: 0.25rem 0.75rem; border-radius: 9999px; font-weight: 600; font-size: 0.875rem; }
    </style>
</head>
<body>
    <div class="card">
        <span class="badge">E2E Visual QA Active</span>
        <h2>Antigravity Dev Suite</h2>
        <p>Playwright Dual-Viewport Screenshot Runner is operating with 100% fidelity.</p>
    </div>
</body>
</html>""")
            temp_html.close()
            temp_synthetic_file = Path(temp_html.name)
            target = temp_html.name
            result["target"] = "synthetic_test_page"

        # URL / File Resolution
        if target.startswith("http://") or target.startswith("https://"):
            url = target
        elif target.startswith("localhost:") or target.startswith("127.0.0.1:"):
            url = f"http://{target}"
        else:
            # Handle possible URL query or hash fragment on file targets
            clean_target = target
            suffix_fragment = ""
            if "#" in target or "?" in target:
                split_idx = min([i for i in [target.find("#"), target.find("?")] if i != -1])
                clean_target = target[:split_idx]
                suffix_fragment = target[split_idx:]

            file_path = Path(clean_target).expanduser().resolve()
            # If it's a frontend source file (tsx/jsx/vue/svelte/astro) that cannot run directly via file://
            if file_path.suffix.lower() in [".tsx", ".jsx", ".vue", ".svelte", ".astro", ".ts"]:
                active_server = dev_server.rstrip("/") if dev_server else find_active_dev_server(preferred_port=port)
                if active_server:
                    target_route = route or extract_route_from_source(file_path) or "/"
                    if not target_route.startswith("/"):
                        target_route = "/" + target_route
                    url = f"{active_server}{target_route}{suffix_fragment}"
                    result["dev_server_detected"] = active_server
                else:
                    result["status"] = "SKIPPED_NO_DEV_SERVER"
                    result["warnings"].append(
                        f"Component {file_path.name} requires an active dev server (e.g., Vite/Next on localhost:5173). None detected."
                    )
                    print(json.dumps(result, indent=2))
                    return 0
            else:
                if not file_path.exists():
                    result["status"] = "ERROR"
                    result["warnings"].append(f"Target file does not exist: {target}")
                    print(json.dumps(result, indent=2))
                    return 1
                
                # If target is a directory, resolve index.html or dev server
                if file_path.is_dir():
                    index_html = file_path / "index.html"
                    if index_html.is_file():
                        url = index_html.as_uri() + suffix_fragment
                    else:
                        active_server = dev_server.rstrip("/") if dev_server else find_active_dev_server(preferred_port=port)
                        if active_server:
                            url = active_server + suffix_fragment
                            result["dev_server_detected"] = active_server
                        else:
                            result["status"] = "SKIPPED_NO_DEV_SERVER"
                            result["warnings"].append(
                                f"Directory '{file_path.name}' has no index.html and no active dev server was detected."
                            )
                            print(json.dumps(result, indent=2))
                            return 0
                else:
                    url = file_path.as_uri() + suffix_fragment

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            result["status"] = "SKIPPED_DEPENDENCY"
            result["warnings"].append(
                "Playwright is not installed in the current Python environment. Run 'pip install playwright && playwright install chromium' to enable visual QA."
            )
            print(json.dumps(result, indent=2))
            return 0

        try:
            with sync_playwright() as p:
                launch_args = [
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--ignore-certificate-errors",
                ]
                if sys.platform == "darwin":
                    # Single-process mode is required on macOS in sandboxed environments to bypass Mach port rendezvous
                    launch_args.append("--single-process")

                browser = None
                try:
                    try:
                        browser = p.chromium.launch(headless=True, args=launch_args)
                    except Exception:
                        # Fallback launch args without single-process
                        fallback_args = ["--no-sandbox", "--disable-dev-shm-usage"]
                        browser = p.chromium.launch(headless=True, args=fallback_args)

                    # Create a single managed page with error listeners
                    page = browser.new_page(viewport={"width": 1280, "height": 800})
                    page.on("pageerror", lambda err: result["page_errors"].append(str(err)))
                    page.on("response", lambda resp: (
                        result["warnings"].append(f"HTTP {resp.status} on {resp.url}")
                        if resp.status >= 400 else None
                    ))
                    
                    # Separate fatal errors from non-fatal warnings
                    def handle_console(msg):
                        if msg.type == "error":
                            result["console_errors"].append(f"[{msg.type}] {msg.text}")
                        elif msg.type == "warning":
                            result["warnings"].append(f"[{msg.type}] {msg.text}")

                    page.on("console", handle_console)

                    # Resilient navigation: load DOM first, then bounded wait for network idle/load
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=12000)
                        try:
                            page.wait_for_load_state("load", timeout=3000)
                        except Exception as load_err:
                            result["warnings"].append(f"Load timeout for {url}: {str(load_err)}")
                    except Exception as nav_err:
                        result["warnings"].append(f"Navigation notice for {url}: {str(nav_err)}")

                    page.wait_for_timeout(300)

                    # 1. Desktop Viewport (1280x800)
                    desktop_screenshot = out_path / "desktop_preview.png"
                    page.screenshot(path=str(desktop_screenshot), full_page=True)
                    result["screenshots"]["desktop"] = str(desktop_screenshot)

                    # Automated WCAG 2.1 AA Accessibility Evaluation
                    try:
                        a11y_data = page.evaluate("""() => {
                            const violations = [];
                            const warnings = [];
                            if (!document.documentElement.getAttribute('lang')) {
                                violations.push("MissingLangAttribute: <html> element missing 'lang' attribute (WCAG 3.1.1).");
                            }
                            if (!document.title || document.title.trim() === '') {
                                violations.push("MissingPageTitle: document <title> is missing or empty (WCAG 2.4.2).");
                            }
                            const imgs = document.querySelectorAll('img:not([alt])');
                            if (imgs.length > 0) {
                                violations.push(`MissingAltText: ${imgs.length} <img> element(s) missing alt attribute (WCAG 1.1.1).`);
                            }
                            const buttons = document.querySelectorAll('button, [role="button"]');
                            let unnamedBtns = 0;
                            for (const b of buttons) {
                                const name = (b.innerText || b.getAttribute('aria-label') || b.getAttribute('title') || '').trim();
                                if (!name && !b.querySelector('svg, img')) {
                                    unnamedBtns++;
                                }
                            }
                            if (unnamedBtns > 0) {
                                violations.push(`EmptyButtonLabel: ${unnamedBtns} button(s) lack text content or aria-label (WCAG 4.1.2).`);
                            }
                            const inputs = document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]), select, textarea');
                            let unlabelledInputs = 0;
                            for (const inp of inputs) {
                                const id = inp.getAttribute('id');
                                const hasAria = inp.getAttribute('aria-label') || inp.getAttribute('aria-labelledby');
                                const hasLabel = id && document.querySelector(`label[for="${id}"]`);
                                const isNestedInLabel = inp.closest('label');
                                if (!hasAria && !hasLabel && !isNestedInLabel) {
                                    unlabelledInputs++;
                                }
                            }
                            if (unlabelledInputs > 0) {
                                warnings.push(`UnlabelledFormInput: ${unlabelledInputs} input element(s) lack associated <label> or aria-label (WCAG 1.3.1).`);
                            }
                            return { violations, warnings };
                        }""")
                        if a11y_data.get("violations"):
                            result["a11y_violations"].extend(a11y_data["violations"])
                        if a11y_data.get("warnings"):
                            result["a11y_warnings"].extend(a11y_data["warnings"])
                            result["warnings"].extend(a11y_data["warnings"])
                    except Exception as a11y_err:
                        result["warnings"].append(f"Accessibility evaluation notice: {str(a11y_err)}")

                    # 2. Mobile Viewport (375x667 - iPhone SE / Standard Mobile)
                    page.set_viewport_size({"width": 375, "height": 667})
                    page.wait_for_timeout(200)

                    # Programmatic Mobile Horizontal Scroll Overflow & Tap Target Check
                    try:
                        metrics = page.evaluate("""() => {
                            const scrollW = Math.max(
                                document.body ? document.body.scrollWidth : 0,
                                document.documentElement ? document.documentElement.scrollWidth : 0
                            );
                            const innerW = window.innerWidth;
                            const smallTargets = [];
                            const interactives = document.querySelectorAll('button, a[href], input:not([type="hidden"]), select, textarea, [role="button"], [role="link"], [role="checkbox"], [tabindex="0"]');
                            for (const el of interactives) {
                                const rect = el.getBoundingClientRect();
                                if (rect.width > 0 && rect.height > 0 && (rect.width < 44 || rect.height < 44)) {
                                    const desc = (el.innerText || el.getAttribute('aria-label') || el.tagName.toLowerCase()).trim();
                                    smallTargets.push(`${el.tagName.toLowerCase()} ("${desc.slice(0, 25)}") size ${Math.round(rect.width)}x${Math.round(rect.height)}px`);
                                    if (smallTargets.length >= 3) break;
                                }
                            }
                            return {
                                hasOverflow: scrollW > innerW,
                                scrollWidth: scrollW,
                                innerWidth: innerW,
                                smallTargets: smallTargets
                            };
                        }""")
                        if metrics.get("hasOverflow"):
                            result["page_errors"].append(
                                f"HorizontalOverflowDetected: scrollWidth ({metrics['scrollWidth']}px) exceeds mobile viewport ({metrics['innerWidth']}px)."
                            )
                        if metrics.get("smallTargets"):
                            for target_info in metrics["smallTargets"]:
                                result["warnings"].append(
                                    f"TouchTargetUnder44px: interactive element {target_info} is below 44x44px minimum touch target size."
                                )
                    except Exception as eval_err:
                        result["warnings"].append(f"Mobile metrics evaluation notice: {str(eval_err)}")

                    mobile_screenshot = out_path / "mobile_preview.png"
                    page.screenshot(path=str(mobile_screenshot), full_page=True)
                    result["screenshots"]["mobile"] = str(mobile_screenshot)

                finally:
                    if browser is not None:
                        try:
                            browser.close()
                        except Exception as close_err:
                            result["warnings"].append(f"Browser close notice: {str(close_err)}")
                
        except Exception as e:
            result["status"] = "ERROR"
            result["warnings"].append(f"Playwright execution error: {str(e)}")
            print(json.dumps(result, indent=2))
            return 1

        print(json.dumps(result, indent=2))
        return 0

    finally:
        # Guarantee cleanup of temporary synthetic test files
        if temp_synthetic_file and temp_synthetic_file.exists():
            try:
                temp_synthetic_file.unlink()
            except (OSError, PermissionError):
                temp_synthetic_file = None

def main():
    parser = argparse.ArgumentParser(description="Antigravity Visual QA Screenshot Runner")
    parser.add_argument("target", nargs="?", default="--test-mode", help="HTML file path, component path, or HTTP URL to inspect")
    parser.add_argument("--output-dir", default=str(Path(tempfile.gettempdir()) / "agy_visual_qa"), help="Directory where screenshots will be saved")
    parser.add_argument("--route", default="", help="Optional sub-route when inspecting component file (e.g. /dashboard)")
    parser.add_argument("--dev-server", default="", help="Explicit dev server base URL (e.g. http://localhost:3000)")
    parser.add_argument("--port", type=int, default=None, help="Explicit port to probe for dev server (e.g. 3000)")
    parser.add_argument("--test-mode", action="store_true", help="Run in self-test synthetic mode")
    
    args = parser.parse_args()
    is_test = args.test_mode or (args.target == "--test-mode")
    target = "" if is_test else args.target
    
    sys.exit(capture_visual_artifacts(
        target,
        args.output_dir,
        test_mode=is_test,
        route=args.route,
        dev_server=args.dev_server,
        port=args.port
    ))

if __name__ == "__main__":
    main()
