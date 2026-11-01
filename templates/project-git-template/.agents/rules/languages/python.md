---
description: Enterprise Python 3.10+ Strict Typing, Defensive Concurrency & Testing Directives
globs: ["**/*.py", "**/*.pyi"]
---

# 🐍 Enterprise Python Cognitive & Engineering Directives

## 1. Multi-Pass Type Safety & Data Models
- Use explicit type annotations everywhere (`from typing import ...` / Python 3.10+ union types `X | Y`).
- Use Pydantic models (v2) or frozen dataclasses (`@dataclass(frozen=True, slots=True)`) for domain state.
- Never use mutable default arguments (`def fn(x=[])`). Use `None` as default sentinel.
- Prevent primitive obsession using `typing.NewType` or `typing.Annotated` for branded types:
  ```python
  from typing import NewType
  UserId = NewType("UserId", str)
  ```
- Enforce exhaustive pattern matching on discriminated unions using `typing.assert_never`:
  ```python
  from typing import assert_never
  match state:
      case Active(): ...
      case Inactive(): ...
      case _ as unreachable:
          assert_never(unreachable)
  ```

## 2. Structured Concurrency & Resource Safety
- Use structured concurrency via `asyncio.TaskGroup()` (Python 3.11+) instead of unconstrained `asyncio.gather()`.
- Propagate cancellation tokens and timeouts with `asyncio.timeout()`:
  ```python
  async with asyncio.timeout(5.0):
      async with asyncio.TaskGroup() as tg:
          task1 = tg.create_task(fetch_data())
  ```
- Always release resources using context managers (`with` / `async with`).
- Prevent memory leaks and dangling tasks by canceling background tasks in `finally` blocks.

## 3. Property-Based Testing & Verification
- Supplement unit tests with randomized property fuzzing using `Hypothesis`:
  ```python
  from hypothesis import given, strategies as st
  @given(st.integers(min_value=0), st.text(min_size=1))
  def test_invariant_holds(val: int, label: str): ...
  ```
- Verify mutation resistance using `python3 scripts/auto_debug_runner.py --mutation --diff`.
