---
name: auto-debug
description: Autonomous test execution, stacktrace parsing, and auto-fix loop before task completion.
---

# Auto-Debug Skill

Use this skill to autonomously execute the project's test suite, capture failures, and fix them in a closed loop.

## Workflow
1. Detect project test framework (`npm test`, `pytest`, `cargo test`, `mvn test`).
2. Run tests in background.
3. If failures occur, parse root cause from stacktrace and apply minimal surgical fix.
4. Re-verify until green (max 3 cycles).
