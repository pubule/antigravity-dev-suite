# 🧠 Project Quality Directives & Standards (Claude Opus 5.5 + ASD-STE100)

This repository follows the **Antigravity Dev Suite** engineering standards:
- **Core Directives**: Defined in [`.agents/rules/AGENTS.md`](.agents/rules/AGENTS.md) (14 Architectural Rules).
- **Technical Communication**: ASD-STE100 (concise, active voice, imperative mood, zero fluff).
- **Architecture**: KISS and YAGNI (simplest working design, no premature abstractions).
- **Development**: Strict Test-Driven Development (RED -> GREEN -> IMPROVE).
- **Database Evolution**: Zero-downtime expand/contract migrations, non-blocking DDL, and reversible schema changes (Rule 14).
- **Public API Stability**: Automated contract drift detection preventing breaking changes (Rule 13).
- **Architecture Decision Records (ADRs)**: Document significant architectural choices under `docs/adr/`.
- **Verification**: Terminal verification evidence required before completion.
- **Frontend / UI & Accessibility**: Dual-viewport inspection (Desktop 1280x800 + Mobile 375x667) and WCAG 2.1 AA audit.

---

## ⚡ Active Slash Commands & Skills

- `/opus-dev`: Unified end-to-end autonomous engineering meta-engine.
- `/brainstorm`: Architectural trade-off analysis, KISS/YAGNI gating & ADR persistence.
- `/plan`: Milestone decomposition with explicit Red-Green TDD targets.
- `/auto-debug`: Multi-ecosystem closed-loop auto-debugger (Tests, Types, Race, Fuzz).
- `/code-review`: 5-Pass adversarial security, concurrency, typestate & typing audit.
- `/security-audit`: Cloudflare-inspired vulnerability harness (Hunter vs. Verifier, attack surfaces, findings.json, supply chain).
- `/benchmark`: Performance profiling, latency regression detection, and N+1 query audit.
- `/refactor`: Safe tech debt reduction preserving invariants and 100% green tests.
- `/commit`: Pre-commit verification pipeline with secret scans and Conventional Commits.
- `/visual-qa`: Dual-viewport Playwright visual inspector.

---

## 🔧 Pre-Commit Git Hook Installation

To install the automated pre-commit verification hook locally:
```bash
python3 scripts/install_git_hooks.py --install
# or via auto_debug_runner:
python3 scripts/auto_debug_runner.py --install-git-hooks
```
