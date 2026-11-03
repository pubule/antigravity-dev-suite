# Antigravity Quality Directives (Claude Opus 5.5 Standard + ASD-STE100)

Write correct, tested, verified code. Machines check your work: read section 0 first.

---

## 0. How Your Work Is Verified (Enforced)

These rules are enforced by hooks. You cannot finish a task while they fail.

1. **Stop gate.** When you try to finish, the suite runs these checks on every file you changed (including committed files and new folders):
   - syntax and structure of each changed file;
   - static critic (secrets, empty `except`, mutable defaults, quadratic traps, unsafe patterns);
   - **test-first**: a changed production file needs a new or changed test file;
   - typecheck, and lint on the lines you changed;
   - the project test suite;
   - **visual QA** when you change UI files (`.tsx .jsx .vue .svelte .astro .html .css .scss`): the gate opens the page in Chromium at 1280x800 and 375x667, compares it with the base commit, and blocks on new JS errors, console errors, failed requests, mobile overflow and WCAG violations. Pages that look different must be reviewed once.
2. **If the gate blocks you**, the reason lists each failure. Fix the cause. Then finish again.
   - **Review points** ("needs a second look") are not failures. Answer each one: fix it, or say why it is intended. Then finish again.
   - "Your tests pass without your change" means your test proves nothing. Make it fail on the old code.
   - "Public API changed" means callers may break. Check every caller before you finish.
3. **Never weaken the checks.** Do not delete, skip or loosen tests. Do not add `# nosec` to silence a finding you did not fix. Do not edit `.agents/agy.json`. Do not use `--no-verify`. The guard blocks these actions.
4. **Run the gate yourself** before you finish. Use the command from the gate message, or:
   - macOS / Linux: `python3 ~/.gemini/config/plugins/antigravity-dev-suite/scripts/agy_hook.py check`
   - Windows: `py -3 $HOME\.gemini\config\plugins\antigravity-dev-suite\scripts\agy_hook.py check`
5. **Report only verified results.** Quote the real command output. Never write "tests pass" without output that shows it.
6. **Syntax errors come back immediately.** After a bad edit, the next turn starts with the error. Fix it first.
7. **Read before you edit.** The guard refuses an edit to a file you have not opened in this conversation. Open it with `view_file` first.
8. **Acceptance criteria.** Before you change code, write `.agy/criteria.md` with 3 to 5 checkable behaviours (`- [ ] <behaviour> (proved by <test>)`). Before you finish, tick each one with its evidence (`- [x] <behaviour> — evidence: <test, output, screenshot>`). The gate fails while a criterion is unticked.
9. **Changed lines need tests.** When coverage is available, the gate lists the changed lines no test runs. Add tests for them, or say why a line cannot be tested.
10. **When the same failure comes back, stop guessing.** After two identical failures, reproduce, read the code path and test your hypotheses before the next edit. After four, stop and explain the problem to the user: what fails, what you tried, what you need.
11. **A stronger reviewer may read your diff** (when the project turns it on). Treat its findings like review points: fix the real ones with a test, and say why the others are wrong.

---

## 1. Work Method

1. **Read before you write.** Open the files you change and their callers. For a signature change, find all call sites first (`symbol_impact.py <symbol>`).
2. **Small steps.** Change one or two files per step. Verify each step before the next.
3. **RED, GREEN, IMPROVE.** Write a failing test. Write the minimum code that passes it. Then clean up with all tests green.
4. **Root cause, not symptoms.** When a test fails, find why. Do not patch the assertion.
5. **Stop and ask** when the request is ambiguous or a fix needs a large redesign.

---

## 2. Technical Communication (ASD-STE100)

- No greetings or filler. Start with the answer.
- Active voice, imperative mood. Maximum 20 words per instruction, one instruction per sentence.
- Use tables, numbered steps, and clickable file links.

---

## 3. Design: KISS & YAGNI

- Choose the simplest working design with the fewest moving parts.
- Do not add unrequested features, unused parameters, or speculative abstractions.
- Extract an abstraction only when the same code appears in three or more places.

---

## 4. Defensive Engineering

- Validate inputs. Handle `0`, `1`, `-1`, empty collections, `null`, Unicode, and limits.
- Release resources deterministically (`with`, `try...finally`, `defer`).
- No empty `catch`/`except` blocks. Fail fast with an actionable message.

---

## 5. Type Safety

Language details: [rules/languages/typescript.md](rules/languages/typescript.md), [rules/languages/python.md](rules/languages/python.md), [rules/languages/compiled.md](rules/languages/compiled.md).
- TypeScript: `strict: true`, no `any`, discriminated unions.
- Python: annotate every function. Never use mutable default arguments.
- Rust / Go: check every error. No unhandled `.unwrap()` in production paths.

---

## 6. Security (OWASP Top 10)

- Never write secrets, keys or tokens into files or logs.
- Use parameterized queries. Pass shell arguments as arrays.
- Validate untrusted input. Do not use `eval` or `pickle` on untrusted data.

---

## 7. Performance

- Keep algorithms at O(1), O(n) or O(n log n). No linear search inside a loop: build a set or map first.
- No nested regex quantifiers such as `(a+)+`.

---

## 8. Frontend

The Stop gate runs visual QA on every UI change. To pass it:
1. Start the dev server before you finish, unless `.agents/agy.json` lets the gate start it.
2. When the gate lists screenshots, open each one and look at it. Say what you see before you fix the code.
3. Fix the cause of each defect: zero console errors, no failed requests, no horizontal overflow at 375px.
4. Check what the page shows, not only the errors: text cut off, overlapping elements, wrong layout. The gate cannot judge these. You can.
5. When the gate shows "Visual changes to review", open each before, after and diff image. For each page, say what changed and whether you meant it. Fix the changes you did not mean.
6. Keep touch targets at 44x44px or more.

---

## 9. Concurrency

Use structured primitives (`TaskGroup`, `AbortController`, `errgroup`). Propagate cancellation. Bound parallel work. Await or handle every Promise.

---

## 10. Typestate & Invariants

Brand identifier types. Model lifecycles with distinct types. Make pattern matching exhaustive (`never`, `assert_never`).

---

## 11. Property-Based Testing

Add property tests (`Hypothesis`, `fast-check`) for parsers, serializers and pure algorithms.

---

## 12. Dependencies

Add a dependency only when needed. Audit with `pip-audit` or `npm audit`.

---

## 13. Public API Contract Preservation

- **Contract-First Stability**: never remove, rename or reorder parameters of exported interfaces.
- Add new parameters as optional with backward-compatible defaults. Deprecate before removal.

---

## 14. Database Migration Safety & Zero-Downtime Schema Evolution

Full protocol: [rules/database/migrations.md](rules/database/migrations.md).
- **Expand/Contract Pattern**: add first, migrate, remove in a later release.
- Use `CREATE INDEX CONCURRENTLY` in PostgreSQL. Never add a `NOT NULL` column without a default to a populated table.
- Every migration must be reversible.

---

## 15. Subagent Model Inheritance & Latency Optimization

- **Model Inheritance Mandate**: configure subagents with `model: inherit`.
- **Pro Model Prohibition**: never configure subagents with `model: pro`.
- **Independent review**: give a review subagent only the diff and the task, not your reasoning.

---

## 16. Spec-First Invariant Matrix & Topological Execution

- **Pre-Implementation Matrix**: for non-trivial logic, list pre-conditions, post-conditions and invariants before you write code.
- **Topological Ordering**: contracts, then tests, then domain logic, then integration.
