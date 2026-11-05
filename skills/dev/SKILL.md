---
name: dev
description: "Magnitude-aware SDLC pipeline. Classifies tasks as trivial/standard/complex, runs proportional ceremony. Graduated remediation, state persistence, rollback, production tracing of every run (tool calls, reasoning, latency, failures). On every invocation it first looks for HANDOFF.md / .dev-pipeline-state.json in the project root to resume interrupted work after a /clear or new session. Invoke: /dev or /dev <description>."
---

# /dev — Magnitude-Aware SDLC Pipeline

Orchestrate development from idea to ship-ready code. Magnitude determines ceremony — a typo fix skips councils; a new module gets the full pipeline.

## Routing Table

Single source of truth. Derive all skip/run decisions from this table.

| Phase | Skill | TRIVIAL | STANDARD | COMPLEX |
|-------|-------|---------|----------|---------|
| 0. Triage | — | run | run | run |
| 1. Brainstorm | `superpowers:brainstorming` | skip | run | run |
| 2. Design Council | `llm-council` | skip | skip | run |
| 3. Plan | `superpowers:writing-plans` | skip | run | run |
| 4. Worktree | `superpowers:using-git-worktrees` | skip | run | run |
| 5-8. Implement+Verify+Review+Audit | `Workflow(implement-and-review.js)` — parallel agents, adversarial verify, deterministic loops | run (direct, no workflow) | run (workflow) | run (workflow) |
| 8.5. Impeccable Quality Gate | Impeccable skills + Resilience & Observability check + Agent Tracing check if IS_AGENTIC (see §Impeccable Quality Gate) | run | run | run |
| 8.6. UI Quality Gate | `Skill(impeccable)` + `detect` CLI (see §UI Quality Gate) | run (detect only, if HAS_FRONTEND) | run (if HAS_FRONTEND) | run (if HAS_FRONTEND) |
| 9. Ship Council | `llm-council` | skip | run | run |
| 10. Docs | — | run | run | run |
| 10.5. Knowledge Quiz | — | run | run | run |
| 11. Finish | `superpowers:finishing-a-development-branch` (or simple commit for trivial) | run | run | run |

**TDD skip criteria (trivial):** config-only, docs-only, dependency bumps, style-only with no logic.

**PHASE GATE ENFORCEMENT (MANDATORY):**

Do NOT proceed to the next phase until the current phase is complete. Before entering any phase marked `run` in the routing table for the current magnitude, verify the gate:

| Gate | Condition | Blocked Phase |
|------|-----------|---------------|
| G1 | COMPLEX: `Skill(llm-council)` invoked AND verdict is GO | Phase 3 (Plan) |
| G2 | STANDARD+: Plan file exists in `docs/superpowers/plans/` | Phase 4 (Worktree) |
| G2.5 | ALL: Impeccable Quality Gate passed (all applicable skills invoked, no CRITICAL findings) | Phase 8.6 (UI Quality Gate) |
| G2.5b | IS_GREENFIELD: Resilience & Observability checklist passed (no CRITICAL gaps in error handling / logging) | Phase 8.6 (UI Quality Gate) |
| G2.6 | STANDARD+ with HAS_FRONTEND: UI Quality Gate passed (detect clean, audit score >= 14/20, no P0 findings) | Phase 9 (Ship Council) |
| G3 | STANDARD+: `Skill(llm-council)` invoked for ship review AND verdict is GO | Phase 10 (Docs) |
| GT | ALL: production tracing is recording this session (`dev-trace.js doctor` → OK), or the user explicitly accepted running untraced | Phase 1 (any phase after Triage) |
| GA | IS_AGENTIC: the user answered the AI Observability Proposal (`state.agentObservability.decision` set, `answeredBy: "user"`) | Phase 3 (Plan) — and, on the TRIVIAL path, any implementation step |
| G2.5c | IS_AGENTIC: Agent Tracing checklist passed for the items the user chose (every LLM call, tool call, decision step and failure of the code being built emits a trace span) | Phase 8.6 (UI Quality Gate) |

If a gate check fails, STOP and execute the missing phase. Do NOT skip it.
Do NOT rationalize skipping with "this is straightforward" or "the design is clear."
The routing table is the authority — if it says `run`, you MUST run it.

---

## Phase Entry Protocol (MANDATORY — execute before EVERY phase)

This is the enforcement mechanism. It is NOT optional. It is NOT skippable. Execute these 5 steps before entering ANY phase (including Phase 0 for state file creation).

```
BEFORE entering Phase N:
1. READ `.dev-pipeline-state.json`
   - If file doesn't exist AND N > 0 → ⛔ BLOCKED: Phase 0 not completed. Execute Phase 0 now.
2. VERIFY `completedPhases` includes ALL prior phases marked `run` for current magnitude
   - Compare against routing table. If any prior `run` phase is missing → ⛔ BLOCKED.
3. VERIFY gate conditions (check gate table above)
   - G1: if N >= 3 && COMPLEX → state.gates.designCouncilGO must be true
   - G2: if N >= 4 && STANDARD+ → state.planFile must exist
   - G2.5: if N >= 8.6 → state.impeccableGate.passed must be true
   - G2.5b: if N >= 8.6 && IS_GREENFIELD → state.observabilityGate.passed must be true
   - G2.6: if N >= 9 && HAS_FRONTEND → state.uiQualityGate.passed must be true
   - G3: if N >= 10 && STANDARD+ → state.gates.shipCouncilGO must be true
   - GT: if N >= 1 → state.tracing.active must be true OR state.tracing.waivedBy must be set
   - GA: if N >= 3 && IS_AGENTIC → state.agentObservability.decision must be set by the user
   - G2.5c: if N >= 8.6 && IS_AGENTIC → state.agentTraceGate.passed must be true
4. WRITE to state file: { currentPhase: N, enteredAt: <now> }
5. ANNOUNCE to user: "▶ Phase N: [name] — prerequisites verified ✓"
```

**On ANY check failure:**
```
Print: "⛔ BLOCKED: Phase [N] requires [missing phase/gate]. Executing now."
Execute the missing phase. Do NOT proceed past the block.
```

**AFTER completing ANY phase:** refresh `HANDOFF.md` in the project root (see §Handoff File). Same moment you update `.dev-pipeline-state.json`. Non-negotiable — the state file is machine state, `HANDOFF.md` is the human/post-`/clear` context.

**BEFORE entering ANY phase:** if `HANDOFF.md` is not on disk, create it before proceeding (backfill from the state file if that is all you have — see Phase 0 Step 0a). Missing is always a bug to fix on the spot, never a reason to skip. This makes the file self-healing: a pipeline started by an older version of this skill, or one whose handoff was deleted, acquires one at the next phase boundary.

**This protocol is NON-NEGOTIABLE.** If you find yourself about to enter a phase without running these 5 steps, STOP. You are about to skip enforcement.

---

## Rationalization Firewall

These are the EXACT rationalizations that cause phase skipping. If you catch yourself thinking ANY of these, you are about to violate the pipeline. STOP and follow the routing table.

| Rationalization | Correct Action |
|----------------|----------------|
| "The code is simple enough to skip brainstorming" | Run brainstorming. Routing table says `run`. |
| "I already know the plan" | Write the plan file anyway. Gate G2 requires it. |
| "The design is obvious, council is overkill" | Council it anyway. You are not the judge of obvious. |
| "Tests would be redundant here" | Write them anyway. CLAUDE.md mandates TDD. |
| "The user seems in a hurry" | Pipeline protects quality. Run every phase. |
| "I'll come back to this phase later" | No. Phases are sequential. Execute now. |
| "This phase didn't produce useful output last time" | Irrelevant. Each invocation is independent. Run it. |
| "The code already exists, just needs finishing" | Still run ALL remaining phases in order. |
| "I can combine these phases to save time" | No. Each phase has its own gate. Run each separately. |
| "Context is running low, I'll skip the rest" | See Context Exhaustion Protocol below. Never silently skip. |
| "The quality gate passed in degraded mode, that counts" | No. Degraded = not validated. Note in state, don't claim pass. |
| "I already loaded these skills earlier" | Reload. Skills may have changed. Phase 8.5 requires fresh load. |
| "This is a fresh task, no need to look for HANDOFF.md" | Look anyway. Phase 0 Step 0a is unconditional. You have no memory of a prior session. |
| "I remember what we were doing" | After a `/clear` you do not. Read `HANDOFF.md`, don't reconstruct from vibes. |
| "Error handling can be added later" | Later never comes. G2.5b is a gate, not a suggestion. Design it in Phase 1. |
| "It's a small script, logging is overkill" | Propose the proportional subset (§Resilience & Observability Design) and let the user cut it. Silence is not a decision. |
| "The happy path works, that's the feature" | The feature includes what happens when it doesn't. Failure paths get tests. |
| "The library handles errors for me" | Verify it. Most clients default to no timeout and swallow nothing usefully. |
| "I'll wrap everything in one try/catch at the top" | That's a crash log, not error handling. Boundaries are per §Resilience & Observability Design point 2. |
| "I know why it failed" | You have a hypothesis. Run `dev-trace.js failures`, quote the verbatim error and the call that produced it, then fix. |
| "The tests passed earlier, no need to re-run" | The trace shows the last run of each command. If the last run of the verification command is red, it is red. |
| "Tracing is noise for this small task" | It costs nothing: hooks record it. Reading it costs one command. The `GT` gate applies to every magnitude. |
| "It's an LLM feature, the model output is the log" | Model output is not a trace. An agent you can't trace is an agent you'll debug by guessing (G2.5c). |

---

## Context Exhaustion Protocol

If context window is running low and phases remain:

1. **ANNOUNCE** which phases are incomplete: "⚠️ Context running low. Phases [N, M, ...] not yet executed."
2. **WRITE** current pipeline state to `.dev-pipeline-state.json` with all completed phases and gate results
2b. **WRITE** a full `HANDOFF.md` (see §Handoff File) — this is the highest-value moment for it. After a `/clear` or compaction, `HANDOFF.md` is the only surviving context.
3. **TELL** user: "Pipeline paused at Phase N. Resume with `/dev` to continue from Phase N. Context saved to `<project-root>/HANDOFF.md`."
4. **Do NOT** silently skip remaining phases
5. **Do NOT** compress multiple phases into one to "fit"
6. **Do NOT** claim phases are complete if they haven't been executed

Silently skipping phases due to context limits is the MOST COMMON enforcement failure. This protocol exists specifically to prevent it.

---

**Audit triggers (by file type):** HAS_FRONTEND (`.html/.css/.scss/.tsx/.jsx/.vue/.component.ts`) → security + a11y + verify + **UI Quality Gate (Phase 8.6)**. HAS_API (routes/controllers/middleware) → security. HAS_PERF (DB queries, caching, I/O) → perf-check.

**IS_GREENFIELD trigger (by scope, not file type):** set when the task creates a **new tool, new app, new service, new CLI, new module/package, or a substantial feature** (new entrypoint, new external integration, new background job, new persistence surface, or ≳3 new source files forming a new unit). Also set on any task whose changes introduce a new process boundary — HTTP client/server, DB connection, filesystem/network I/O, subprocess, queue consumer.

When IS_GREENFIELD:
- Phase 1 MUST produce an **Error & Logging Strategy** section (see §Resilience & Observability Design).
- Phase 3 plan MUST contain an **Errors & Observability** task group.
- Phase 8.5 runs the **Resilience & Observability checklist** as a blocking sub-gate (G2.5b).

**IS_AGENTIC trigger:** set when the change adds or modifies code that calls an LLM in any form:
- **SDK / HTTP API:** Anthropic, Claude Agent SDK, OpenAI, Google GenAI, Vercel AI SDK, LangChain/LangGraph, LlamaIndex, or direct HTTP calls to a model endpoint.
- **Headless AI CLI as a subprocess:** `claude -p`, `gemini -p`, `agy -p`, `codex exec`, `cursor-agent -p`, `ollama run`, etc., from code, scripts, Makefiles, CI jobs or git hooks.
- **Agent constructs:** a tool-calling / agent loop, sub-agent orchestration, retrieval for a model, or tool / MCP server definitions for a model.

Grep the diff for SDK imports and for these CLI names in `spawn`/`exec`/`subprocess`/shell lines. When in doubt, set it. The Stop hook also scans the diff (and untracked files) on every turn: if it finds SDK imports or headless AI CLI calls (`claude -p`, `gemini -p`, `agy -p`, `codex exec`, ...) while `agentObservability.decision` is unset, it blocks and tells you to ask — so IS_AGENTIC detected mid-implementation still reaches the user. When IS_AGENTIC:
- **ASK THE USER the AI Observability Proposal** (§AI Observability Proposal) before planning — or before implementing on the TRIVIAL path. Gate GA. Never decide it for them.
- Phase 1 design doc MUST contain an **Agent Tracing** section (§Agent Tracing Design) covering what the user chose.
- Phase 3 plan MUST contain a **Tracing** task group (tracer setup first, then spans per LLM call / tool call / step, then failure-path tests that assert the error span exists).
- Phase 8.5 runs the **Agent Tracing checklist** as blocking sub-gate G2.5c.

Not greenfield (edits inside an existing unit with an established error/log convention): follow the existing convention, no extra gate. If the existing convention is *absent*, say so and treat the change as greenfield for the touched surface.

**Impeccable skill loading during implementation:** When writing code in Phases 5-8, load applicable impeccable `global-*` skills BEFORE coding. These inform coding style, conventions, error handling, and validation patterns. Phase 8.5 enforces compliance — loading early prevents rework. **For HAS_FRONTEND changes:** also consult `Skill(impeccable, "harden <target>")` guidance during implementation for edge cases, i18n, error states, and text overflow. Hardening during implementation is cheaper than remediating after Phase 8.6. **For IS_GREENFIELD:** keep the approved Error & Logging Strategy open while coding — write the error types and logger setup *first*, before the feature logic, so every later path has something to use. Retrofitting is what produces `catch {}`.

---

## Production Tracing (MANDATORY — gate GT)

Stop guessing what the agent did. Every session with the `dev` plugin installed records a production trace of its own run through hooks — automatically, not by asking the model to remember:

| Recorded | Source | Use it to answer |
|---|---|---|
| Every tool call: name, redacted input summary, outcome, error text | `PreToolUse` / `PostToolUse` / `PostToolUseFailure` hooks + transcript `tool_result` | "What exactly did it run, and what did it get back?" |
| Latency of every tool call and every model call, token usage | hook timestamps + transcript timestamps/usage | "Where did the 20 minutes go?" |
| Reasoning step before each tool call (visible thinking/text) | transcript | "Why did it decide to do that?" |
| Pipeline phases and gate verdicts | writes to `.dev-pipeline-state.json` | "Which phase was it in when it went wrong? Was the gate really GO?" |
| Subagents and Workflow agents (per-agent duration + outcome) | `SubagentStart/Stop` + `devTrace` returned by `implement-and-review.js` | "Which parallel agent failed or stalled?" |
| Nested AI calls run from the shell: `claude -p`, `gemini -p`, `agy -p`, `codex exec`, `cursor-agent -p`, ... — model, turns, tokens, cost, the nested agent's own tool calls and errors, link to the child session's trace | Bash hooks + parsing of `--output-format json/stream-json` | "What did the model I called from the shell actually do, and why did it fail?" |

Storage: `<git-common-dir>/dev-trace/<session>.jsonl` (shared by all worktrees, never in the working tree, never committed). Secrets are redacted and file contents are never stored. Retention 14 days.

**CLI** — `<skill_dir>` is the directory of this `SKILL.md` (fallback `~/.claude/skills/dev`):
```bash
node <skill_dir>/dev-trace.js doctor            # is this session being traced?
node <skill_dir>/dev-trace.js summary [session] # phases, per-tool latency (avg/p95/max), failures with "why", slowest calls
node <skill_dir>/dev-trace.js failures [session]# every failed call: input, reasoning that led to it, verbatim error, retries
node <skill_dir>/dev-trace.js show [session] [--failures] [--slow N]   # chronological timeline
node <skill_dir>/dev-trace.js export [session] > trace.json            # OTLP/JSON for Jaeger / Phoenix / Langfuse / Tempo
```

**Rules (non-negotiable):**
1. **Diagnose from the trace, not from memory.** Before any debug step — verify failure, review/audit remediation, council NO-GO, Workflow `FAILED`, or resuming a handoff — run `dev-trace.js failures` (or `summary`) and quote the verbatim error and the trace call number in your reasoning. A fix that does not cite the evidence it is fixing is a guess.
2. **Narrate decisions in one line.** Hidden thinking is not always persisted, so the trace's "why" comes from what you write. Before each phase entry, each fix and each gate verdict, write one visible line: `Decision: <what> — because <evidence>`. It costs a sentence and makes every later diagnosis possible.
3. **The last run counts.** A verification command (tests, build, lint, type check) whose last run in the turn is red is red. The Stop hook enforces it: if one failed and was never re-run green, it blocks once and lists them. Fix and re-run the SAME command, or say plainly that it still fails and record it in `HANDOFF.md`.
4. **Never claim a result the trace contradicts.** "Tests pass", "build is green", "council said GO" must match the trace. If they do not, the trace wins.
5. **Nested AI calls are traced too.** When you call another model from the shell during the pipeline (second opinions, councils, code generation with `claude -p`, `gemini -p`, `agy -p`, `codex exec`):
   - always request structured output and keep that JSON on stdout or `tee` it, so the trace can parse turns, tokens, tool calls and errors. While a pipeline is active the PreToolUse hook **denies** `claude`/`gemini`/`agy`/`codex`/`cursor-agent` headless calls without it:
     - `agy -p "…" --output-format stream-json --print-timeout 15m` (or `json`). Check `status == "SUCCESS"`, not just the exit code: a permission soft-denial exits `0`. The default `--print-timeout` is `0s`, which means no limit, so always set it.
     - `claude -p "…" --output-format stream-json --verbose` (or `json`). Check `is_error` / `subtype`, e.g. `error_max_turns`.
     - `gemini -p "…" --output-format json` (or `stream-json`). Exit codes: `1` API error, `42` bad input, `53` turn limit.
     - `codex exec --json "…"`. Check `turn.failed` / `error` events.
   - for CLIs without a structured mode: never discard stderr, never `|| true`, set a timeout, and check the exit code. The trace records latency and outcome and flags the call as "internals not traced";
   - run them from the project directory so a nested `claude -p` writes its own trace next to yours (`summary` links it as the child session);
   - after the call, check `dev-trace.js summary` → *Nested AI calls* before using the output. A nested run that hit `error_max_turns` or had tool errors is not a valid answer.
6. **Tracing stays on.** Do not set `DEV_TRACE=0` or `DEV_TRACE_GATE=0` yourself; only the user can, and it is recorded as a waiver.

---

## Phase 0: Triage

### Step 0a: Resume check (ALWAYS FIRST — before reading args, before asking anything)

`/dev` is frequently invoked after a `/clear` or a new session, with zero memory of prior work. Assume that is the case until proven otherwise. Do NOT start a fresh pipeline before this check.

1. **Resolve the project root** (see §Handoff File — path resolution). Do this BEFORE anything else; everything below depends on it. If args mention files/paths, resolve from those; otherwise from cwd.
2. **Look for prior-session artifacts** — search the project root, then upward to the git toplevel, then in sibling worktrees (`git worktree list`):
```bash
ls -la "$ROOT"/.dev-pipeline-state.json "$ROOT"/HANDOFF.md 2>/dev/null
git worktree list 2>/dev/null
```
   If neither exists at the root, do ONE bounded search before giving up:
```bash
find "$ROOT" -maxdepth 3 -name HANDOFF.md -not -path '*/node_modules/*' 2>/dev/null
```
3. **If `HANDOFF.md` is found → READ IT IN FULL before doing anything else.** Not a skim, not the headings. It is the cheapest context you will ever get. Read `.dev-pipeline-state.json` too if present.
4. **Reconcile with the user's current request:**

Compare the recorded task against the user's current request. "Same task" includes re-descriptions in different words and a bare `/dev` with no args; only treat it as different when the subject matter clearly does not match.

| Found | Recorded task vs request | Action |
|---|---|---|
| `HANDOFF.md`, Status IN PROGRESS/PAUSED | same | Show task, phase N, next step, open questions. Ask: "Resume from Phase N? [Y / Restart / New task]" |
| `HANDOFF.md`, Status IN PROGRESS/PAUSED | different | Do NOT resume. Say what the stale pipeline was. Rename to `HANDOFF.prev.md`, then Step 0b for the new task |
| `HANDOFF.md`, Status DONE | any | Not a resume. Read it as prior context (decisions, dead ends, commands still apply), then Step 0b |
| state file only, no `HANDOFF.md` | same | Resume from the state file, and **backfill `HANDOFF.md` immediately** (see Backfill below) before touching any phase |
| state file only, no `HANDOFF.md` | different | Stale pipeline from an older session. Backfill `HANDOFF.md` from it anyway (cheap, preserves the record), report it, ask: A) resume the old task, B) archive it (`HANDOFF.prev.md`, delete state file) and start the new one, C) abort |
| `HANDOFF.md` only, no state file | same | Rebuild the state file from the handoff (phase, magnitude, gates, rollbackSHA), confirm with user |
| neither | — | Step 0b |

**Backfill (state file predates the handoff feature, or handoff was deleted).** Do not ask the user to reconstruct it — derive it. Take task, magnitude, currentPhase, completedPhases, gates, rollbackSHA, worktreePath from the state file; get branch and changed files from `git status --short` and `git diff --stat <rollbackSHA>`; leave `Failures & dead ends`, `Key decisions` and `Commands` empty with the marker `(not recorded — predates handoff tracking)`. An incomplete handoff beats no handoff. Tell the user it was reconstructed and which sections are missing.

5. **On resume:** skip to the Phase Entry Protocol for the phase named in the handoff. Do NOT re-run completed phases. Do NOT re-ask decisions already recorded under `Key decisions`. Do NOT retry anything under `Do NOT` or `Failures & dead ends`.

6. **EXIT INVARIANT — `HANDOFF.md` MUST exist at the project root before Phase 0 ends.** Every path through this table produces one: resumed, backfilled, or freshly created in Step 0b. There is no branch where Phase 0 completes without it. If you are about to enter Phase 1 (or resume into any phase) and the file is not on disk, you have violated Step 0a — write it now. "It's missing because the session that started this work predates the feature" is not an exception, it is precisely the case backfill exists for.

**Anti-rationalization:** "the user gave me a fresh description, so this is obviously new work" — check anyway. A resumed task is often re-described in different words. Reading one file is cheap; redoing eight phases is not.

**Trace on resume:** if a handoff names a `Trace:` session, run `node <skill_dir>/dev-trace.js summary <session>` (and `failures <session>`) BEFORE reconciling. It tells you what the previous session actually ran, what failed and where it stopped — facts, not the handoff author's memory of them. If the handoff and the trace disagree, the trace wins; fix the handoff.

**Hook assist:** the `SessionStart` hook `~/.claude/hooks/dev-handoff-detect.js` already surfaces a summary of any `IN PROGRESS`/`PAUSED` handoff at session start, including a collision warning if another Claude process is alive in the same directory. Treat that summary as a pointer, not a substitute — still read the full file at Step 0a. If the hook said nothing, it does not prove absence (cwd may be outside the project): run the search anyway.

### Step 0b: Fresh pipeline

1. Get task description (from args or ask user).
2. Classify magnitude: **TRIVIAL** (config/typo/1-file/deps/style) | **STANDARD** (feature/multi-file/bug/API) | **COMPLEX** (architecture/new module/cross-cutting/security-sensitive).
2b. **Set `IS_GREENFIELD`** (see §IS_GREENFIELD trigger). Announce it: "🧯 Greenfield detected — error handling & logging will be designed in Phase 1 and verified at gate G2.5b." Store in state as `isGreenfield`.
   - **IS_GREENFIELD + TRIVIAL is a contradiction.** A new tool/app/module is never trivial. Escalate to STANDARD (upward reclassification is the default) and say why. If the user insists on TRIVIAL, keep the flag: the trivial path still owes the proportional Error & Logging proposal (§Resilience & Observability Design, minimal subset) inline before implementing, and G2.5b still applies.
2c. **Set `IS_AGENTIC`** (see §IS_AGENTIC trigger). Announce it: "🔭 Agentic code detected — this tool will call an AI. I'll ask you how much of its reasoning, metrics and tracing you want to be able to inspect." Store in state as `isAgentic`. IS_AGENTIC implies IS_GREENFIELD for the touched surface. If magnitude is TRIVIAL, ask the AI Observability Proposal right here, before step 3.
3. Show classification + active phases + advisory cost estimate (~20K trivial / ~120K standard / ~250K+ complex). Token estimates are advisory only — Claude Code has no runtime token counter.
4. Ask user: proceed / override magnitude / abort.
5. Create TaskCreate entries for active phases.
6. **MANDATORY: Write `.dev-pipeline-state.json` NOW.** This is NOT optional. Pipeline has NOT started until this file exists. Format:
```json
{
  "task": "<task description>",
  "magnitude": "<trivial|standard|complex>",
  "currentPhase": 0,
  "completedPhases": [0],
  "rollbackSHA": "<current HEAD SHA>",
  "startedAt": "<ISO timestamp>",
  "isGreenfield": <true|false>,
  "isAgentic": <true|false>,
  "tracing": { "active": <true|false>, "session": "<session id>", "dir": "<trace dir>" },
  "gates": {},
  "impeccableGate": null,
  "observabilityGate": null,
  "uiQualityGate": null,
  "agentTraceGate": null
}
```
**If this file is not written, the pipeline has NOT started. Do NOT proceed to any phase.**
6b. **MANDATORY: Verify production tracing (gate GT).** Run `node <skill_dir>/dev-trace.js doctor` (see §Production Tracing). On `status: OK` store `"tracing": { "active": true, "session": "<$CLAUDE_CODE_SESSION_ID>", "dir": "<trace dir>" }` in the state file. On `NOT TRACING`: tell the user the run will be untraced and why (usually: the suite was copied as a bare skill instead of installed as a plugin, so the hooks are absent), and ask: A) install the plugin and restart (recommended), B) continue untraced. Only B sets `tracing.waivedBy: "user"` — never waive it yourself. Record the waiver under `Waived / deferred` in `HANDOFF.md`.
7. **MANDATORY: Resolve the project root and write `HANDOFF.md` there NOW** (see §Handoff File). Both `.dev-pipeline-state.json` and `HANDOFF.md` live in the project root — NOT necessarily the directory Claude was launched from.
8. Announce: "▶ Phase 0: Triage complete. State + HANDOFF.md written to `<project-root>`. Starting /dev pipeline ([MAGNITUDE]) for: [description]"

**Dynamic re-evaluation** at 2 checkpoints (after codebase analysis, after first implementation attempt):
- Upward reclassification by default (trivial→standard→complex). Downward with explicit user confirmation only.
- On escalation: announce reclassification + added phases. If worktree needed and dirty tree exists, `git stash` before worktree setup, `git stash pop` after.
- Update `.dev-pipeline-state.json`.

---

## Phase 1: Brainstorm (standard+)

**Invoke:** `Skill(superpowers:brainstorming)` with feature description.

**Frontend-heavy features (HAS_FRONTEND):** When the feature is primarily UI/UX (new page, component redesign, form flow, dashboard), also invoke `Skill(impeccable, "shape <feature description>")` as supplement. Shape runs structured UX discovery and produces a design brief — append to brainstorming doc. Optional: do not block Phase 1 if user declines or feature has no UI surface.

**Greenfield features (IS_GREENFIELD) — MANDATORY:** the design doc MUST contain an **Error & Logging Strategy** section, presented to the user as an explicit proposal (not a silent default) before Phase 1 exits. See §Resilience & Observability Design for the questions to answer. Present it as: proposal → alternatives → cost. The user can slim it down; they cannot be left unaware of it. Record any reduction under `Waived / deferred` in `HANDOFF.md`.

**Exit:** User approved design. Design doc saved to `docs/superpowers/specs/`. If IS_GREENFIELD: design doc contains an approved Error & Logging Strategy section.
**Completion:** Update `.dev-pipeline-state.json`: add `1` to `completedPhases`. Announce: "✅ Phase 1: Brainstorm complete. Design doc saved. Next: Phase 2 or 3."

### Resilience & Observability Design (IS_GREENFIELD)

Answer every line. "Not needed" is a valid answer **only if written down with a reason** — a blank is a gap, not a decision.

**Errors**
1. **Taxonomy** — which errors exist: expected (validation/domain), external (network, API, DB, filesystem), internal bugs. Dedicated class/type per family, no scattered strings.
2. **Catch boundaries** — where errors are caught: top-level of entrypoints (CLI `main`, HTTP handlers, job consumers) + I/O boundaries. In between, propagate; never swallow.
3. **Wrapping** — rethrow preserving original cause (`cause`, `from e`, `%w`). Never lose the stack trace.
4. **Outbound mapping** — internal error → exit code / HTTP status / user message. User-facing messages must never expose stack traces, internal paths, raw queries, or secrets.
5. **Transient vs permanent** — retry policy: backoff with jitter, max attempts, idempotency guarantee. **Explicit timeout on every external call** (library defaults almost always lack timeouts).
6. **Cleanup** — ensure resources are released on error paths (files, connections, locks, child processes). Graceful shutdown on SIGINT/SIGTERM.
7. **Fail fast** — configuration and credentials validated at startup, not upon first request.
8. **Errors never silenced** — no empty `catch {}` or `except: pass`. If deliberate, include an explanatory comment.

**Logging**
9. **Library** — reuse existing project logger. If absent: standard library/ecosystem structured logger, not scattered `print` or `console.log`. No new dependencies if standard library suffices.
10. **Levels** — clear guidelines: ERROR (human action required), WARN (degraded but handled), INFO (business events at boundaries), DEBUG (diagnostics). Level configurable via env/flags.
11. **Format and sink** — structured JSON for services/aggregated logs; readable TTY for CLI. Explicit destination (stdout/stderr, file, collector) with log rotation/retention.
12. **Mandatory fields** — timestamp, level, component/module, event name, and a **propagated correlation/request ID** across requests.
13. **Redaction** — passwords, tokens, API keys, and PII must never be logged. Centralized redaction, not left to callers.
14. **Boundary logging** — log every external call: outcome + duration for zero-debugger diagnostics.
15. **Anti-duplication** — do not both log and re-raise the same error at multiple levels: log where handled. No logging inside hot loops.

**Tracing**
16. **Spans at boundaries** — every inbound request/job/command and every outbound call is a span (or at minimum a structured log line) with name, duration, outcome and error type. Reuse the project's tracer; if there is none and the unit is a service, propose OpenTelemetry (stdlib-only alternative: structured start/end log lines carrying the correlation id).
17. **Propagation** — the trace/correlation id crosses process boundaries (HTTP headers such as W3C `traceparent`, message metadata, subprocess env) and appears in every log line of the request.

**Proportionality:** a one-shot script needs points 2, 4, 8, 9, 10 — not all 17 points. A service with external integrations needs all 17. Propose the subset proportional to magnitude and state it explicitly.

### AI Observability Proposal (IS_AGENTIC — ask the user, gate GA)

When the tool being built calls an AI (SDK or `claude -p` / `gemini -p` / `agy -p` / `codex exec` ...), the user decides how much of the AI's behaviour they want to be able to inspect. Present this as an explicit question — one message, with the options and what each costs — not as a silent default. Recommend A.

> 🔭 This tool calls an AI (`<where: file / CLI / SDK>`). How much do you want to be able to see of what the AI does inside it?
>
> | | Reasoning | Metrics | Traces | Failures | How you inspect it |
> |---|---|---|---|---|---|
> | **A. Full (recommended)** | rationale / plan per step, thinking summary when the model exposes it, why the loop stopped | latency, tokens (in/out/thinking/cache), cost, turns, tool calls + success rate, retries, error rate, timeouts | run id + span per LLM call, per tool call, per step; child session id for CLI runs | error span with type + verbatim message for every failure path; non-SUCCESS status of CLI runs | local report command (`<tool> trace <run-id>` or a JSONL run log) + optional OTLP export (Jaeger / Phoenix / Langfuse) |
> | **B. Choose** | pick from the A columns | | | | |
> | **C. Minimal** | — | latency, tokens, exit status | run id | error + stderr tail | log lines |
> | **D. None** | — | — | — | (exit code + timeout still mandatory: G2.5b) | — |
>
> Cost of A: ~1 module (tracer + redaction + report) and a few tests; tracing can be switched off by config.

Record the answer verbatim in `.dev-pipeline-state.json`:
```json
{ "agentObservability": { "decision": "A|B|C|D|not-applicable", "items": ["reasoning", "metrics", "traces", "failures", "report", "otlp"], "answeredBy": "user", "askedAt": "<ISO>" } }
```
and under `Key decisions` in `HANDOFF.md` (D also under `Waived / deferred`). The chosen items become requirements: Phase 1 designs them (§Agent Tracing Design), Phase 3 plans them as a **Tracing** task group, G2.5c verifies them with a real run, and the Knowledge Quiz asks about them. D never waives the resilience basics for AI CLI subprocesses (timeout, exit/status check, stderr capture), which stay CRITICAL in G2.5b/G2.5c.

If the user already answered this for the same tool in an earlier pipeline (see `HANDOFF.md` Key decisions or project memory), show the previous choice and ask to confirm rather than re-asking from scratch.

### Agent Tracing Design (IS_AGENTIC)

Code that drives an LLM must be diagnosable the same way this pipeline is: from production traces that reveal tool calls, reasoning steps, latency and failures. Answer every line covered by the user's AI Observability choice in the Phase 1 design doc (decision A: all; B: the chosen items; C: 2, 3 latency/tokens, 6, 10; D: 10's timeout/status/stderr only):

1. **Tracer** — the project's existing one (OpenTelemetry, LangSmith, Langfuse, Phoenix, Braintrust, ...) or OpenTelemetry with the GenAI semantic conventions (`gen_ai.*` attributes). Exporter configurable by env; console/file exporter for local runs, in-memory exporter in tests.
2. **Run span** — one root span per agent run / conversation turn with a run id that is returned to the caller and written to logs, so a user report can be mapped to its trace.
3. **LLM call spans** — model, latency, input/output tokens, finish/stop reason, retry attempt number. Prompts and completions recorded only through the redaction layer, and switchable off.
4. **Tool call spans** — tool name, redacted arguments, result status and size, duration; child of the LLM step that requested it.
5. **Reasoning / decision steps** — each loop iteration is a span or event: step number, chosen action, short rationale or plan if the model provides one, and why the loop stopped (final answer, max iterations, budget, error).
6. **Failures** — every error path sets error status on its span with the exception type and message: provider errors, timeouts, rate limits, tool exceptions, invalid tool arguments, output parse/schema failures, guardrail refusals.
7. **Cost & limits** — token totals per run, and the configured max iterations / timeout / budget recorded on the run span.
8. **Sampling & privacy** — sampling rate and content capture are configuration, with secrets/PII redacted centrally before export.
9. **Tests** — at least one test runs the agent with a failing tool (or a mocked failing LLM call) and asserts the error span and the run id exist.
10. **AI CLI subprocesses** (`claude -p`, `gemini -p`, `agy -p`, `codex exec`, ...): each invocation is a span (CLI, model, args redacted, exit code, duration, timeout); the CLI runs with its structured output mode (`agy`/`claude`/`gemini --output-format stream-json`/`json`, `codex exec --json`) and the wrapper parses it into child spans/attributes: turns, tokens, cost, the nested agent's tool calls, `is_error`/`subtype` (e.g. `error_max_turns`); stderr is captured, never discarded; a hard timeout kills the process tree; the run id is passed down (env var, or `--session-id` for Claude) and the child session id is recorded on the span. Success is the structured status, not the exit code: `agy` exits `0` on permission soft-denials, so check `status == "SUCCESS"`; Claude: `is_error`/`subtype`; Gemini: exit `53` = turn limit; Codex: `turn.failed`. Use the CLI's own timeout when it has one (`agy --print-timeout`, whose default is unlimited). For a CLI without a structured mode, record exit code + stderr tail + duration and say so in the design.

Proportionality: a single LLM call in a script needs 2, 3, 6 (plus 10 if it is a CLI subprocess); an agent loop with tools needs all of them.

## Phase 2: Design Council (complex only)

**GATE G1 — This phase is MANDATORY for COMPLEX magnitude. Do NOT skip it.**

Council the design for implementation-readiness (soundness, completeness, scope, risk). **Invoke:** `Skill(llm-council)`.
- **GO** → Phase 3. **NO-GO** → Council Remediation Loop (see Protocols).
**Completion:** Update `.dev-pipeline-state.json`: add `2` to `completedPhases`, set `gates.designCouncilGO: true`. Announce: "✅ Phase 2: Design Council complete. Verdict: GO. Next: Phase 3."

## Phase 3: Plan (standard+)

**PRE-CONDITION CHECK:** If magnitude is COMPLEX, verify that Phase 2 (Design Council) was executed and returned GO before proceeding. If Phase 2 was not executed, STOP and run it now.

**Invoke:** `Skill(superpowers:writing-plans)` with approved design doc.

**If IS_GREENFIELD:** the plan MUST contain an **Errors & Observability** task group turning the Phase 1 strategy into concrete tasks (error types module, catch boundaries at each entrypoint, logger setup + redaction, timeouts/retry on external calls, tests for the failure paths). Error paths get tests too — TDD applies to `catch` as much as to the happy path. A plan without this group does not pass Gate G2.

**Exit:** Plan saved to `docs/superpowers/plans/`.
**Completion:** Update `.dev-pipeline-state.json`: add `3` to `completedPhases`, set `planFile: "<path>"`. Announce: "✅ Phase 3: Plan complete. Plan saved. Next: Phase 4."

## Phase 4: Worktree (standard+)

**Invoke:** `Skill(superpowers:using-git-worktrees)`.
**Exit:** Working in isolated worktree on feature branch.
**Completion:** Update `.dev-pipeline-state.json`: add `4` to `completedPhases`, set `worktreePath: "<path>"`. Announce: "✅ Phase 4: Worktree complete. Branch ready. Next: Phases 5-8."

## Phases 5-8: Implement → Verify → Review → Audit

### TRIVIAL path (no workflow)

1. Capture rollback SHA → store in `.dev-pipeline-state.json`.
2. Implement the change directly (no plan, no subagents). If the change makes the code call an AI (SDK or headless CLI), stop first and ask the AI Observability Proposal (gate GA) — the Stop hook blocks until the answer is recorded.
3. Run verification: full test suite or build fallback. On failure: **diagnose from evidence** — read the verbatim error (`dev-trace.js failures` shows it with the reasoning that led to the call), state the root cause, fix, then re-run the SAME command until green. The Stop hook blocks once if a failed verification command was never re-run green.
4. Security audit (conditional): if changed files match HAS_FRONTEND or HAS_API, run `maestro:security-audit` on changed files. Fix HIGH+ findings before proceeding.
**Exit:** Change implemented, tests/build passing, security checked (if applicable).
**Completion:** Update `.dev-pipeline-state.json`: add `5`, `6`, `7`, `8` to `completedPhases`. Announce: "✅ Phases 5-8: Implement+Verify+Review+Audit complete (trivial path). Next: Phase 8.5."

### STANDARD / COMPLEX path (parallel workflow)

Phases 5-8 execute as a **single Workflow** with parallel agents, deterministic loops, and adversarial verification.

1. Capture rollback SHA → store in `.dev-pipeline-state.json`.
2. Detect audit triggers from changed file types (`git diff origin/main --name-only`):
   - HAS_FRONTEND → security + a11y + verify
   - HAS_API → security
   - HAS_PERF → perf-check
3. **Invoke Workflow:**
Resolve `implement-and-review.js` absolute path (located in the same directory as this `SKILL.md`, e.g. `<skill_base_dir>/implement-and-review.js` or fallback to `~/.claude/skills/dev/implement-and-review.js`):
```
Workflow({
  scriptPath: "<absolute path to implement-and-review.js>",
  args: {
    planPath: "<path to plan from Phase 3>",
    magnitude: "<trivial|standard|complex>",
    tddRequired: true,
    auditTriggers: { security: <bool>, a11y: <bool>, perf: <bool> }
  }
})
```
4. Wait for Workflow completion. Parse results.
5. If `status: FAILED` → run `dev-trace.js summary` (the Workflow's per-agent spans, with durations and errors, are in the trace) and show the user: the failing phase, the failing agent label(s), `lastFailures` verbatim. Then ask: retry / manual fix / abort. A retry prompt must cite the failing span, not a paraphrase.

**What the Workflow does internally (all deterministic, parallel, with loops):**
- **Implement:** Parallel agents (one per task, worktree-isolated) + integration agent merges results
- **Verify:** Full test suite with debug loop (max 3 cycles: fail → systematic debug → re-test)
- **Review:** Maestro review → conditional 2nd review (if HIGH+) → **adversarial verify** (independent agents try to refute each HIGH+ finding) → graduated remediation loop (max 3 cycles)
- **Audit:** Parallel conditional audits → remediation loop (max 3 cycles)

**Exit:** Workflow returns `{ status, implemented, verified, reviewFindings, auditFindings }`.
**Completion:** Update `.dev-pipeline-state.json`: add `5`, `6`, `7`, `8` to `completedPhases`. Announce: "✅ Phases 5-8: Implement+Verify+Review+Audit complete (workflow). Next: Phase 8.5."

## Phase 8.5: Impeccable Quality Gate (always)

**GATE G2.5 — MANDATORY for ALL magnitudes. Do NOT skip.**

After implementation, verification, review, and audit are complete, invoke impeccable skills to enforce coding standards on all changed files. This gate runs BEFORE Ship Council so quality issues are fixed before ship-readiness review.

### Step 1: Detect applicable skills from changed files

Run `git diff --name-only origin/main` (or vs rollback SHA) and classify:

| File Pattern | Impeccable Skills to Invoke |
|--------------|-----------------------------|
| `*.tsx`, `*.jsx`, `*.vue`, `*.component.ts` | `frontend-components` |
| `*.css`, `*.scss`, `*.sass`, styled-components | `frontend-css` |
| Routes, controllers, middleware, API handlers | `backend-api` |
| DB queries, ORM calls, repositories | `backend-queries` |
| Migration files, schema definitions | `backend-migrations` |
| Model/entity files, DTOs | `backend-models` |
| Test files (`*.test.*`, `*.spec.*`, `*.feature`) | `testing-test-writing` |
| **ALL code files** (always) | `global-coding-style`, `global-commenting`, `global-conventions`, `global-error-handling`, `global-tech-stack`, `global-validation` |

### Step 2: Invoke skills and collect findings

For each applicable skill:
1. `Skill(<skill-name>)` — load skill guidelines
2. Review changed code against skill rules
3. Classify findings: **CRITICAL** (must fix) / **WARNING** (should fix) / **INFO** (optional improvement)

### Step 2b: Resilience & Observability checklist (IS_GREENFIELD — blocking)

Verify the implemented code against the 17 points of §Resilience & Observability Design. Read the actual changed files — do not infer from the plan. Classify each gap:

| Gap | Severity |
|---|---|
| Swallowed error (`catch {}`, `except: pass`, ignored error return) | CRITICAL |
| No catch boundary at an entrypoint — unhandled crash reaches the user raw | CRITICAL |
| External call with no timeout | CRITICAL |
| Secret / token / PII reachable in a log line | CRITICAL |
| Cause lost when wrapping / re-raising | WARNING |
| Resource not released on the error path | WARNING |
| No correlation id, or not propagated | WARNING |
| Wrong level (errors at INFO, noise at ERROR), or level not configurable | WARNING |
| Same error logged at multiple levels of the stack | WARNING |
| No test covering a failure path | WARNING |
| Unstructured logging where the project logs structured | WARNING |
| Outbound call / job / request handler with no trace span (or no duration + outcome logged) | WARNING |
| Trace / correlation id not propagated across a process or service boundary | WARNING |

Non-greenfield tasks: skip this step, but still report any CRITICAL row spotted in the diff as a normal Phase 8.5 CRITICAL finding.

Update state:
```json
{ "observabilityGate": { "critical": 0, "warnings": { "fixed": 0, "waived": 0 }, "passed": true } }
```

Gate G2.5b passes when zero CRITICAL remain and every WARNING is fixed or explicitly waived by the user.

### Step 2c: Agent Tracing checklist (IS_AGENTIC — blocking)

Verify the implemented code against §Agent Tracing Design, scoped to the items in `state.agentObservability` (rows outside the user's choice are N/A, except the AI CLI timeout / exit-status / stderr rows, which always apply). Read the changed files AND run the code once (test or example run) with the tracer pointed at a local sink (console/file exporter, in-memory exporter in tests): a checklist answered from the source alone is not verified.

| Gap | Severity |
|---|---|
| An LLM call with no span (model, latency, token usage, finish reason) | CRITICAL |
| A tool / function call executed for the model with no span (tool name, arguments, outcome, duration) | CRITICAL |
| A failure path (LLM error, tool exception, timeout, schema/parse failure, max-iterations stop) that leaves no error span / error status | CRITICAL |
| Prompts, tool arguments or outputs traced without redaction of secrets / PII | CRITICAL |
| No run / trace id tying all steps of one agent run together, or not returned to the caller / logged | WARNING |
| Agent loop iterations / decision steps not recorded (which step, why it chose that tool, why it stopped) | WARNING |
| Retries not visible (each attempt should be its own span or a counted attribute) | WARNING |
| No test asserting that a failing tool or LLM call produces an error span | WARNING |
| Tracing cannot be disabled or sampled via configuration | WARNING |
| AI CLI subprocess (`claude -p`, `gemini -p`, `agy -p`, `codex exec`, ...) with no span, exit code ignored, or stderr discarded | CRITICAL |
| AI CLI subprocess with no timeout | CRITICAL |
| AI CLI that supports structured output run in text mode, so its turns / tool calls / errors cannot be traced | WARNING |
| Child session id / nested run id not recorded on the span | WARNING |

Update state:
```json
{ "agentTraceGate": { "critical": 0, "warnings": { "fixed": 0, "waived": 0 }, "verifiedByRun": true, "passed": true } }
```

Gate G2.5c passes when zero CRITICAL remain, every WARNING is fixed or explicitly waived by the user, and `verifiedByRun` is true.

### Step 3: Remediation

- **CRITICAL findings:** Fix ALL before proceeding. Max 3 remediation cycles (fix → re-check → fix).
- **WARNING findings:** Fix unless user explicitly waives. List waived items in pipeline state.
- **INFO findings:** Report to user, no blocking.
- After fixes: re-run verification (test suite) to ensure fixes don't break anything.

### Step 4: Gate check

Gate G2.5 passes when: zero CRITICAL findings remain AND all WARNING findings are fixed or waived.
Gate G2.5b (IS_GREENFIELD only) passes per Step 2b. Gate G2.5c (IS_AGENTIC only) passes per Step 2c. All applicable gates must pass to leave Phase 8.5.

Update `.dev-pipeline-state.json` with:
```json
{
  "impeccableGate": {
    "skillsInvoked": ["list of invoked skills"],
    "criticalFindings": 0,
    "warningFindings": { "fixed": N, "waived": N },
    "infoFindings": N,
    "passed": true
  }
}
```

**Exit:** All impeccable quality checks passed. Proceed to UI Quality Gate (if HAS_FRONTEND) or Ship Council.
**Completion:** Update `.dev-pipeline-state.json`: add `8.5` to `completedPhases`. Announce: "✅ Phase 8.5: Impeccable Quality Gate passed. Next: Phase 8.6 or 9."

---

## Phase 8.6: UI Quality Gate (standard+ with HAS_FRONTEND)

**GATE G2.6 — MANDATORY for STANDARD and COMPLEX when HAS_FRONTEND. Do NOT skip.**

After coding standards pass (Phase 8.5), run UI-specific quality checks on changed frontend files. Catches design anti-patterns, accessibility gaps, and UX issues that coding standard skills cannot detect.

**Skip condition:** If no frontend files changed (`git diff --name-only origin/main` produces zero matches for `.html/.css/.scss/.tsx/.jsx/.vue/.component.ts`), skip entirely. Log: "Phase 8.6 skipped: no frontend files changed."

**TRIVIAL magnitude:** Run Step 1 (detect CLI) only. Skip Steps 2-5 (audit, critique, remediation, gate). detect is deterministic and free — trivial UI changes (color swap, label change) can break accessibility, and detect catches these.

### Step 1: Deterministic anti-pattern scan (always first)

Run bundled detector on changed frontend files:

```bash
# macOS/Linux (bash/zsh):
npx impeccable detect --json $(git diff --name-only origin/main | grep -E '\.(html|htm|tsx|jsx|vue|css|scss)$' | tr '\n' ' ')

# Cross-platform / Windows PowerShell:
# Collect modified frontend files via git diff, then pass them:
# npx impeccable detect --json file1.tsx file2.css ...
```

- Exit code 0 = clean. Exit code 2 = findings.
- Parse JSON. Classify: CRITICAL (slop tells, accessibility blockers) / WARNING (minor anti-patterns).
- If detector unavailable or errors, log and continue to Step 2 (degraded mode).

Fast, deterministic, zero LLM tokens. Always run before LLM-based checks.

### Step 2: Technical audit (STANDARD+)

**Invoke:** `Skill(impeccable, "audit <changed-frontend-files-or-directory>")`

Produces scores across 5 dimensions (a11y, performance, theming, responsive, anti-patterns) with total out of 20, plus P0-P3 severity findings.

### Step 3: UX critique (COMPLEX only)

**Invoke:** `Skill(impeccable, "critique <primary-changed-surface>")`

Produces Nielsen heuristic scores (out of 40), cognitive load assessment, persona red flags. Expensive — skip for STANDARD.

### Step 4: Remediation

**Threshold calibration (REQUIRED before first use):** Run `npx impeccable detect --json src/` on actual codebase. Set initial thresholds at baseline score or baseline+2. Tighten over time. Do NOT use default thresholds below without calibration.

**Gate thresholds (defaults — calibrate before use):**
- **detect CLI:** Zero CRITICAL required. WARNING reported but non-blocking.
- **audit score:** >= 14/20 required (calibrate). Below threshold = remediation.
- **audit P0:** Zero P0 required. P1 should-fix (waiver rules same as Phase 8.5).
- **critique (COMPLEX):** Zero P0, heuristic total >= 20/40 required (calibrate).

**Remediation by finding type:**

| Finding Type | Remediation Command | Blocking |
|---|---|---|
| Anti-pattern / AI slop | Fix directly (remove pattern) | Mandatory |
| Accessibility (a11y) | Fix directly (semantic HTML, ARIA, contrast) | P0/P1 mandatory |
| Responsive issues | `Skill(impeccable, "adapt <target>")` | P0 mandatory |
| UX copy / error messages | `Skill(impeccable, "clarify <target>")` | P0 mandatory |
| Spacing / layout / hierarchy | `Skill(impeccable, "layout <target>")` | P1+ recommended |
| Multiple dimensions low | `Skill(impeccable, "polish <target>")` | Final pass after targeted fixes |

**Remediation loop:** Max 2 cycles (fix → re-audit → fix → re-audit). After 2 cycles if gate still fails: ask user A) Continue fixing, B) Waive remaining, C) Abort.

After fixes: re-run test suite + re-run `detect` CLI to verify.

**Failure output requirements:** When gate blocks, show: specific anti-patterns found, file paths and line numbers, one-line fix suggestion per finding. Do NOT show only a score — actionable feedback is mandatory for developer adoption.

### Step 5: Gate check

Gate G2.6 passes when:
- detect CLI: zero CRITICAL
- audit score >= 14/20
- zero P0 audit findings
- (COMPLEX) zero P0 critique findings AND heuristic >= 20/40
- all P1 fixed or waived

Update `.dev-pipeline-state.json`:
```json
{
  "uiQualityGate": {
    "detectFindings": { "critical": 0, "warning": 0 },
    "auditScore": 0,
    "auditFindings": { "p0": 0, "p1Fixed": 0, "p1Waived": 0 },
    "critiqueScore": null,
    "critiqueFindings": null,
    "remediationCycles": 0,
    "passed": true
  }
}
```

**Exit:** UI quality checks passed. Proceed to Ship Council.
**Completion:** Update `.dev-pipeline-state.json`: add `8.6` to `completedPhases`. Announce: "✅ Phase 8.6: UI Quality Gate passed. Next: Phase 9."

**Note on excluded impeccable commands:** The remaining commands (`bolder`, `quieter`, `distill`, `animate`, `colorize`, `typeset`, `delight`, `overdrive`, `onboard`, `optimize`, `live`, `init`, `document`, `extract`, `pin/unpin`) are available as manual developer tools via `Skill(impeccable, "<command> <target>")`. They are interactive/creative and do not belong in automated gates. Do NOT auto-remediate with generative commands in the pipeline — non-deterministic LLM-driven fixes in CI are a reliability hazard.

---

## Phase 9: Ship Council (standard+)

**GATE G3 — This phase is MANDATORY for STANDARD and COMPLEX. Do NOT skip it.**

Council the implementation for ship-readiness (correctness, quality, completeness, risk). Include: what was built, implementation summary, test results, review findings (from Workflow result), audit results, diff stats. **If IS_GREENFIELD:** include the Error & Logging Strategy as approved plus the G2.5b outcome (gaps found, fixed, waived) — the council reviews whether the resilience story is adequate for what is shipping. **Always:** include the `dev-trace.js summary` of this pipeline run — failures and whether each was resolved, debug/remediation cycles, slowest steps. Unresolved failures in the trace are a NO-GO unless explained. **If IS_AGENTIC:** include the G2.5c outcome and one sample trace of the built agent (span tree of a real run). **If Phase 8.6 ran:** include UI Quality Gate results (detect findings, audit score + dimension breakdown, critique heuristic scores if available, remediation actions taken, waived items). **Invoke:** `Skill(llm-council)`.
- **GO** → Phase 10. **NO-GO** → Council Remediation Loop: extract feedback, re-run Workflow with council feedback as additional context, re-council. Max 5 iterations (see Protocols).
**Completion:** Update `.dev-pipeline-state.json`: add `9` to `completedPhases`, set `gates.shipCouncilGO: true`. Announce: "✅ Phase 9: Ship Council complete. Verdict: GO. Next: Phase 10."

## Phase 10: Docs Check (always)

**PRE-CONDITION CHECK:** If magnitude is STANDARD or COMPLEX, verify that Phase 9 (Ship Council) was executed and returned GO before proceeding. If Phase 9 was not executed, STOP and run it now.

Scan changed files. Check: README, CLAUDE.md, API docs, inline docs (JSDoc/TSDoc), design doc (mark IMPLEMENTED), changelog. Update stale docs, commit separately. If no docs impacted: "No documentation updates needed."
**Completion:** Update `.dev-pipeline-state.json`: add `10` to `completedPhases`. Announce: "✅ Phase 10: Docs complete. Next: Phase 10.5."

## Phase 10.5: Knowledge Quiz (always)

Interactive quiz on the newly completed implementation. Purpose: ensure the developer maintains full awareness and ownership of code authored by Claude. Non-blocking — purely informative result.

### Question Generation

Generate questions based on:
- **Modified files** (`git diff --name-only`) — "Which file handles X?"
- **Key logic** — "How does the new Y work?" / "Why does Z follow this pattern?"
- **Design decisions** — "Why did we choose approach A over B?"
- **Handled edge cases** — "What happens if input is empty, null, or exceeding bounds?"
- **Tracing** (mandatory if IS_AGENTIC, ≥1 question) — "A user reports a wrong answer from run R: which span tells you which tool the agent called and why?"
- **Errors & logging** (mandatory if IS_GREENFIELD, ≥1 question) — "What happens if call to X times out?" / "Where is error Y caught and what does the user see?" / "At which log level is Z emitted and why?"
- **Test coverage** — "Which scenario is verified by test T?"
- **Dependencies** — "Which existing module was reused and why?"

Mix: ~40% questions on WHAT changed, ~30% on HOW it works, ~30% on WHY (decisions).

### Adaptive Depth

- **TRIVIAL:** 5 questions.
- **STANDARD:** 10 questions.
- **COMPLEX:** 10 questions + 2 architectural bonus questions on trade-offs and discarded alternatives.

### Format

Present all numbered questions together in one block. The user answers (concisely or in batch). Claude evaluates each answer:
- ✅ Correct
- ⚠️ Partial — provides missing detail
- ❌ Incorrect — explains the correct answer with file:line references

### Scoring

Final report: X/N correct, Y partial, Z incorrect. No gate — quiz does not block Phase 11. Result is informative only.

**Completion:** Update `.dev-pipeline-state.json`: add `10.5` to `completedPhases`, set `knowledgeQuiz: { total: N, correct: X, partial: Y, wrong: Z }`. Announce: "✅ Phase 10.5: Knowledge Quiz complete. Score: X/N. Next: Phase 11."

## Phase 11: Finish (always)

**STANDARD/COMPLEX:** `Skill(superpowers:finishing-a-development-branch)`.
**TRIVIAL (no worktree):** Show `git diff --stat`, ask user: A) Commit, B) Leave unstaged, C) Discard.

**Completion announcement:** Feature, magnitude, council iterations (or N/A), audits run, docs updated, result, and the trace line: `Trace: <session> — <N> tool calls, <F> failures (<U> unresolved), wall <time>` (from `dev-trace.js summary`). Point the user at `dev-trace.js export <session>` if they want to load it into an OpenTelemetry viewer.
**Completion:** Update `.dev-pipeline-state.json`: add `11` to `completedPhases`. Delete `.dev-pipeline-state.json` (pipeline complete). Final `HANDOFF.md` refresh with `Status: DONE`, then **keep it** — do NOT delete. It is the record of what was built, what was waived, and what was deliberately not done. Announce: "✅ Phase 11: Finish complete. /dev pipeline DONE. Handoff at `<project-root>/HANDOFF.md`."

---

## Protocols

### Council Remediation Loop

Used by Phase 2 (design) and Phase 9 (ship). Identical structure, different remediation action.

```
MAX_ITERATIONS = 5. Counter per council gate.

WHILE council says NO:
  IF counter > MAX_ITERATIONS → ask user: A) Continue (reset), B) Force-proceed, C) Abort, D) Reset to rollbackSHA
  1. Extract issues from council feedback (Recommendation + Clashes + Blind Spots)
  2. For design council: re-invoke Skill(superpowers:brainstorming) with feedback, re-council
  3. For ship council: re-run Workflow (implement-and-review.js) with council feedback as additional args, re-council
  4. Parse verdict → GO exits, NO loops
```

### Graduated Remediation Protocol (inside Workflow)

This protocol now lives inside `implement-and-review.js` as deterministic JS loops. It is NOT a prompt-level protocol anymore. The Workflow handles:
- Verify→debug loop: max 3 cycles (for loop in JS)
- Review remediation: adversarial verify + graduated fix by severity, max 3 cycles
- Audit remediation: fix + re-verify + re-audit, max 3 cycles

All loop counters are JS variables, not LLM-estimated counts.

---

## State & Rollback

**Pipeline state** persisted to `.dev-pipeline-state.json` after every phase completion, reclassification, and remediation cycle. Fields: task, magnitude, isGreenfield, isAgentic, tracing, currentPhase, completedPhases, rollbackSHA, remediationCounts, designDoc, planDoc, worktreePath, startedAt, impeccableGate, observabilityGate, uiQualityGate, agentTraceGate, knowledgeQuiz.

Resume detection is **Phase 0 Step 0a** — see there for the full lookup order and reconciliation table. Delete the state file at Phase 11 completion or user abort; keep `HANDOFF.md`.

**Rollback:** Worktree delete discards all changes. During remediation, if 3+ fixes fail, offer `git reset --hard <rollbackSHA>`. User can abort at any time — state preserved.

---

## Handoff File (`HANDOFF.md`)

Human-readable context snapshot for resuming work after `/clear`, compaction, or a new session. `.dev-pipeline-state.json` is machine state (phases, gates, booleans); `HANDOFF.md` is *why and where we are*. Both are mandatory, both live in the **project root**.

### Path resolution (do this once at Phase 0, store in state as `projectRoot`)

The project root is NOT necessarily Claude's launch directory. Resolve in order, first hit wins:

1. `state.worktreePath` if Phase 4 ran → the worktree root.
2. `git rev-parse --show-toplevel` executed from the directory containing the files being changed.
3. Nearest ancestor of the changed files containing a project marker (`package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `pom.xml`, `.git`, `CLAUDE.md`).
4. Fallback: Claude's cwd — and **say so explicitly** to the user, since it may be wrong.

Announce the resolved path once: "📁 Project root: `<path>`". If the user contradicts it, use their path and update `state.projectRoot`.

Write with an absolute path (`<projectRoot>/HANDOFF.md`), never a relative one — the cwd may differ.

**Pre-existing file:** if `HANDOFF.md` already exists and its `Task:` differs from the current one, do NOT silently overwrite. Rename the old one to `HANDOFF.prev.md` (overwriting any previous `HANDOFF.prev.md`) and tell the user. If `Task:` matches, overwrite in place — it's the same pipeline resuming.

**Concurrent sessions (same directory):** stamp ownership in the header — get it with `echo "$CLAUDE_CODE_SESSION_ID $CLAUDE_PID"` at Phase 0 and reuse the values for the rest of the pipeline. Before the FIRST write of the pipeline, if an existing `HANDOFF.md` has `Status: IN PROGRESS` and a different pid that is **still alive** (`kill -0 <pid>`), STOP: another Claude terminal is running `/dev` in this same directory and both pipelines would clobber each other. Report it and let the user choose: A) work in a separate worktree, B) take over (they close the other terminal), C) abort. A dead pid is just a leftover from a previous session of your own — take it over silently.

Different repos and different worktrees never collide: each has its own root, so its own `HANDOFF.md`. Only the same-directory case needs this check.

**Gitignore:** if the repo has a `.gitignore` and `HANDOFF.md` is not covered, ask the user once whether to ignore it or commit it. Default suggestion: ignore (it's session scratch, not a deliverable).

### Update triggers

Rewrite the whole file (it's short — no diffing) at:

- Phase 0 (creation)
- every phase completion
- every magnitude reclassification
- every failed verification / review / audit / council NO-GO
- Context Exhaustion Protocol step 2b
- Phase 11 (final, `Status: DONE`)

### Template

```markdown
# HANDOFF — <task title>

Status: IN PROGRESS | PAUSED | DONE
Updated: <ISO timestamp>
Session: <$CLAUDE_CODE_SESSION_ID> (pid <$CLAUDE_PID>)
Magnitude: <trivial|standard|complex>
Project root: <absolute path>
Branch / worktree: <branch> @ <worktreePath or "none">
Rollback SHA: <sha>
Trace: <session id(s) of the sessions that worked on this> — `node <skill_dir>/dev-trace.js summary <session>`

## Goal
<2-4 sentences: what the user asked for, in their terms, and the acceptance
condition — how we know it's done. Not a phase list.>

## Where we are
Phase <N>: <name> — <one line on what is in flight right now>
Completed: <list>  |  Remaining: <list>
Gates: designCouncil=<GO/–> shipCouncil=<GO/–> impeccable=<pass/–> observability=<pass/n-a> agentTrace=<pass/n-a> ui=<pass/–> tracing=<on/waived>

## Next step
1. <the single next concrete action, specific enough to execute cold>
2. <then>
3. <then>

## Files touched
| File | What changed / why it matters |
|---|---|
| path:line | <one line> |
<Changed files first, then key files READ but not changed — those are the
context that took the longest to rebuild.>

## Key decisions
- <decision> — because <reason>. Alternative rejected: <alt>.

## Failures & dead ends
- ❌ <what was tried> → <how it failed, exact error text> → <resolved how, or still open>  (trace #<n> in <session>)
<Only significant ones: failed approaches, non-obvious errors, flaky steps.
This section prevents a post-clear Claude from re-trying what already failed.>

## Do NOT
- <approach already ruled out, and why>

## Open questions
- <pending user decision, blocking or not>

## Waived / deferred
- <finding or scope item consciously not fixed> — <why, who waived>

## Commands
- Test: `<cmd>`
- Build: `<cmd>`
- Lint / detect: `<cmd>`
- Run app: `<cmd>`
<Verified commands only — the ones actually run this session. A wrong command
here is worse than none.>

## Resume
`/dev` — resumes from Phase <N>. Read this file first.
```

### Rules

- **Facts only.** Every claim must be something that happened this session. No plans described as done, no assumed test results. If a step was skipped, write it in `Waived / deferred`.
- **Errors verbatim.** Quote exact error text in `Failures & dead ends` — paraphrased errors are ungreppable. Copy it from `dev-trace.js failures`, and cite the trace call number.
- Keep it under ~150 lines. If a section is empty, drop the heading.
- Prose is terse and mechanical; this is a note to a Claude with zero memory, not a report.
- Never put secrets, tokens, or credentials in it — it is a plaintext file in the repo.
