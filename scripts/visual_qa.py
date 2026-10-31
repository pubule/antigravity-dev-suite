#!/usr/bin/env python3
"""
Enterprise Playwright Visual QA Runner for Antigravity & Gemini
Captures desktop (1280x800) and mobile (375x667) screenshots, JS console errors, and page defects.
"""

import sys
import os
import json
import socket
import argparse
import tempfile
from pathlib import Path

COMMON_DEV_PORTS = [5173, 3000, 8080, 4200, 8000, 3001, 5000, 8081, 19006]

def is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False

def find_active_dev_server() -> str:
    for port in COMMON_DEV_PORTS:
        if is_port_open(port):
            return f"http://localhost:{port}"
    return ""

def capture_visual_artifacts(target: str, output_dir: str, test_mode: bool = False):
    result = {
        "target": target,
        "status": "SUCCESS",
        "dev_server_detected": None,
        "screenshots": {},
        "console_errors": [],
        "page_errors": [],
        "warnings": []
    }
    
    out_path = Path(output_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)
    
    # Check test mode
    if test_mode:
        temp_html = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8")
        temp_html.write("""<!DOCTYPE html>
<html>
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
        target = temp_html.name
        result["target"] = "synthetic_test_page"

    # URL / File Resolution
    if target.startswith("http://") or target.startswith("https://"):
        url = target
    else:
        file_path = Path(target).resolve()
        # If it's a frontend source file (tsx/jsx/vue/svelte) that cannot run via file://
        if file_path.suffix.lower() in [".tsx", ".jsx", ".vue", ".svelte", ".ts"]:
            active_server = find_active_dev_server()
            if active_server:
                url = active_server
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
            url = file_path.as_uri()

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
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--single-process",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--ignore-certificate-errors",
                ],
            )

            # Create a single managed page with error listeners
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.on("pageerror", lambda err: result["page_errors"].append(str(err)))
            page.on(
                "console",
                lambda msg: result["console_errors"].append(f"[{msg.type}] {msg.text}")
                if msg.type in ["error", "warning"]
                else None,
            )

            # Navigate once
            page.goto(url, wait_until="load", timeout=12000)
            page.wait_for_timeout(400)

            # 1. Desktop Viewport (1280x800)
            desktop_screenshot = out_path / "desktop_preview.png"
            page.screenshot(path=str(desktop_screenshot), full_page=True)
            result["screenshots"]["desktop"] = str(desktop_screenshot)

            # 2. Mobile Viewport (375x667 - iPhone SE / Standard Mobile)
            page.set_viewport_size({"width": 375, "height": 667})
            page.wait_for_timeout(200)

            mobile_screenshot = out_path / "mobile_preview.png"
            page.screenshot(path=str(mobile_screenshot), full_page=True)
            result["screenshots"]["mobile"] = str(mobile_screenshot)

            browser.close()
            
    except Exception as e:
        result["status"] = "ERROR"
        result["warnings"].append(f"Playwright execution error: {str(e)}")
        print(json.dumps(result, indent=2))
        return 1

    print(json.dumps(result, indent=2))
    return 0

def main():
    parser = argparse.ArgumentParser(description="Antigravity Visual QA Screenshot Runner")
    parser.add_argument("target", nargs="?", default="--test-mode", help="HTML file path, component path, or HTTP URL to inspect")
    parser.add_argument("--output-dir", default=str(Path(tempfile.gettempdir()) / "agy_visual_qa"), help="Directory where screenshots will be saved")
    parser.add_argument("--test-mode", action="store_true", help="Run in self-test synthetic mode")
    
    args = parser.parse_args()
    is_test = args.test_mode or (args.target == "--test-mode")
    target = "" if is_test else args.target
    
    sys.exit(capture_visual_artifacts(target, args.output_dir, test_mode=is_test))

if __name__ == "__main__":
    main()
