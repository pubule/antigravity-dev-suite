# Team Project Directives & Autonomous Quality Mandate

Welcome to the project! This repository uses the **Antigravity Dev Suite** standards to guarantee high quality, automated testing, and visual defect elimination.

## 1. Zero-Preamble & Technical Rigor
- Keep responses direct, structured, and free of conversational filler.
- Always provide fully typed code with explicit file paths.

## 2. Strict TDD (Red-Green-Refactor)
- Identify or write failing tests before implementing business logic.
- Implement minimal clean code to achieve 100% green tests.
- Never declare a task complete without executing test verification in terminal.

## 3. Playwright Visual QA (Frontend & UI Changes)
- For every UI/HTML/CSS/React/Vue modification, inspect layout in Dual-Viewport:
  - **Desktop**: 1280x800
  - **Mobile**: 375x667 (iPhone SE standard)
- Ensure 0 horizontal scroll overflow on mobile and 0 console errors.

## 4. Autonomous Auto-Debug & Self-Healing
- If compilation, typecheck, or tests fail, analyze the stacktrace and auto-fix without delegating routine fixes to developers.
