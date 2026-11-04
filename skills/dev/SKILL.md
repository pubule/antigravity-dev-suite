---
name: dev
description: "Magnitude-aware SDLC pipeline. Classifies tasks as trivial/standard/complex, runs proportional ceremony. Graduated remediation, state persistence, rollback. On every invocation it first looks for HANDOFF.md / .dev-pipeline-state.json in the project root to resume interrupted work after a /clear or new session. Invoke: /dev or /dev <description>."
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
| 8.5. Impeccable Quality Gate | Impeccable skills + Resilience & Observability check (see §Impeccable Quality Gate) | run | run | run |
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

Not greenfield (edits inside an existing unit with an established error/log convention): follow the existing convention, no extra gate. If the existing convention is *absent*, say so and treat the change as greenfield for the touched surface.

**Impeccable skill loading during implementation:** When writing code in Phases 5-8, load applicable impeccable `global-*` skills BEFORE coding. These inform coding style, conventions, error handling, and validation patterns. Phase 8.5 enforces compliance — loading early prevents rework. **For HAS_FRONTEND changes:** also consult `Skill(impeccable, "harden <target>")` guidance during implementation for edge cases, i18n, error states, and text overflow. Hardening during implementation is cheaper than remediating after Phase 8.6. **For IS_GREENFIELD:** keep the approved Error & Logging Strategy open while coding — write the error types and logger setup *first*, before the feature logic, so every later path has something to use. Retrofitting is what produces `catch {}`.

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
| `HANDOFF.md`, Status IN PROGRESS/PAUSED | same | Show task, phase N, next step, open questions. Ask: "Riprendo dalla Phase N? [Y / Restart / Nuova task]" |
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

**Hook assist:** the `SessionStart` hook `~/.claude/hooks/dev-handoff-detect.js` already surfaces a summary of any `IN PROGRESS`/`PAUSED` handoff at session start, including a collision warning if another Claude process is alive in the same directory. Treat that summary as a pointer, not a substitute — still read the full file at Step 0a. If the hook said nothing, it does not prove absence (cwd may be outside the project): run the search anyway.

### Step 0b: Fresh pipeline

1. Get task description (from args or ask user).
2. Classify magnitude: **TRIVIAL** (config/typo/1-file/deps/style) | **STANDARD** (feature/multi-file/bug/API) | **COMPLEX** (architecture/new module/cross-cutting/security-sensitive).
2b. **Set `IS_GREENFIELD`** (see §IS_GREENFIELD trigger). Announce it: "🧯 Greenfield rilevato — error handling & logging saranno progettati in Phase 1 e verificati al gate G2.5b." Store in state as `isGreenfield`.
   - **IS_GREENFIELD + TRIVIAL is a contradiction.** A new tool/app/module is never trivial. Escalate to STANDARD (upward reclassification is the default) and say why. If the user insists on TRIVIAL, keep the flag: the trivial path still owes the proportional Error & Logging proposal (§Resilience & Observability Design, minimal subset) inline before implementing, and G2.5b still applies.
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
  "gates": {},
  "impeccableGate": null,
  "observabilityGate": null,
  "uiQualityGate": null
}
```
**If this file is not written, the pipeline has NOT started. Do NOT proceed to any phase.**
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

**Greenfield features (IS_GREENFIELD) — MANDATORY:** the design doc MUST contain an **Error & Logging Strategy** section, presented to the user as an explicit proposal (not a silent default) before Phase 1 exits. See §Resilience & Observability Design for the questions to answer. Present it as: proposta → alternative → costo. The user can slim it down; they cannot be left unaware of it. Record any reduction under `Waived / deferred` in `HANDOFF.md`.

**Exit:** User approved design. Design doc saved to `docs/superpowers/specs/`. If IS_GREENFIELD: design doc contains an approved Error & Logging Strategy section.
**Completion:** Update `.dev-pipeline-state.json`: add `1` to `completedPhases`. Announce: "✅ Phase 1: Brainstorm complete. Design doc saved. Next: Phase 2 or 3."

### Resilience & Observability Design (IS_GREENFIELD)

Answer every line. "Non serve" is a valid answer **only if written down with a reason** — a blank is a gap, not a decision.

**Errori**
1. **Tassonomia** — quali errori esistono: attesi (validazione/dominio), esterni (rete, API, DB, filesystem), bug interni. Un tipo/classe per famiglia, non stringhe sparse.
2. **Confini di cattura** — dove si catturano: top-level dell'entrypoint (CLI `main`, handler HTTP, consumer del job) + i confini di I/O. In mezzo si propaga, non si inghiotte.
3. **Wrapping** — errore rilanciato preservando la causa originale (`cause`, `from e`, `%w`). Mai perdere lo stack.
4. **Mappatura in uscita** — errore interno → exit code / HTTP status / messaggio utente. Il messaggio all'utente non espone stack, path interni, query, o segreti.
5. **Transient vs permanente** — cosa si ritenta: retry con backoff+jitter, tetto ai tentativi, idempotenza garantita. **Timeout esplicito su ogni chiamata esterna** (default della libreria = nessun timeout, quasi sempre).
6. **Cleanup** — risorse rilasciate anche sul percorso di errore (file, connessioni, lock, subprocess). Shutdown ordinato su SIGINT/SIGTERM.
7. **Fail fast** — config e credenziali validate all'avvio, non alla prima richiesta.
8. **Errori mai silenziati** — nessun `catch {}` vuoto, nessun `except: pass`. Se è deliberato, serve un commento con il perché.

**Log**
9. **Libreria** — riusare quella già nel progetto. Se assente: structured logger dello stdlib/ecosistema, non `print`/`console.log` sparsi. Nessuna nuova dipendenza se lo stdlib basta.
10. **Livelli** — quando si usa ognuno: ERROR (azione umana necessaria), WARN (degradato ma gestito), INFO (eventi di business ai confini), DEBUG (diagnostica). Livello configurabile via env/flag.
11. **Formato e sink** — JSON strutturato per servizi/log aggregati; leggibile su TTY per CLI. Dove finisce (stdout/stderr, file, collector) e con quale rotazione/retention.
12. **Campi obbligatori** — timestamp, level, component/modulo, evento, e un **correlation/request id propagato** lungo tutta la richiesta.
13. **Redazione** — password, token, chiavi, PII mai loggati. Redazione centralizzata, non affidata al chiamante.
14. **Cosa si logga ai confini** — ogni chiamata esterna: esito + durata. Serve per diagnosticare senza un debugger.
15. **Anti-duplicazione** — non loggare *e* rilanciare lo stesso errore a ogni livello: si logga dove si gestisce. Niente log dentro hot loop.

**Proporzione:** uno script one-shot ha bisogno dei punti 2, 4, 8, 9, 10 — non di 15 punti. Un servizio con integrazioni esterne li vuole tutti. Proponi il sottoinsieme adatto alla magnitudine e dillo esplicitamente.

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
2. Implement the change directly (no plan, no subagents).
3. Run verification: full test suite or build fallback. On failure: debug and fix.
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
5. If `status: FAILED` → announce failure details, ask user: retry / manual fix / abort.

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

Verify the implemented code against the 15 points of §Resilience & Observability Design. Read the actual changed files — do not infer from the plan. Classify each gap:

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

Non-greenfield tasks: skip this step, but still report any CRITICAL row spotted in the diff as a normal Phase 8.5 CRITICAL finding.

Update state:
```json
{ "observabilityGate": { "critical": 0, "warnings": { "fixed": 0, "waived": 0 }, "passed": true } }
```

Gate G2.5b passes when zero CRITICAL remain and every WARNING is fixed or explicitly waived by the user.

### Step 3: Remediation

- **CRITICAL findings:** Fix ALL before proceeding. Max 3 remediation cycles (fix → re-check → fix).
- **WARNING findings:** Fix unless user explicitly waives. List waived items in pipeline state.
- **INFO findings:** Report to user, no blocking.
- After fixes: re-run verification (test suite) to ensure fixes don't break anything.

### Step 4: Gate check

Gate G2.5 passes when: zero CRITICAL findings remain AND all WARNING findings are fixed or waived.
Gate G2.5b (IS_GREENFIELD only) passes per Step 2b. Both must pass to leave Phase 8.5.

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

Council the implementation for ship-readiness (correctness, quality, completeness, risk). Include: what was built, implementation summary, test results, review findings (from Workflow result), audit results, diff stats. **If IS_GREENFIELD:** include the Error & Logging Strategy as approved plus the G2.5b outcome (gaps found, fixed, waived) — the council reviews whether the resilience story is adequate for what is shipping. **If Phase 8.6 ran:** include UI Quality Gate results (detect findings, audit score + dimension breakdown, critique heuristic scores if available, remediation actions taken, waived items). **Invoke:** `Skill(llm-council)`.
- **GO** → Phase 10. **NO-GO** → Council Remediation Loop: extract feedback, re-run Workflow with council feedback as additional context, re-council. Max 5 iterations (see Protocols).
**Completion:** Update `.dev-pipeline-state.json`: add `9` to `completedPhases`, set `gates.shipCouncilGO: true`. Announce: "✅ Phase 9: Ship Council complete. Verdict: GO. Next: Phase 10."

## Phase 10: Docs Check (always)

**PRE-CONDITION CHECK:** If magnitude is STANDARD or COMPLEX, verify that Phase 9 (Ship Council) was executed and returned GO before proceeding. If Phase 9 was not executed, STOP and run it now.

Scan changed files. Check: README, CLAUDE.md, API docs, inline docs (JSDoc/TSDoc), design doc (mark IMPLEMENTED), changelog. Update stale docs, commit separately. If no docs impacted: "No documentation updates needed."
**Completion:** Update `.dev-pipeline-state.json`: add `10` to `completedPhases`. Announce: "✅ Phase 10: Docs complete. Next: Phase 10.5."

## Phase 10.5: Knowledge Quiz (always)

Quiz sull'implementazione appena completata. Scopo: il developer mantiene il polso sul codice che Claude ha scritto. Non bloccante — risultato informativo.

### Question Generation

Genera domande in italiano basate su:
- **File modificati** (`git diff --name-only`) — "Quale file gestisce X?"
- **Logica chiave** — "Come funziona il nuovo Y?" / "Perché Z usa questo pattern?"
- **Decisioni di design** — "Perché abbiamo scelto A invece di B?"
- **Edge case gestiti** — "Cosa succede se l'input è vuoto/nullo/enorme?"
- **Errori e log** (obbligatoria se IS_GREENFIELD, ≥1 domanda) — "Cosa succede se la chiamata a X va in timeout?" / "Dove viene catturato l'errore Y e cosa vede l'utente?" / "A quale livello viene loggato Z e perché?"
- **Test scritti** — "Quale scenario copre il test T?"
- **Dipendenze** — "Quale modulo esistente viene riusato e perché?"

Mix: ~40% domande su COSA è cambiato, ~30% su COME funziona, ~30% su PERCHÉ (decisioni).

### Adaptive Depth

- **TRIVIAL:** 5 domande.
- **STANDARD:** 10 domande.
- **COMPLEX:** 10 domande + 2 bonus architetturali su trade-off e alternative scartate.

### Format

Presenta tutte le domande numerate in un blocco. User risponde (anche sinteticamente, anche in batch). Claude valuta ogni risposta:
- ✅ Corretta
- ⚠️ Parziale — aggiunge dettaglio mancante
- ❌ Errata — spiega risposta corretta con riferimento a file:linea

### Scoring

Report finale: X/N corrette, Y parziali, Z errate. No gate — quiz non blocca Phase 11. Risultato puramente informativo.

**Completion:** Update `.dev-pipeline-state.json`: add `10.5` to `completedPhases`, set `knowledgeQuiz: { total: N, correct: X, partial: Y, wrong: Z }`. Announce: "✅ Phase 10.5: Knowledge Quiz complete. Score: X/N. Next: Phase 11."

## Phase 11: Finish (always)

**STANDARD/COMPLEX:** `Skill(superpowers:finishing-a-development-branch)`.
**TRIVIAL (no worktree):** Show `git diff --stat`, ask user: A) Commit, B) Leave unstaged, C) Discard.

**Completion announcement:** Feature, magnitude, council iterations (or N/A), audits run, docs updated, result.
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

**Pipeline state** persisted to `.dev-pipeline-state.json` after every phase completion, reclassification, and remediation cycle. Fields: task, magnitude, isGreenfield, currentPhase, completedPhases, rollbackSHA, remediationCounts, designDoc, planDoc, worktreePath, startedAt, impeccableGate, observabilityGate, uiQualityGate, knowledgeQuiz.

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

## Goal
<2-4 sentences: what the user asked for, in their terms, and the acceptance
condition — how we know it's done. Not a phase list.>

## Where we are
Phase <N>: <name> — <one line on what is in flight right now>
Completed: <list>  |  Remaining: <list>
Gates: designCouncil=<GO/–> shipCouncil=<GO/–> impeccable=<pass/–> observability=<pass/n-a> ui=<pass/–>

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
- ❌ <what was tried> → <how it failed, exact error text> → <resolved how, or still open>
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
- **Errors verbatim.** Quote exact error text in `Failures & dead ends` — paraphrased errors are ungreppable.
- Keep it under ~150 lines. If a section is empty, drop the heading.
- Prose is terse and mechanical; this is a note to a Claude with zero memory, not a report.
- Never put secrets, tokens, or credentials in it — it is a plaintext file in the repo.
