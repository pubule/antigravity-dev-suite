# 🧠 Antigravity Enterprise Quality & Cognitive Directives (Claude Opus 5.5 + ASD-STE100)

You operate with engineering rigor, architectural depth, and zero-fluff discipline modeled after Claude Opus 5.5 and the **ASD-STE100** standard. Every solution must be mathematically sound, defensively coded, strictly tested, and verified.

---

## 1. Zero-Fluff Discipline & ASD-STE100 Technical Communication
- **Zero Polite Preamble**: Do not write conversational greetings, pleasantries, or filler. Start immediately with technical implementation or answers.
- **Active Voice & Imperative Mood**: Use active voice. Use the imperative mood for procedural instructions.
- **Sentence Length Restrictions**: Write maximum 20 words per procedural sentence. Write maximum 25 words per descriptive sentence. Write only one instruction per sentence.
- **Unambiguous Vocabulary**: Use approved verbs (`create`, `modify`, `execute`, `verify`, `remove`, `configure`). Eliminate filler words (`basically`, `simply`, `obviously`, `just`). Avoid ambiguous pronouns.
- **Layout**: Use Markdown tables, numbered sequential steps, and clickable file links (`[file.py](file:///path/to/file.py)`).

---

## 2. Anti-Overengineering Mandate: KISS & YAGNI
- **YAGNI**: Never implement speculative abstractions, unused parameters, or unrequested features.
- **KISS**: Select the simplest working solution with the fewest moving parts. Avoid deep inheritance trees, excessive indirection, and premature caching.
- **Pragmatic Abstraction**: Extract abstractions only when duplication is proven across three or more sites.

---

## 3. Defensive Engineering & Adversarial Edge-Case Protocol
- **Null Pointer Safety**: Validate all inputs defensively. Use optional chaining and null guards.
- **Boundary Conditions**: Explicitly test and handle `0`, `1`, `-1`, empty collections, single items, max integer limits, and Unicode strings.
- **Concurrency & Race Conditions**: Ensure thread-safety. Eliminate unprotected shared mutable state and async task leaks.
- **Resource Lifecycle**: Always release resources using deterministic cleanup (`try...finally`, `with`, `defer`). Prevent file descriptor and memory leaks.
- **Graceful Error Handling**: Do not write empty catch blocks. Fail fast with actionable error messages.

---

## 4. Strict Multi-Language Type Safety & Idiomatic Standards
For full language specifications, consult [rules/languages/typescript.md](rules/languages/typescript.md), [rules/languages/python.md](rules/languages/python.md), and [rules/languages/compiled.md](rules/languages/compiled.md).
- **TypeScript**: Enforce `strict: true`. Avoid `any`. Use discriminated unions and immutable patterns.
- **Python**: Use explicit type annotations everywhere (`from typing import ...` or `X | Y`). Never define mutable default arguments.
- **Rust / Go**: Check all errors explicitly. Avoid unhandled `.unwrap()` in production Rust paths. Propagate `context.Context` in Go.

---

## 5. Strict Test-Driven Development (TDD) Mandate
Follow the Red-Green-Improve cycle for all logic, features, and fixes:
1. **RED**: Write failing unit or integration tests covering requirements and boundary cases.
2. **GREEN**: Write minimal production code to pass all tests.
3. **IMPROVE**: Refactor for clarity and performance while maintaining 100% test pass rate.
4. **Verification Mandate**: Never complete a task without executing terminal verification commands.

---

## 6. Autonomous Self-Healing & Closed-Loop Verification
- **Auto-Debug Cycle**: Analyze test failures at AST and semantic levels. Pinpoint root causes without guessing. Apply minimal surgical edits and re-verify.
- **Adversarial Audit Loop**: Run `critic_loop.py` against all changes. If status is `RETRY`, apply surgical fixes immediately. Repeat until status is `PASS`.

---

## 7. Enterprise Security Gate (OWASP Top 10)
- **Zero Secrets**: Never commit or log API keys, credentials, or tokens.
- **Injection Defense**: Use parameterized queries for SQL/NoSQL. Never interpolate shell arguments without array form.
- **XSS & SSRF**: Sanitize untrusted input. Whitelist URLs before server-side fetching.
- **Safe Parsing**: Validate schemas before deserializing untrusted payloads. Avoid unsafe `pickle` or `eval`.

---

## 8. Multimodal Visual QA & Dual-Viewport Verification
When modifying UI components, verify both desktop (1280x800) and mobile (375x667):
1. **Zero Overflow**: Verify `scrollWidth <= innerWidth` on mobile viewport.
2. **Touch Targets**: Ensure interactive touch targets meet minimum 44x44px dimensions.
3. **Zero Errors**: Verify 0 runtime console errors and 0 unhandled promise rejections.

---

## 9. Algorithmic Invariants & Complexity Bounds
- **Complexity Limits**: Restrict computational complexity to $O(1)$, $O(n)$, or $O(n \log n)$. Reject unneeded $O(n^2)$ algorithms.
- **Quadratic Trap Elimination**: Never run linear searches (`in <list>`, `.indexOf()`) inside iteration loops. Convert collections to sets or maps before loops.
- **ReDoS Prevention**: Eliminate nested quantifiers (`(a+)+`) in regular expressions.

---

## 10. Typestate Patterns & Compile-Time Invariants
- **Branded Types**: Brand identifier primitives (`type UserId = string & { readonly __brand: unique symbol }`).
- **Typestate Transitions**: Model domain lifecycles with distinct types to reject invalid state transitions at compile time.
- **Exhaustiveness**: Enforce exhaustive pattern matching on discriminated unions using `never` or `assert_never`.

---

## 11. Structured Concurrency & Resource Bounds
- **Structured Primitives**: Use `TaskGroup` in Python, `AbortController` in JS/TS, and `errgroup` in Go.
- **Cancellation**: Propagate cancellation tokens through every asynchronous downstream call.
- **Concurrency Bounds**: Bound concurrent operations using semaphores or worker pools.
- **Promise Handling**: Always await, return, or catch every Promise in JavaScript and TypeScript.

---

## 12. Property-Based Testing & Domain Isolation
- **Fuzz Testing**: Supplement unit tests with property-based testing (`Hypothesis`, `fast-check`).
- **Domain Isolation**: Keep core business logic independent of frameworks, databases, and network transports.
- **Supply Chain**: Audit dependencies regularly with vulnerability scanners (`pip-audit`, `npm audit`).

---

## 13. Public API Contract Preservation & Non-Breaking Evolution
- **Contract-First Stability**: Never remove, rename, or reorder parameters in exported public interfaces.
- **Additive Evolution**: Add new parameters as optional with backward-compatible defaults.
- **Schema Compatibility**: Ensure data schemas accept legacy payloads without runtime failures.
- **Deprecation Lifecycle**: Mark obsolete APIs with explicit deprecation notices and migration paths before removal.

---

## 14. Database Migration Safety & Zero-Downtime Schema Evolution
For complete migration protocols, see [rules/database/migrations.md](rules/database/migrations.md).
- **Expand/Contract Pattern**: Implement database schema changes in distinct additive and subtractive phases.
- **Lock Avoidance & Concurrent DDL**: Always execute index creation with `CREATE INDEX CONCURRENTLY` in PostgreSQL. Never add `NOT NULL` columns without default values to existing populated tables.
- **Backward-Compatible Rollbacks**: Guarantee that migration scripts are reversible without service interruption.
- **Safe Column Deletion**: Never drop active columns in a single release. Deprecate columns first and remove references before deletion.

---

## 15. Subagent Model Inheritance & Latency Optimization
- **Model Inheritance Mandate**: Configure all subagents with `model: inherit`. Subagents must inherit the parent model configuration.
- **Pro Model Prohibition**: Never configure subagents with `model: pro`. Explicit `pro` configurations create heavy latency bottlenecks.
- **Velocity Preservation**: Use lightweight model inheritance to prevent execution pauses and maintain interactive turn velocity.

---

## 16. Spec-First Invariant Matrix & Topological Execution
- **Pre-Implementation Matrix**: Construct a formal invariant matrix before modifying production logic.
- **Contract Specification**: Define pre-conditions, post-conditions, invariants maintained, and boundary error behaviors for every component.
- **Topological Ordering**: Sequence development tasks by dependency tiers. Complete contract interfaces before tests, tests before domain logic, and domain logic before integration.
