# 🧠 Team Project Directives & Autonomous Quality Mandate (Claude Opus 5.5 Standard)

Welcome to the project! This repository uses the **Antigravity Dev Suite** standards to guarantee high architectural quality, automated testing, and visual defect elimination.

---

## 1. Zero-Preamble & Technical Rigor
- Keep responses direct, structured, and free of conversational filler.
- Always provide fully typed, defensively written code with explicit file links.
- Check and enforce all negative constraints prior to writing code.

## 2. Anti-Overengineering Mandate (KISS & YAGNI)
- **YAGNI**: Never implement speculative abstractions, unused parameters, or forward-looking extension points not required in the immediate scope.
- **KISS**: Favor the simplest working solution with the fewest moving parts that satisfies requirements and passes all tests.
- **Pragmatic Abstraction**: Extract abstractions only when duplication is proven and structural (Rule of Three).

## 3. Defensive Engineering & Edge Cases
- Handle `null`/`undefined`, empty collections, boundary conditions, and concurrency defensively.
- Manage resource lifecycles (`try...finally`, `with`, `defer`) to prevent socket/memory leaks.

## 4. Strict TDD (Red-Green-Improve)
- Write or identify failing tests before implementing business logic.
- Implement minimal clean code to achieve 100% green tests.
- Never declare a task complete without executing test verification in the terminal.

## 5. Playwright Visual QA (Frontend & UI Changes)
- For every UI/HTML/CSS/React/Vue modification, inspect layout in Dual-Viewport:
  - **Desktop**: 1280x800 px
  - **Mobile**: 375x667 px (iPhone SE standard)
- Ensure **0 horizontal scroll overflow** on mobile and 0 console errors.

## 6. Autonomous Auto-Debug & Self-Healing
- If compilation, typecheck, or tests fail, analyze the stacktrace at the AST level and auto-fix (up to 3 cycles) without delegating routine fixes to developers.
