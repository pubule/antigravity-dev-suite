#!/usr/bin/env python3
"""
Antigravity CLI (agy) Custom Statusline Renderer
Renders live model, workspace, and context window occupancy bar for agy statusline.

Usage in agy:
    /statusline python3 /absolute/path/to/antigravity-dev-suite/scripts/statusline.py

Settings (~/.gemini/antigravity-cli/settings.json):
    "statusLine": {
      "type": "command",
      "command": "python3 /absolute/path/to/antigravity-dev-suite/scripts/statusline.py",
      "enabled": true
    }
"""

from __future__ import annotations

import sys
import os
import json
from pathlib import Path
from typing import Dict, Any, Optional

# Add parent directory for module imports
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

try:
    from handoff import get_context_occupancy
except ImportError:
    get_context_occupancy = None  # type: ignore


def build_context_bar(percentage: float, width: int = 10, use_color: bool = True) -> str:
    """Constructs ANSI-colored progress bar for context occupancy. # safe-bounds"""
    clamped_pct = max(0.0, min(100.0, percentage))
    filled = int(round((clamped_pct / 100.0) * width))
    empty = width - filled
    bar_chars = ("█" * filled) + ("░" * empty)

    if not use_color:
        return f"[{bar_chars}] {clamped_pct:.1f}%"

    # Color thresholds: Green < 50%, Yellow 50-80%, Bold Red >= 80%
    if clamped_pct < 50.0:
        color = "\033[32m"  # Green
        status_label = "OK"
    elif clamped_pct < 80.0:
        color = "\033[33m"  # Yellow
        status_label = "MODERATE"
    else:
        color = "\033[1;31m"  # Bold Red
        status_label = "CRITICAL"

    reset = "\033[0m"
    return f"{color}[{bar_chars}] {clamped_pct:.1f}% {status_label}{reset}"


def read_stdin_payload(max_bytes: int = 65536) -> Optional[Dict[str, Any]]:
    """Reads and parses JSON payload piped from agy via stdin. # safe-bounds"""
    if sys.stdin.isatty():
        return None
    try:
        raw = sys.stdin.read(max_bytes)
        if not raw or not raw.strip():
            return None
        return json.loads(raw)
    except Exception as err:
        sys.stderr.write(f"[statusline payload parsing failed]: {err}\n")
        return None


def render_statusline(payload: Optional[Dict[str, Any]] = None) -> str:
    """Generates the formatted single-line statusline string. # safe-bounds"""
    if payload is None:
        payload = read_stdin_payload()

    model_name = "Gemini"
    dir_name = Path.cwd().name
    pct = 0.0
    tokens_label = ""

    if payload:
        # Extract model
        model_obj = payload.get("model")
        if isinstance(model_obj, dict):
            model_name = model_obj.get("display_name") or model_obj.get("name") or "Gemini"
        elif isinstance(model_obj, str) and model_obj:
            model_name = model_obj

        # Extract workspace directory
        ws_obj = payload.get("workspace")
        if isinstance(ws_obj, dict) and ws_obj.get("current_dir"):
            dir_name = Path(ws_obj["current_dir"]).name

        # Extract context window data
        ctx_window = payload.get("context_window")
        if isinstance(ctx_window, dict):
            rem = ctx_window.get("remaining_percentage")
            if rem is not None:
                pct = max(0.0, min(100.0, 100.0 - float(rem)))
            usage = ctx_window.get("current_usage")
            if isinstance(usage, dict):
                in_tok = usage.get("input_tokens", 0) + usage.get("cache_read_tokens", 0)
                if in_tok > 0:
                    tokens_label = f" ({in_tok // 1000}k)"

    # Fallback to transcript telemetry if payload context is missing
    if pct == 0.0 and get_context_occupancy:
        try:
            telemetry = get_context_occupancy()
            if telemetry.get("tracked"):
                pct = telemetry.get("occupancy_percentage", 0.0)
                tot = telemetry.get("total_prompt_tokens", 0)
                if tot > 0:
                    tokens_label = f" ({tot // 1000}k/100k)"
        except Exception as err:
            sys.stderr.write(f"[statusline context fallback failed]: {err}\n")

    ctx_bar = build_context_bar(pct, width=10, use_color=True)
    sep = "\033[2m│\033[0m"

    # Assemble concise statusline segments
    line = f"\033[1;36m{model_name}\033[0m {sep} \033[2m{dir_name}\033[0m {sep} {ctx_bar}{tokens_label}"
    return line


def main() -> None:
    try:
        output = render_statusline()
        # Print without extra trailing newline to fit statusline single line
        sys.stdout.write(output)
        sys.stdout.flush()
    except Exception as e:
        sys.stderr.write(f"[statusline error]: {e}\n")


if __name__ == "__main__":
    main()
