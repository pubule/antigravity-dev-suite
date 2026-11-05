# /dev — Magnitude-Aware SDLC Pipeline Suite

Deterministic, magnitude-aware SDLC pipeline for **Claude Code**.
Automates software engineering from idea to release-ready code by scaling ceremony (triage, brainstorming, design councils, structured planning, isolated TDD worktrees, adversarial code reviews, and quality gates) based on task magnitude.

Includes interactive visual documentation: see [`README.html`](./README.html).

---

## ⚡ Key Capabilities

- **Deterministic Routing Table:**
  - **TRIVIAL:** Quick fixes, typos, dependency bumps (skips councils and worktrees; executes fast verification and scoped audits).
  - **STANDARD:** New features, non-trivial bugs (brainstorming, implementation plans, parallel workflows, ship council).
  - **COMPLEX:** Architectural changes, new modules, security-sensitive work (Design Council, rigorous planning, dual adversarial reviews).
- **Enforced Quality Gates:**
  - **Gate G1:** Design Council GO mandatory for COMPLEX tasks.
  - **Gate G2:** Implementation plan saved to disk for STANDARD+.
  - **Gate G2.5:** Impeccable Quality Gate for coding standards, error handling, and test conventions.
  - **Gate G2.5b:** Resilience & Observability Strategy verification for greenfield code.
  - **Gate G2.6:** UI Quality Gate for frontend code (anti-pattern and accessibility scans).
  - **Gate G3:** Ship Council GO mandatory prior to documentation and release.
  - **Gate GT:** Production tracing must be recording before Phase 1 (only the user can waive it).
  - **Gate G2.5c:** Agent Tracing checklist for code that calls an LLM or runs a tool-calling loop (IS_AGENTIC).
- **Production Tracing (`dev-trace`):** every session records tool calls, reasoning steps, latency and failures through hooks, so a bad run is diagnosed from evidence instead of guessed. See [Production Tracing](#-production-tracing).
- **Parallel Workflow Engine:** Runs TDD tasks across isolated git worktrees in parallel, merges changes deterministically, runs self-healing auto-debug loops, and executes adversarial review refutation.
- **Session Recovery & Handoff:** State persistence in `.dev-pipeline-state.json` paired with a human-readable `HANDOFF.md` to safely resume interrupted tasks across `/clear`, compaction, or terminal restarts.

---

## 📦 Prerequisites

1. **Git** (available in system `PATH`)
2. **Node.js** (v18+ recommended; already required by Claude Code)
3. **Claude Code CLI** (`npm install -g @anthropic-ai/claude-code`)

---

## 🚀 Quickstart Installation (Option 2)

Setup scripts verify prerequisites, install required dependencies (`superpowers` and `llm-council`), and register the `/dev` suite.

### macOS / Linux
```bash
git clone <REPO_URL>
cd antigravity-dev-suite
chmod +x setup.sh
./setup.sh
```

### Windows (PowerShell)
```powershell
git clone <REPO_URL>
cd antigravity-dev-suite
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

### Or via Claude Code Marketplace
```bash
/plugin marketplace add <owner>/<repo>
/plugin install dev --marketplace <owner>/<repo>
```

---

## 🧩 Dependencies Installed by Setup

The setup script automatically wires together:

| Dependency | Type | Role in Pipeline |
|---|---|---|
| `superpowers@claude-plugins-official` | Claude Code Plugin | Brainstorming, plan generation, git worktree management, branch finalization |
| `llm-council` | Claude Code Skill | Multi-perspective Design Council (Phase 2) and Ship Council (Phase 9) |
| `dev` | Plugin / Skill | SDLC pipeline orchestrator, handoff detector hook, parallel workflow execution |

---

## 🛠️ Usage

Inside any Claude Code session in your project root:

```bash
# Interactive launch
/dev

# Or with task description
/dev implement retry with exponential backoff on HTTP client
```

### Resuming Interrupted Work

When a session is cleared or interrupted:
- The `SessionStart` hook detects any active `HANDOFF.md` in progress.
- Run `/dev`: the pipeline inspects state and prompts you to resume from the exact interrupted phase without repeating completed work.

---

## 🔭 Production Tracing

Stop guessing what the agent did. With the plugin installed, hooks record a trace of every Claude Code session, with no effort from the model:

| Recorded | How |
|---|---|
| Tool calls: name, redacted input summary, outcome, verbatim error | `PreToolUse` / `PostToolUse` / `PostToolUseFailure` hooks, cross-checked with the transcript |
| Latency of each tool call and each model call, token usage | hook and transcript timestamps |
| Reasoning step that led to each tool call | the visible thinking/text preceding the call in the transcript |
| `/dev` phases and gate verdicts | every write to `.dev-pipeline-state.json` |
| Subagents and Workflow agents (duration, outcome) | `SubagentStart/Stop` hooks, `devTrace` spans returned by `implement-and-review.js` |
| Nested AI calls from the shell (`claude -p`, `gemini -p`, `agy -p`, `codex exec`, ...): model, turns, tokens, cost, the nested agent's tool calls and errors, link to the child trace | Bash hooks + parsing of `--output-format json/stream-json` |

Traces live in `<git-common-dir>/dev-trace/<session>.jsonl`: one file per session, shared by all worktrees, never in the working tree. Secrets are redacted, file contents are never stored, and files older than 14 days are pruned.

```bash
D=~/.claude/plugins/.../skills/dev    # or wherever the dev skill is installed
node $D/dev-trace.js doctor             # is this session being traced?
node $D/dev-trace.js summary            # phases, per-tool avg/p95/max latency, failures + "why", slowest calls
node $D/dev-trace.js failures           # each failed call with its input, reasoning and verbatim error
node $D/dev-trace.js show --slow 10     # the 10 slowest calls on the timeline
node $D/dev-trace.js export > trace.json   # OTLP/JSON for Jaeger, Phoenix, Langfuse, Tempo
```

**How it is enforced in `/dev`:**
- **Gate GT:** Phase 0 runs `doctor`. An untraced run needs the user's explicit waiver.
- **Diagnose from the trace:** every debug, remediation, NO-GO and resume step starts from `dev-trace.js failures` and cites the verbatim error.
- **Stop check:** while a pipeline is active, if a test, build, lint or type-check command failed in the turn and was never re-run green, the Stop hook blocks once and lists it. The agent then has to fix it or say plainly that it still fails.
- **Ship Council** receives the trace summary. **Phase 11** reports `N tool calls, F failures (U unresolved)`.
- **Nested AI calls:** while a pipeline is active, a headless `agy`/`claude`/`gemini`/`codex`/`cursor-agent` call without structured output is denied, because its internals would be invisible (e.g. `agy -p "…" --output-format stream-json --print-timeout 15m`). The trace flags `agy` runs with no timeout, since its default is unlimited. CLIs without a JSON mode are still traced for latency and outcome, and flagged as "internals not traced".
- **Code you build (IS_AGENTIC):** if the change calls an LLM through an SDK or spawns a headless AI CLI (`claude -p`, `gemini -p`, `agy -p`, ...), or runs an agent loop, the design must include an Agent Tracing section (run id, LLM, tool and decision-step spans, error spans, redaction). Gate G2.5c verifies it with a real run.

| Variable | Effect |
|---|---|
| `DEV_TRACE=0` | disable recording |
| `DEV_TRACE_GATE=0` | disable the Stop check |
| `DEV_TRACE_CONTENT=summary\|full\|minimal` | how much input/reasoning text is kept (default `summary`) |
| `DEV_TRACE_DIR` | storage directory override |
| `DEV_TRACE_RETENTION_DAYS` | retention (default 14) |

> Tracing needs the hooks, so install the suite as a plugin. The bare-skill fallback copy does not trace, and `/dev` flags that at gate GT.

Tests: `node --test tests/*.test.js` (Node 18+, no dependencies).

---

## 🗑️ Uninstallation

- **macOS / Linux:** `./uninstall.sh`
- **Windows:** `powershell -ExecutionPolicy Bypass -File .\uninstall.ps1`

---

## 📄 License

MIT License. See [LICENSE](./LICENSE).
