#!/usr/bin/env python3
"""
Antigravity Handoff Generator (Claude Opus 5.5 Standard)
Serializes current agent session state, telemetry, and git context into a structured,
portable Markdown handoff briefing located in the system temporary directory.
100% Portable across macOS, Linux, and Windows 10/11.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from auto_debug_runner import (
        get_last_test_run,
        get_last_critic_run,
        get_last_syntax_error,
        safe_git_env,
    )
except ImportError:
    get_last_test_run = lambda: None
    get_last_critic_run = lambda: None
    get_last_syntax_error = lambda: None
    safe_git_env = lambda: dict(os.environ)

try:
    from critic_loop import SECRET_PATTERNS
except ImportError:
    SECRET_PATTERNS = [
        (re.compile(r'\b(?:sk-[a-zA-Z0-9_\-]{20,}|ghp_[a-zA-Z0-9]{20,}|github_pat_[a-zA-Z0-9_]{50,}|glpat-[a-zA-Z0-9_\-]{20,}|xox[baprs]-[0-9a-zA-Z]{10,48}|sk_live_[0-9a-zA-Z]{24,}|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16})\b'), "API key / token"),
        (re.compile(r'(?i)aws_secret_access_key\s*[:=]\s*[\'"]?[A-Za-z0-9/+=]{40}[\'"]?'), "AWS Secret Access Key"),
        (re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'), "Private Key"),
    ]


def redact_secrets(text: str) -> str:
    """Sanitizes text by replacing secrets and credentials with redacted placeholders. # safe-bounds"""
    if not text:
        return ""
    sanitized = text
    for pattern, _ in SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)
    return sanitized


def get_git_context(ws_dir: Path) -> Dict[str, Any]:
    """Extracts git branch, status, and last commit context."""
    ctx: Dict[str, Any] = {
        "is_git": False,
        "branch": "unknown",
        "last_commit": "None",
        "modified_files": [],
        "untracked_files": [],
    }

    try:
        # Check if inside git repository
        rev = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(ws_dir),
            capture_output=True,
            text=True,
            timeout=5,
            env=safe_git_env()
        )
        if rev.returncode != 0 or rev.stdout.strip() != "true":
            return ctx

        ctx["is_git"] = True

        # Current branch
        br = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(ws_dir),
            capture_output=True,
            text=True,
            timeout=5,
            env=safe_git_env()
        )
        if br.returncode == 0:
            ctx["branch"] = br.stdout.strip()

        # Last commit
        log_res = subprocess.run(
            ["git", "log", "-1", "--format=%h %s"],
            cwd=str(ws_dir),
            capture_output=True,
            text=True,
            timeout=5,
            env=safe_git_env()
        )
        if log_res.returncode == 0 and log_res.stdout.strip():
            ctx["last_commit"] = log_res.stdout.strip()

        # Status porcelain
        st = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(ws_dir),
            capture_output=True,
            text=True,
            timeout=5,
            env=safe_git_env()
        )
        if st.returncode == 0:
            for line in st.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    code, rel_path = parts
                    if code == "??":
                        ctx["untracked_files"].append(rel_path)
                    else:
                        ctx["modified_files"].append(rel_path)
    except Exception as e:
        sys.stderr.write(f"[handoff] Notice: git extraction failed: {e}\n")

    return ctx


def get_model_context_threshold(model_name: Optional[str] = None) -> int:
    """Returns the context window compaction threshold based on model architecture. # safe-bounds"""
    if not model_name:
        model_name = os.getenv("ANTIGRAVITY_MODEL") or os.getenv("GEMINI_MODEL") or "gemini"
    m = model_name.lower()
    if "flash" in m or "gemini" in m:
        return 1000000
    if "claude" in m or "sonnet" in m or "opus" in m:
        return 200000
    if "gpt-4o" in m or "gpt-4" in m or "o1" in m or "o3" in m:
        return 128000
    return 1000000


def get_context_occupancy(
    app_data_dir: Optional[str] = None,
    conversation_id: Optional[str] = None,
    model_name: Optional[str] = None
) -> Dict[str, Any]:
    """Extracts live context window occupancy and token telemetry from transcript. # safe-bounds"""
    app_data = Path(app_data_dir or os.getenv("ANTIGRAVITY_APP_DATA_DIR") or (Path.home() / ".gemini" / "antigravity-cli"))
    conv_id = conversation_id or os.getenv("ANTIGRAVITY_CONVERSATION_ID")
    threshold = get_model_context_threshold(model_name)

    transcript_path: Optional[Path] = None
    if conv_id:
        cand = app_data / "brain" / conv_id / ".system_generated" / "logs" / "transcript.jsonl"
        if cand.exists():
            transcript_path = cand

    # Only fall back to latest transcript if conv_id was not explicitly specified
    if not transcript_path and not conv_id:
        brain_dir = app_data / "brain"
        if brain_dir.is_dir():
            candidates = sorted(
                brain_dir.glob("*/.system_generated/logs/transcript.jsonl"),
                key=lambda x: x.stat().st_mtime if x.exists() else 0,
                reverse=True
            )
            if candidates:
                last_cand = candidates[0]
                # Only use transcript if updated within the last 30 minutes
                if abs(time.time() - last_cand.stat().st_mtime) < 1800:
                    transcript_path = last_cand

    telemetry: Dict[str, Any] = {
        "tracked": False,
        "input_tokens": 0,
        "cache_read_tokens": 0,
        "total_prompt_tokens": 0,
        "output_tokens": 0,
        "step_index": 0,
        "compaction_threshold": threshold,
        "occupancy_percentage": 0.0,
        "status": "UNKNOWN",
        "recommendation": "Context telemetry not available.",
    }

    if not transcript_path or not transcript_path.exists():
        return telemetry

    try:
        file_size = transcript_path.stat().st_size
        read_size = min(file_size, 65536)
        with open(transcript_path, "r", encoding="utf-8", errors="ignore") as f:
            if file_size > read_size:
                f.seek(file_size - read_size)
            lines = f.readlines()

        last_tokens: Optional[Dict[str, Any]] = None
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if "input_tokens" in data or "cache_read_tokens" in data:
                    last_tokens = data
            except Exception:
                continue

        if last_tokens:
            inp = int(last_tokens.get("input_tokens", 0) or 0)
            cache = int(last_tokens.get("cache_read_tokens", 0) or 0)
            out = int(last_tokens.get("output_tokens", 0) or 0)
            total = inp + cache
            step = int(last_tokens.get("step_index", 0) or 0)
            pct = round((total / threshold) * 100, 1)

            crit_threshold = int(threshold * 0.8)
            mod_threshold = int(threshold * 0.5)

            thresh_lbl = f"{threshold // 1000}k" if threshold < 1000000 else f"{threshold // 1000000}M"
            crit_lbl = f"{crit_threshold // 1000}k" if crit_threshold < 1000000 else f"{crit_threshold / 1000000:.1f}M"
            mod_lbl = f"{mod_threshold // 1000}k" if mod_threshold < 1000000 else f"{mod_threshold / 1000000:.1f}M"

            if total >= crit_threshold:
                status = "CRITICAL"
                rec = f"Context occupancy is high (≥{crit_lbl} tokens of {thresh_lbl}). High risk of compaction or slowdown. Hand off session now."
            elif total >= mod_threshold:
                status = "MODERATE"
                rec = f"Context occupancy is moderate (≥{mod_lbl} tokens of {thresh_lbl}). Consider /handoff at next milestone."
            else:
                status = "HEALTHY"
                rec = f"Context occupancy is healthy (<{mod_lbl} tokens of {thresh_lbl}). Normal execution."

            telemetry.update({
                "tracked": True,
                "input_tokens": inp,
                "cache_read_tokens": cache,
                "total_prompt_tokens": total,
                "output_tokens": out,
                "step_index": step,
                "compaction_threshold": threshold,
                "occupancy_percentage": pct,
                "status": status,
                "recommendation": rec,
            })
    except Exception as e:
        sys.stderr.write(f"[handoff] Context tracking notice: {e}\n")

    return telemetry


def infer_suggested_skills(
    git_ctx: Dict[str, Any],
    test_run: Optional[Dict[str, Any]],
    critic_run: Optional[Dict[str, Any]]
) -> List[Tuple[str, str]]:
    """Infers recommended Antigravity skills for the incoming session."""
    suggestions: List[Tuple[str, str]] = []

    test_failed = test_run and test_run.get("status") in ("FAIL", "ERROR")
    critic_failed = critic_run and critic_run.get("status") == "RETRY"

    if test_failed:
        suggestions.append(("/auto-debug", "Investigate and auto-heal failing test cases in closed loop."))
    if critic_failed:
        suggestions.append(("/code-review", "Audit and resolve detected static hygiene and security violations."))

    if not test_failed and not critic_failed:
        if git_ctx.get("modified_files") or git_ctx.get("untracked_files"):
            suggestions.append(("/commit", "Verify pre-commit gates and create atomic Conventional Commit."))
        suggestions.append(("/opus-dev", "Continue end-to-end implementation under Claude Opus 5.5 rigor."))
        suggestions.append(("/plan", "Decompose upcoming requirements into atomic sequential subtasks."))

    return suggestions


def generate_handoff_markdown(
    target_goal: str,
    summary: str,
    ws_dir: Path,
    git_ctx: Dict[str, Any],
    test_run: Optional[Dict[str, Any]],
    critic_run: Optional[Dict[str, Any]],
    suggested_skills: List[Tuple[str, str]],
    context_occupancy: Optional[Dict[str, Any]] = None
) -> str:
    """Generates an ASD-STE100 compliant markdown handoff document."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    branch = git_ctx.get("branch", "unknown")
    last_commit = git_ctx.get("last_commit", "None")

    lines = [
        "# 📋 Session Handoff Briefing",
        "",
        f"- **Timestamp**: {timestamp}",
        f"- **Workspace**: `{ws_dir.name}`",
        f"- **Git Branch**: `{branch}`",
        f"- **Last Commit**: `{last_commit}`",
        "",
        "---",
        "",
        "## 1. Objective & Target Goal",
        f"> {target_goal if target_goal else 'Continue current development iteration.'}",
        "",
    ]

    if summary:
        lines.extend([
            "## 2. Context & Implementation Notes",
            summary.strip(),
            "",
        ])

    lines.extend([
        "## 3. Telemetry & Verification State",
        "| Gate / Telemetry | Status | Details |",
        "| :--- | :--- | :--- |",
    ])

    # Test suite row
    if test_run:
        t_stat = test_run.get("status", "UNKNOWN")
        t_dur = test_run.get("duration_seconds", 0)
        lines.append(f"| **Test Suite** | `{t_stat}` | Duration: {t_dur}s |")
    else:
        lines.append("| **Test Suite** | `NONE` | No test run recorded in session |")

    # Critic loop row
    if critic_run:
        c_stat = critic_run.get("status", "UNKNOWN")
        c_viols = critic_run.get("violations_count", 0)
        lines.append(f"| **Critic Audit** | `{c_stat}` | Violations: {c_viols} |")
    else:
        lines.append("| **Critic Audit** | `NONE` | No critic audit recorded in session |")

    # Context occupancy row
    if context_occupancy and context_occupancy.get("tracked"):
        ctx_stat = context_occupancy.get("status", "UNKNOWN")
        ctx_tok = context_occupancy.get("total_prompt_tokens", 0)
        ctx_pct = context_occupancy.get("occupancy_percentage", 0.0)
        thresh = context_occupancy.get("compaction_threshold", 1000000)
        thresh_lbl = f"~{thresh // 1000}k" if thresh < 1000000 else f"~{thresh // 1000000}M"
        lines.append(f"| **Context Window** | `{ctx_stat}` | {ctx_tok:,} tokens ({ctx_pct}% of {thresh_lbl} threshold) |")
    else:
        lines.append("| **Context Window** | `NONE` | Transcript token telemetry not available |")

    lines.append("")

    # Modified files section
    mod_files = git_ctx.get("modified_files", [])
    untracked = git_ctx.get("untracked_files", [])

    if mod_files or untracked:
        lines.extend([
            "## 4. Modified Files & Pointers",
            "> [!NOTE] File paths are linked relative to workspace. File contents are not duplicated to preserve token budget.",
            "",
        ])
        for f in mod_files:
            lines.append(f"- `modified`: [{f}](file:///{ws_dir / f})")
        for f in untracked:
            lines.append(f"- `untracked`: [{f}](file:///{ws_dir / f})")
        lines.append("")

    # Architectural Constraints
    lines.extend([
        "## 5. Architectural Constraints & Dead-Ends",
        "- **KISS & YAGNI**: Reject speculative abstractions and premature caching.",
        "- **Zero Comment Stripping**: Preserve all existing explanatory documentation and docstrings.",
        "- **Strict TDD**: Write failing unit or integration tests before modifying production code.",
        "- **Dual-Gate Completion**: Ensure both tests (`PASS`) and critic loop (`PASS`) succeed prior to completing.",
        "",
    ])

    # Suggested skills
    if suggested_skills:
        lines.extend([
            "## 6. Suggested Skills for Next Agent Session",
            "| Command | Objective |",
            "| :--- | :--- |",
        ])
        for cmd, reason in suggested_skills:
            lines.append(f"| `{cmd}` | {reason} |")
        lines.append("")

    return "\n".join(lines)


def create_handoff_file(
    target_goal: str = "",
    summary: str = "",
    workspace_dir: Optional[Path] = None,
    output_path: Optional[Path] = None,
    suggested_skills_override: Optional[List[Tuple[str, str]]] = None
) -> Dict[str, Any]:
    """Generates and writes session handoff file to system temporary directory or specified path."""
    ws = Path(workspace_dir or Path.cwd()).resolve()

    clean_goal = redact_secrets(target_goal)
    clean_summary = redact_secrets(summary)

    git_ctx = get_git_context(ws)
    test_run = get_last_test_run()
    critic_run = get_last_critic_run()
    ctx_occ = get_context_occupancy()

    if suggested_skills_override is not None:
        skills = suggested_skills_override
    else:
        skills = infer_suggested_skills(git_ctx, test_run, critic_run)

    content = generate_handoff_markdown(
        target_goal=clean_goal,
        summary=clean_summary,
        ws_dir=ws,
        git_ctx=git_ctx,
        test_run=test_run,
        critic_run=critic_run,
        suggested_skills=skills,
        context_occupancy=ctx_occ
    )

    if output_path:
        target_file = Path(output_path).resolve()
        target_file.parent.mkdir(parents=True, exist_ok=True)
    else:
        temp_dir = Path(tempfile.gettempdir())
        time_tag = int(time.time())
        hash_tag = hashlib.md5(f"{clean_goal}:{time_tag}".encode("utf-8")).hexdigest()[:6]
        target_file = temp_dir / f"agy_handoff_{time_tag}_{hash_tag}.md"

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(content)

    return {
        "status": "SUCCESS",
        "handoff_file": str(target_file),
        "target_goal": clean_goal,
        "suggested_skills": [cmd for cmd, _ in skills],
        "context_occupancy": ctx_occ,
        "content_length": len(content),
    }


def main():
    parser = argparse.ArgumentParser(description="Antigravity Session Handoff Generator (Claude Opus 5.5 Standard)")
    parser.add_argument("goal", nargs="?", default="", help="Target goal or focus for the next session")
    parser.add_argument("--summary", "-s", default="", help="Contextual summary or technical implementation notes")
    parser.add_argument("--output", "-o", default="", help="Optional explicit output file path")
    parser.add_argument("--stats", "--context", dest="stats", action="store_true", help="Print live context window occupancy and token telemetry")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON format")

    args = parser.parse_args()

    if args.stats:
        stats = get_context_occupancy()
        thresh = stats.get("compaction_threshold", 1000000)
        thresh_lbl = f"~{thresh // 1000}k" if thresh < 1000000 else f"~{thresh // 1000000}M"
        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            print("📊 Context Window Occupancy:")
            print(f"  - Total Prompt Tokens: {stats['total_prompt_tokens']:,} (Input: {stats['input_tokens']:,}, Cache: {stats['cache_read_tokens']:,})")
            print(f"  - Output Tokens:       {stats['output_tokens']:,}")
            print(f"  - Step Index:          {stats['step_index']}")
            print(f"  - Occupancy ({thresh_lbl}):   {stats['occupancy_percentage']}% [{stats['status']}]")
            print(f"  - Recommendation:      {stats['recommendation']}")
        return

    out_p = Path(args.output).resolve() if args.output else None

    res = create_handoff_file(
        target_goal=args.goal,
        summary=args.summary,
        output_path=out_p
    )

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"✅ Session handoff generated: {res['handoff_file']}")
        print(f"📋 Suggested next skills: {', '.join(res['suggested_skills'])}")


if __name__ == "__main__":
    main()
