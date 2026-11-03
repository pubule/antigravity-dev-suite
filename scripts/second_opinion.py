#!/usr/bin/env python3
"""Optional second opinion at Stop: a stronger model reviews the finished diff.

Turned on per project in .agents/agy.json:

    "second_opinion": {"provider": "anthropic", "model": "claude-opus-5-5"}
    "second_opinion": {"provider": "gemini", "model": "gemini-2.5-pro"}

The API key is read from the environment only (ANTHROPIC_API_KEY, or GEMINI_API_KEY /
GOOGLE_API_KEY; "api_key_env" names another variable). It is never written to disk.
The reviewer gets the acceptance criteria and the diff, and answers with JSON
findings. Blocker and major findings become a one-time review for agy. API errors,
timeouts and refusals never block: they become a note.

Python 3.9+ standard library only (urllib). Works on macOS, Linux and Windows.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from base_worktree import git  # noqa: E402

logger = logging.getLogger("second_opinion")

DEFAULT_MODELS = {"anthropic": "claude-opus-5-5", "gemini": "gemini-2.5-pro"}
KEY_ENVS = {"anthropic": ("ANTHROPIC_API_KEY",), "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY")}
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
SKIP_DIFF = ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "uv.lock", "Cargo.lock", "go.sum")
BLOCKING = ("blocker", "major")

SYSTEM_PROMPT = (
    "You are a senior staff engineer reviewing a change written by a fast coding agent. The change "
    "already passes its tests, linters and type checks. Find the defects those checks miss: wrong "
    "logic, unhandled edge cases and error paths, race conditions, security problems, broken callers "
    "or contracts, tests that do not really test the changed behaviour, and anything that does not "
    "meet the acceptance criteria. Ignore style and naming. Report only problems you are confident "
    "about, each with the file, the line in the new version (0 if unknown), and a concrete fix. "
    "Severity: blocker = wrong result, data loss or security hole; major = a real bug in a plausible "
    "case or a criterion not met; minor = everything else. If the change is correct, return an "
    "empty list."
)

SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["blocker", "major", "minor"]},
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "issue": {"type": "string"},
                    "fix": {"type": "string"},
                },
                "required": ["severity", "file", "line", "issue", "fix"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "findings"],
    "additionalProperties": False,
}


class OpinionError(Exception):
    """The reviewer could not give an answer (network, key, refusal, bad JSON)."""


def settings(cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    raw = cfg.get("second_opinion")
    if not raw:
        return None
    if raw is True:
        raw = {}
    if not isinstance(raw, dict) or raw.get("enabled") is False:
        return None
    provider = str(raw.get("provider") or "anthropic").lower()
    if provider not in DEFAULT_MODELS:
        return None
    return {
        "provider": provider,
        "model": str(raw.get("model") or DEFAULT_MODELS[provider]),
        "key_envs": (str(raw["api_key_env"]),) if raw.get("api_key_env") else KEY_ENVS[provider],
        "max_diff_chars": int(raw.get("max_diff_chars", 60000)),
        "timeout": int(raw.get("timeout", 180)),
        "effort": str(raw.get("effort") or "high"),
        "url": str(raw.get("url") or ""),  # a compatible gateway or proxy
    }


def api_key(conf: Dict[str, Any]) -> str:
    for name in conf["key_envs"]:
        val = os.environ.get(name, "").strip()
        if val:
            return val
    return ""


# ------------------------------------------------------------------- the diff

def build_diff(root: Path, base: str, files: List[str], limit: int) -> str:
    parts: List[str] = []
    tracked: List[str] = []
    for rel in files:
        if rel.rsplit("/", 1)[-1] in SKIP_DIFF:
            continue
        code, _ = git(["ls-files", "--error-unmatch", rel], root)
        if code == 0:
            tracked.append(rel)
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        parts.append(f"--- /dev/null\n+++ b/{rel}  (new file)\n" + "\n".join("+" + ln for ln in text.splitlines()))
    if tracked:
        code, out = git(["diff", "--no-color", "-U5", base or "HEAD", "--"] + tracked, root)
        if code == 0 and out.strip():
            parts.insert(0, out)
    diff = "\n".join(parts)
    if len(diff) > limit:
        diff = diff[:limit] + f"\n[... diff cut at {limit} characters ...]"
    return diff


def build_prompt(criteria: str, diff: str) -> str:
    crit = criteria.strip() or "(the agent wrote no acceptance criteria)"
    return (
        "Acceptance criteria written by the agent (the box marks are its own claims, verify them):\n"
        f"<criteria>\n{crit}\n</criteria>\n\n"
        f"The change, as a unified diff against the commit the task started from:\n<diff>\n{diff}\n</diff>\n\n"
        "Return your review as JSON with this shape: "
        '{"summary": "<one sentence>", "findings": [{"severity": "blocker|major|minor", '
        '"file": "<path>", "line": <int>, "issue": "<what is wrong>", "fix": "<how to fix it>"}]}'
    )


# -------------------------------------------------------------------- providers

def _post(url: str, headers: Dict[str, str], body: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers=dict(headers, **{"content-type": "application/json"}))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec: fixed https endpoints
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        raise OpinionError(f"HTTP {e.code}: {detail}") from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise OpinionError(str(e)) from e


def ask_anthropic(conf: Dict[str, Any], key: str, prompt: str) -> str:
    body = {
        "model": conf["model"],
        "max_tokens": 16000,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}],
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": conf["effort"], "format": {"type": "json_schema", "schema": SCHEMA}},
    }
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    data = _post(conf["url"] or ANTHROPIC_URL, headers, body, conf["timeout"])
    stop = data.get("stop_reason")
    if stop == "refusal":
        raise OpinionError("the model declined to review this change")
    if stop == "max_tokens":
        raise OpinionError("the review was cut off (max_tokens)")
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    if not text.strip():
        raise OpinionError(f"empty answer (stop_reason={stop})")
    return text


def ask_gemini(conf: Dict[str, Any], key: str, prompt: str) -> str:
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    url = (conf["url"] or GEMINI_URL).format(model=urllib.request.quote(conf["model"], safe=""))
    data = _post(url, {"x-goog-api-key": key}, body, conf["timeout"])
    cands = data.get("candidates") or []
    if not cands:
        reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
        raise OpinionError(f"no answer ({reason})")
    parts = (cands[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    if not text.strip():
        raise OpinionError(f"empty answer (finishReason={cands[0].get('finishReason')})")
    return text


def parse_findings(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[raw.find("{"):]
    start, end = raw.find("{"), raw.rfind("}")
    try:
        data = json.loads(raw[start:end + 1] if start >= 0 and end > start else raw)
    except ValueError as e:
        raise OpinionError(f"the answer is not JSON: {e}") from e
    findings = [f for f in data.get("findings") or [] if isinstance(f, dict)]
    return str(data.get("summary") or ""), findings


def review(root: Path, base: str, files: List[str], criteria: str, cfg: Dict[str, Any]
           ) -> Tuple[str, List[Dict[str, Any]], str]:
    """Returns (status, blocking findings, note). status: off | skipped | ok | issues."""
    conf = settings(cfg)
    if conf is None:
        return "off", [], ""
    key = api_key(conf)
    if not key:
        return "skipped", [], f"Second opinion skipped: set {' or '.join(conf['key_envs'])} in the environment agy runs in."
    diff = build_diff(root, base, files, conf["max_diff_chars"])
    if not diff.strip():
        return "skipped", [], "Second opinion skipped: empty diff."
    ask = ask_anthropic if conf["provider"] == "anthropic" else ask_gemini
    try:
        summary, findings = parse_findings(ask(conf, key, build_prompt(criteria, diff)))
    except OpinionError as e:
        return "skipped", [], f"Second opinion ({conf['model']}) unavailable: {e}"
    blocking = [f for f in findings if str(f.get("severity", "")).lower() in BLOCKING]
    minor = len(findings) - len(blocking)
    note = f"Second opinion ({conf['model']}): {summary or 'no summary'}" + (f" ({minor} minor point(s) not shown)" if minor else "")
    return ("issues" if blocking else "ok"), blocking, note


def format_findings(model: str, findings: List[Dict[str, Any]]) -> str:
    lines = [f"A stronger reviewer ({model}) read your diff and found these problems:"]
    for f in findings[:12]:
        loc = f"{f.get('file', '?')}:{f.get('line', 0)}" if f.get("line") else str(f.get("file", "?"))
        lines.append(f"- [{f.get('severity', '?')}] {loc}: {f.get('issue', '').strip()}")
        if f.get("fix"):
            lines.append(f"  Fix: {str(f['fix']).strip()}")
    lines.append("Check each point against the code. Fix the real ones (with a test). If a point is "
                 "wrong, say why in your answer.")
    return "\n".join(lines)
