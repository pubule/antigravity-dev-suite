#!/usr/bin/env python3
"""Antigravity Stop Gate (compatibility wrapper).

The gate now lives in agy_hook.py, which runs the checks itself instead of
reading records left by earlier commands. This wrapper keeps the old entry points:

    python stop_gate.py            # read a Stop payload on stdin, print the decision
    python stop_gate.py --check .  # run the gate on a folder (exit 1 on failure)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import agy_hook  # noqa: E402


def audit_stop_permission(payload: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """Returns (decision, reason) where decision is 'continue' or 'allow'."""
    out = agy_hook.handle_stop(payload)
    return out.get("decision", "allow"), out.get("reason")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ("--check", "-c"):
        sys.exit(agy_hook.cli_check(sys.argv[2] if len(sys.argv) > 2 else "."))
    agy_hook.emit(agy_hook.handle_stop(agy_hook.read_payload()))


if __name__ == "__main__":
    main()
