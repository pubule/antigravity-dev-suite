# Antigravity Enterprise Quality & Verification Directives

## 1. Claude-Style Discipline & Pre-Execution Chain-of-Thought (CoT)
- **Zero Unrequested Preamble & Filler**: Start responses immediately with the structured solution, file modifications, or requested technical answers.
- **Negative Constraint Checklist**: Evaluate all explicit negative constraints before executing code.
- **Adversarial Edge-Case Critique**: Test boundary conditions, null/empty values, concurrency, and error handling.
- **Strict TDD & Evidence Mandate**: Write/identify failing tests first (RED), implement minimal solution (GREEN), and refactor with confidence (IMPROVE). Never claim success without executing verification commands.

## 2. Autonomous Self-Healing & Auto-Debug Loop
- When a build, test, lint, or typecheck error occurs, autonomously analyze the stacktrace, locate root causes, apply minimal fixes, and re-verify (up to 3 cycles) before asking the user.

## 3. Multimodal Visual QA & Dual-Viewport Verification
- Whenever modifying frontend layouts, HTML, CSS, React, Vue, or Svelte components:
  1. Inspect **Desktop Viewport (1280x800)** for grid/flex layout fidelity.
  2. Inspect **Mobile Viewport (375x667)** for touch targets and zero horizontal scroll overflow.
  3. Ensure 0 JavaScript runtime errors and 0 HTTP 404s on assets.
