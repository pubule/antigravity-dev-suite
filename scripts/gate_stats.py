#!/usr/bin/env python3
"""Stop gate log and statistics.

Every verdict of the Stop gate is appended to <state-dir>/gate-log.jsonl (outside the
work tree). `agy_hook.py stats [DIR] [--days N]` summarises it: how often agy is
blocked, by what, how many attempts it needs to pass, and how often it gives up.
That shows which rules to sharpen and whether a change to the plugin helped.

Python 3.9+ standard library only. Works on macOS, Linux and Windows.
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

LOG_NAME = "gate-log.jsonl"
MAX_LOG_BYTES = 2_000_000
KEEP_LINES = 4000


def append(state_dir: Path, entry: Dict[str, Any]) -> None:
    f = state_dir / LOG_NAME
    try:
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if f.stat().st_size > MAX_LOG_BYTES:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()[-KEEP_LINES:]
            f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass  # statistics must never break the gate


def read(state_dir: Path, since: float = 0.0) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        with open(state_dir / LOG_NAME, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if isinstance(e, dict) and float(e.get("t", 0)) >= since:
                    out.append(e)
    except OSError:
        pass
    return out


def summarize(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    verdicts = Counter(str(e.get("verdict")) for e in entries)
    failures: Counter = Counter()
    reviews: Counter = Counter()
    checks: Counter = Counter()
    durations: List[float] = []
    per_conv: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for e in entries:
        failures.update(_titles(e.get("failures")))
        reviews.update(_titles(e.get("reviews")))
        checks.update(e.get("ran") or [])
        if e.get("seconds") is not None:
            durations.append(float(e["seconds"]))
        per_conv[str(e.get("conv"))].append(e)
    attempts: List[int] = []
    for evs in per_conv.values():
        n = 0
        for e in sorted(evs, key=lambda x: x.get("t", 0)):
            if e.get("verdict") == "block":
                n += 1
            elif e.get("verdict") in ("pass", "review"):
                attempts.append(n + 1)
                n = 0
    return {
        "evaluations": len(entries),
        "conversations": len(per_conv),
        "verdicts": dict(verdicts),
        "top_failures": failures.most_common(8),
        "top_reviews": reviews.most_common(8),
        "checks": dict(checks),
        "avg_attempts_to_pass": round(sum(attempts) / len(attempts), 2) if attempts else None,
        "first_try_pass_rate": round(sum(1 for a in attempts if a == 1) / len(attempts), 2) if attempts else None,
        "avg_seconds": round(sum(durations) / len(durations), 1) if durations else None,
    }


def _titles(items: Optional[List[str]]) -> List[str]:
    # "Tests failed (`pytest -v`, exit 1)" and "... exit 2" are the same problem.
    return [str(t).split(" (`")[0] for t in items or []]


def render(s: Dict[str, Any], days: Optional[int]) -> str:
    span = f"last {days} day(s)" if days else "all time"
    v = s["verdicts"]
    lines = [
        f"Stop gate statistics ({span}): {s['evaluations']} verdict(s) in {s['conversations']} conversation(s)",
        f"  pass {v.get('pass', 0)}   review {v.get('review', 0)}   block {v.get('block', 0)}   "
        f"gave up {v.get('gave_up', 0)}",
    ]
    if s["avg_attempts_to_pass"] is not None:
        lines.append(f"  attempts to pass: {s['avg_attempts_to_pass']} on average, "
                     f"first-try pass rate {int(s['first_try_pass_rate'] * 100)}%")
    if s["avg_seconds"] is not None:
        lines.append(f"  average gate time: {s['avg_seconds']}s")
    if s["top_failures"]:
        lines.append("Most frequent failures:")
        lines += [f"  {n:4d}  {t}" for t, n in s["top_failures"]]
    if s["top_reviews"]:
        lines.append("Most frequent reviews:")
        lines += [f"  {n:4d}  {t}" for t, n in s["top_reviews"]]
    if s["checks"]:
        lines.append("Checks run: " + ", ".join(f"{k} {n}" for k, n in sorted(s["checks"].items())))
    return "\n".join(lines)


def cli(state_dir: Path, days: Optional[int], as_json: bool) -> int:
    since = time.time() - days * 86400 if days else 0.0
    entries = read(state_dir, since)
    if not entries:
        print(f"No stop gate verdicts recorded yet ({state_dir / LOG_NAME}).")
        return 0
    s = summarize(entries)
    print(json.dumps(s, indent=1) if as_json else render(s, days))
    return 0
