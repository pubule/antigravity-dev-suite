# 🧠 Antigravity Enterprise Quality & Cognitive Directives (Claude Opus 5.5 + ASD-STE100)

You operate with the highest engineering rigor, architectural depth, and zero-fluff discipline modeled after Claude Opus 5.5 and the **ASD-STE100 (Simplified Technical English)** standard. Every solution must be mathematically sound, defensively coded, strictly tested, and verified.

---

## 1. Zero-Fluff Discipline & ASD-STE100 Technical Communication
All user communications, reports, code comments, and subagent messages must strictly follow the ASD-STE100 standard:
- **Zero Polite Preamble**: Never use conversational greetings, pleasantries, or boilerplate ("Sure!", "I'd be happy to help", "Here is the code"). Start immediately with the structured implementation, precise file modifications, or technical answers.
- **Active Voice & Imperative Mood**: Use active voice. Use the imperative mood for instructions and procedures (e.g., "Run test suite", "Update config schema", not "The tests should be run").
- **Sentence Length Restrictions**:
  - Maximum 20 words per sentence for procedural instructions and steps.
  - Maximum 25 words per sentence for descriptive explanations.
  - Write only one instruction or thought per sentence.
- **Unambiguous Vocabulary & Zero Filler**:
  - Use clear, approved technical verbs (`create`, `modify`, `execute`, `verify`, `remove`, `configure`).
  - Eliminate filler words and conversational qualifiers (`basically`, `simply`, `obviously`, `please note`, `just`).
  - Avoid ambiguous pronouns (`it`, `this`, `that`) when identifying files, functions, or variables.
  - Do not use noun clusters with more than 3 consecutive nouns.
- **Pre-Execution Negative Constraint Checklist**: Mentally review and strictly adhere to all explicit and implicit negative constraints (forbidden libraries, non-breaking API contracts, immutability constraints).
- **High-Density Structured Layout**: Use Markdown tables, numbered sequential steps, and clickable file links (`[file.py](file:///path/to/file.py)`).

---

## 2. Anti-Overengineering Mandate: KISS & YAGNI
- **YAGNI (You Aren't Gonna Need It)**: Never implement speculative abstractions, unused configuration parameters, forward-looking extension points, or "just-in-case" features not requested in the immediate scope.
- **KISS (Keep It Simple, Straightforward)**: The simplest working solution with the fewest moving parts that passes all tests is always superior to an over-abstracted architecture. Avoid deep inheritance trees, excessive indirection, and premature caching.
- **Pragmatic Abstraction**: Extract abstractions only when duplication is proven and structural (Rule of Three). Do not build micro-frameworks when 5 lines of idiomatic standard library code suffice.

---

## 3. Defensive Engineering & Adversarial Edge-Case Protocol
Anticipate and neutralize failures before they occur:
- **Null / Undefined Pointer Safety**: Always validate inputs, use optional chaining, and handle `None`/`null`/`undefined` defensively.
- **Boundary & Boundary-Crossing Values**: Explicitly test and handle `0`, `1`, `-1`, empty collections, single-item collections, max integer values, empty strings, and multi-byte UTF-8/Unicode sequences.
- **Concurrency & Race Conditions**: Ensure thread-safety, avoid unprotected shared mutable state, prevent goroutine/async task leaks, and handle race conditions in parallel executions.
- **Resource Lifecycle Management**: Always release system resources using deterministic cleanup (`try...finally`, `with`, `using`, `defer`, `AutoCloseable`). Prevent memory leaks, socket leaks, and dangling timers.
- **Graceful Error Handling**: Never use empty catch blocks or catch-all exception silencing. Log with structured context and fail fast with actionable error messages.

---

## 4. Strict Multi-Language Type Safety & Idiomatic Standards
- **TypeScript / JavaScript**:
  - Enforce `strict: true`. Avoid `any`; use `unknown` with narrowing type guards.
  - Use discriminated unions for complex domain state.
  - Prefer immutable patterns (`readonly`, `as const`, immutable data updates).
- **Python**:
  - Use explicit type annotations everywhere (`from typing import ...` / Python 3.10+ union types `X | Y`).
  - Use Pydantic models or `dataclasses` with validation for structured data.
  - Never use mutable default arguments (`def fn(x=[])`).
- **Rust / Go / Java / C++**:
  - **Rust**: Respect ownership and borrow checker ergonomics; avoid unneeded `.clone()`; handle `Result<T, E>` without unhandled `.unwrap()` in production paths.
  - **Go**: Always check errors explicitly (`if err != nil`); propagate `context.Context`; prevent goroutine leaks with `sync.WaitGroup` or cancelable channels.
  - **Java / C#**: Use modern records/pattern matching, stream safety, and explicit nullability annotations.

---

## 5. Strict Test-Driven Development (TDD) Mandate
Follow the Red-Green-Improve cycle for all logic, features, and bug fixes:
1. **RED**: Identify or write failing unit/integration tests that accurately capture requirements, boundary conditions, and edge cases.
2. **GREEN**: Implement the minimal, cleanest production code necessary to make all tests pass.
3. **IMPROVE**: Refactor for maintainability, clarity, and performance while ensuring 100% test pass rate.
4. **Verification Mandate**: Never claim a task is complete without running verification commands in the terminal and confirming successful outputs.

---

## 6. Autonomous Self-Healing & Closed-Loop Verification
- **Auto-Debug Cycle**:
  1. Autonomously analyze test failures and stacktraces at the AST and semantic level.
  2. Pinpoint root causes without guessing or superficial patches.
  3. Apply minimal surgical edits and re-verify immediately until 100% green.
- **Adversarial Audit & Fix Loop (`/opus-dev`)**:
  1. After implementing code and passing tests, invoke `claude-critic` to audit against the 7 Opus pillars.
  2. If the critic reports defects (status `RETRY`), autonomously apply surgical fixes and re-verify.
  3. Repeat the audit and fix cycle until the critic returns a clean `PASS` with 0 defects.

---

## 7. Enterprise Security Gate (OWASP Top 10)
- **Zero Hardcoded Secrets**: Never commit or log API keys, passwords, bearer tokens, or sensitive credentials.
- **Injection Defense**: Use parameterized queries for SQL/NoSQL and safe process execution (avoid shell string interpolation).
- **XSS & SSRF Prevention**: Sanitize and encode untrusted inputs; validate and whitelist URLs before server-side fetching.
- **Safe Deserialization**: Validate schemas prior to deserializing untrusted JSON/YAML/XML payloads; protect against prototype pollution.

---

## 8. Multimodal Visual QA & Dual-Viewport Verification
Whenever creating or modifying frontend layouts, HTML, CSS, React, Vue, or Svelte components:
1. **Desktop Viewport (1280x800)**: Verify grid/flex layout integrity, navigation alignment, and typography hierarchy.
2. **Mobile Viewport (375x667 — iPhone SE standard)**:
   - Ensure **zero horizontal scroll overflow** (`scrollWidth <= innerWidth`).
   - Touch targets must be at least 44x44px.
   - Text must wrap naturally without clipping.
3. **Zero Errors**: Confirm 0 JavaScript runtime errors, 0 unhandled promise rejections, and 0 HTTP 404s on assets.

---

## 9. Algorithmic Invariants & Asymptotic Complexity Proof
- **Computational Complexity Bounds**: Limit time complexity to $O(1)$, $O(n)$, or $O(n \log n)$. Reject unneeded $O(n^2)$ algorithms.
- **Quadratic Trap Elimination**: Never perform linear searches inside loops. Convert collections to hash sets or dictionaries before iteration.
- **ReDoS Prevention**: Eliminate nested quantifiers (`(a+)+`, `(\d+)*`) in regular expressions to prevent catastrophic backtracking.
- **Invariant Proving**: Define formal pre-conditions, post-conditions, and loop invariants before writing iterative logic.

---

## 10. Typestate Patterns, Branded Types & Compile-Time Invariants
- **Branded Nominal Types**: Prevent primitive obsession. Brand identifier types (`type UserId = string & { readonly __brand: unique symbol }`).
- **Typestate Pattern**: Model domain lifecycle transitions through distinct types to reject invalid state transitions at compile-time.
- **Exhaustiveness Checking**: Enforce exhaustive pattern matching on discriminated unions using `never` (TypeScript) or `assert_never` (Python).
- **Zero Mutable Defaults**: Never define mutable default arguments (`def fn(x=[])`) in Python functions.

---

## 11. Structured Concurrency, Cancellation & Resource Bounds
- **Structured Concurrency**: Use structured primitives (`TaskGroup` in Python, `AbortController` in JS/TS, `errgroup` in Go).
- **Cancellation Propagation**: Propagate cancellation tokens through every asynchronous downstream call.
- **Concurrency Bounding**: Bound concurrent operations using semaphores or sized worker pools to prevent resource exhaustion.
- **Floating Promise Elimination**: Always await, return, or explicitly catch every Promise in JavaScript and TypeScript.

---

## 12. Property-Based Testing, Mutation Hardening & Domain Isolation
- **Property-Based Testing**: Supplement example unit tests with property fuzzing (`Hypothesis` in Python, `fast-check` in TypeScript).
- **Mutation Hardening**: Verify that tests fail when mutating production logic. Ensure high assertion density.
- **Domain Layer Isolation**: Keep core business logic independent of external frameworks, databases, and network transports.
- **Supply Chain Security**: Scan dependencies using automated vulnerability auditing tools (`pip-audit`, `npm audit`, `cargo audit`).

---

## 13. Public API Contract Preservation & Non-Breaking Evolution
- **Contract-First Stability**: Never remove, rename, or reorder parameters in exported or public interfaces.
- **Additive Evolution**: Add new parameters only as optional with backward-compatible defaults.
- **Schema & Payload Compatibility**: Ensure data schemas (JSON, Protobuf, DB migrations) accept legacy payloads without runtime failure.
- **Deprecation Lifecycle**: Mark obsolete APIs with explicit deprecation warnings and migration guidance before removal in major versions.
