---
description: Enterprise TypeScript / JavaScript Strict Typing, Concurrency & Immutability Directives
globs: ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx", "**/*.mjs"]
---

# ⚡ Enterprise TypeScript / JavaScript Cognitive Directives

## 1. Strict Typing & Typestate Modeling
- Enforce `strict: true` in tsconfig. Avoid `any` under all circumstances; use `unknown` with narrowing type guards.
- Use discriminated unions for domain state transitions:
  ```typescript
  type State =
    | { readonly status: "idle" }
    | { readonly status: "loading"; readonly startedAt: number }
    | { readonly status: "success"; readonly data: Payload }
    | { readonly status: "error"; readonly error: Error };
  ```
- Use Branded Nominal Types for identifiers to eliminate primitive obsession:
  ```typescript
  declare const brand: unique symbol;
  type Brand<T, B> = T & { readonly [brand]: B };
  type UserId = Brand<string, "UserId">;
  ```
- Enforce compile-time exhaustiveness checking on discriminated unions with `assertNever`:
  ```typescript
  function assertNever(x: never): never {
    throw new Error(`Unexpected object: ${x}`);
  }
  ```
- Prefer immutable data patterns (`readonly`, `ReadonlyArray<T>`, `as const`).

## 2. Concurrency & Floating Promise Elimination
- Always await, return, or explicitly catch every Promise. Floating unhandled promises are strictly forbidden.
- Propagate cancellation tokens using `AbortController` and `AbortSignal`:
  ```typescript
  async function fetchData(url: string, signal: AbortSignal): Promise<Data> {
    const res = await fetch(url, { signal });
    return res.json();
  }
  ```
- Bound concurrent network or filesystem operations using `p-limit` or sized worker pools.
- Eliminate ReDoS risks: avoid nested quantifiers in RegExp.

## 3. Web & Security Standards
- Sanitize all dynamic HTML assignments using `DOMPurify.sanitize()` prior to DOM insertion.
- Prevent prototype pollution by avoiding unvalidated deep object merges.
- Ensure 44x44px minimum touch targets and zero horizontal scroll on mobile viewports.
