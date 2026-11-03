#!/usr/bin/env python3
"""Guidance that makes a fast model plan and prove like a careful one.

- `start_message`: injected on the first model call of a conversation. A compact
  map of the repository (so agy reads the right files first) and the request to
  write acceptance criteria in `.agy/criteria.md` before changing code.
- `check_criteria`: at Stop, the criteria must exist, belong to this conversation
  and be ticked with evidence.
- `rules_for`: the language rules (rules/languages, rules/database) that match the
  changed files, injected once per conversation when such files first appear.

Python 3.9+ standard library only. Works on macOS, Linux and Windows.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("guidance")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
CRITERIA_REL = ".agy/criteria.md"
CRITERIA_RE = re.compile(r"^\s*[-*]\s*\[(?P<mark>[ xX])\]\s*(?P<text>.+?)\s*$")
EVIDENCE_RE = re.compile(r"evidence\s*:|prova\s*:|\s[—–]\s|\s->\s", re.IGNORECASE)
FRONTMATTER_RE = re.compile(r"\A---\s*\n(?P<head>.*?)\n---\s*\n", re.DOTALL)
MAX_RULE_CHARS = 3000

START_TEXT = (
    "[Antigravity Guided Start] Work like a senior engineer: understand first, then change, then prove.\n"
    "1. Restate the task in one sentence. List what you do not know yet and read the files involved "
    "(the map below shows where things are) before you edit anything.\n"
    "2. Before changing code, write {criteria} with 3 to 5 acceptance criteria. Each one is an "
    "observable behaviour you can check, not an activity:\n"
    "   - [ ] <behaviour> (proved by <test or command>)\n"
    "3. Before you finish, tick each criterion with its evidence:\n"
    "   - [x] <behaviour> — evidence: <test name, command output or screenshot>\n"
    "   The stop gate fails while a criterion is unticked. If a criterion turns out to be wrong, "
    "fix the criterion and say why.\n"
    "Skip the criteria only when the user asked a question and no code changes.\n"
)


# ------------------------------------------------------------------ start

def ensure_excluded(root: Path) -> None:
    """Keep .agy/ out of git status and commits without touching the project's .gitignore."""
    try:
        import subprocess
        out = subprocess.run(["git", "rev-parse", "--git-path", "info/exclude"], cwd=str(root),
                             capture_output=True, text=True, timeout=10, check=False)
        rel = out.stdout.strip()
        if out.returncode != 0 or not rel:
            return
        f = Path(rel) if Path(rel).is_absolute() else root / rel
        text = f.read_text(encoding="utf-8") if f.is_file() else ""
        if not re.search(r"^/?\.agy/?\s*$", text, re.MULTILINE):
            f.parent.mkdir(parents=True, exist_ok=True)
            with open(f, "a", encoding="utf-8") as fh:
                fh.write(("" if not text or text.endswith("\n") else "\n") + ".agy/\n")
    except (OSError, ValueError) as err:
        logger.debug("Cannot update info/exclude: %s", err)


def repo_map_text(root: Path, max_tokens: int = 1200) -> str:
    try:
        from repo_map import generate_repo_map
        res = generate_repo_map(root, max_tokens=max_tokens, max_files=150, use_cache=False)
        return str(res.get("formatted_map") or "").strip()
    except Exception as err:  # a map is a help, never a reason to fail
        logger.debug("Repo map failed: %s", err)
        return ""


def start_message(root: Path, cfg: Dict[str, Any]) -> str:
    parts: List[str] = []
    if cfg.get("criteria", True):
        ensure_excluded(root)
        parts.append(START_TEXT.format(criteria=CRITERIA_REL))
    if cfg.get("repo_map", True):
        rmap = repo_map_text(root)
        if rmap:
            parts.append("Repository map (files and main symbols):\n" + rmap[:5000])
    return "\n".join(parts)


# --------------------------------------------------------------- criteria

def read_criteria(root: Path) -> Tuple[Optional[float], List[Tuple[bool, str]]]:
    """(mtime or None when missing, [(ticked, text)])."""
    f = root / CRITERIA_REL
    try:
        mtime = f.stat().st_mtime
        text = f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, []
    items: List[Tuple[bool, str]] = []
    for line in text.splitlines():
        m = CRITERIA_RE.match(line)
        if m:
            items.append((m.group("mark") != " ", m.group("text")))
    return mtime, items


def criteria_fingerprint(root: Path) -> str:
    """Part of the gate fingerprint: ticking a criterion must re-run the gate."""
    try:
        return (root / CRITERIA_REL).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def check_criteria(root: Path, cfg: Dict[str, Any], session_start: float = 0.0
                   ) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    """Returns (failures, reviews) for the acceptance criteria."""
    if not cfg.get("criteria", True):
        return [], []
    mtime, items = read_criteria(root)
    if mtime is None:
        return [], [("No acceptance criteria", (
            f"Write {CRITERIA_REL} now: 3 to 5 behaviours this change must have, each ticked with evidence:\n"
            "- [x] <behaviour> — evidence: <test name, command output or screenshot>\n"
            "Check each one honestly against your change. Fix the code if one is not met."))]
    if session_start and mtime < session_start - 1:
        return [], [("Acceptance criteria are from an earlier task", (
            f"{CRITERIA_REL} was last written before this conversation started. Replace it with the "
            "criteria of the current task and tick each one with evidence."))]
    if not items:
        return [], [("Acceptance criteria have no checkboxes", (
            f"Write each criterion in {CRITERIA_REL} as a checkbox line:\n"
            "- [x] <behaviour> — evidence: <test name, command output or screenshot>"))]
    failures: List[Tuple[str, str]] = []
    reviews: List[Tuple[str, str]] = []
    open_items = [t for done, t in items if not done]
    if open_items:
        failures.append(("Acceptance criteria not met", (
            "These criteria in " + CRITERIA_REL + " are not ticked:\n"
            + "\n".join(f"- [ ] {t}" for t in open_items[:15])
            + "\nMake the change meet each one and tick it with evidence. If a criterion is wrong, "
            "rewrite it and explain why in your answer.")))
    bare = [t for done, t in items if done and not EVIDENCE_RE.search(" " + t)]
    if bare:
        reviews.append(("Criteria ticked without evidence", (
            "Add the evidence to each of these lines (` — evidence: <test, command output, screenshot>`):\n"
            + "\n".join(f"- [x] {t}" for t in bare[:15]))))
    return failures, reviews


# ------------------------------------------------------------------ rules

def _rule_dirs(root: Path) -> List[Path]:
    return [root / ".agents" / "rules", PLUGIN_DIR / "rules"]


def _globs(head: str) -> List[str]:
    m = re.search(r"^globs:\s*(\[.*\])\s*$", head, re.MULTILINE)
    if not m:
        return []
    try:
        val = json.loads(m.group(1))
        return [g for g in val if isinstance(g, str)]
    except ValueError:
        return []


def _matches(rel: str, pattern: str) -> bool:
    pat = pattern[3:] if pattern.startswith("**/") else pattern
    if pat.endswith("/**"):
        return f"/{pat[:-3]}/" in f"/{rel}"
    if "/" not in pat:
        return fnmatch.fnmatch(rel.rsplit("/", 1)[-1], pat)
    return fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(rel, pattern)


def available_rules(root: Path) -> Dict[str, Tuple[List[str], str]]:
    """name -> (globs, body). Project copies in .agents/rules win over the plugin's."""
    rules: Dict[str, Tuple[List[str], str]] = {}
    for base in _rule_dirs(root):
        for sub in ("languages", "database"):
            d = base / sub
            if not d.is_dir():
                continue
            for f in sorted(d.glob("*.md")):
                name = f"{sub}/{f.stem}"
                if name in rules:
                    continue
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                m = FRONTMATTER_RE.match(text)
                globs = _globs(m.group("head")) if m else []
                if globs:
                    rules[name] = (globs, text[m.end():].strip() if m else text)
    return rules


def rules_for(root: Path, files: List[str], already: List[str]) -> List[Tuple[str, str]]:
    """(name, message) for each rule set that matches a changed file and was not injected yet."""
    out: List[Tuple[str, str]] = []
    for name, (globs, body) in available_rules(root).items():
        if name in already:
            continue
        hits = [f for f in files if any(_matches(f, g) for g in globs)]
        if not hits:
            continue
        if len(body) > MAX_RULE_CHARS:
            body = body[:MAX_RULE_CHARS] + "\n[... see the full rules in " + name + ".md ...]"
        out.append((name, (
            f"[Antigravity Rules: {name}] You are changing {hits[0]}"
            + (f" and {len(hits) - 1} more" if len(hits) > 1 else "")
            + ". Follow these rules for this kind of file:\n" + body)))
    return out
