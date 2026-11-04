# /dev — Magnitude-Aware SDLC Pipeline Suite

Deterministic, magnitude-aware SDLC pipeline for **Claude Code**.
Automates software engineering from idea to release-ready code by scaling ceremony (triage, brainstorming, design councils, structured planning, isolated TDD worktrees, adversarial code reviews, and quality gates) based on task magnitude.

Includes interactive visual documentation: see [`README.html`](./README.html).

---

## ⚡ Key Capabilities

- **Deterministic Routing Table:**
  - **TRIVIAL:** Quick fixes, typos, dependency bumps (skips councils and worktrees; executes fast verification and scoped audits).
  - **STANDARD:** New features, non-trivial bugs (brainstorming, implementation plans, parallel workflows, ship council).
  - **COMPLEX:** Architectural changes, new modules, security-sensitive work (Design Council, rigorous planning, dual adversarial reviews).
- **Enforced Quality Gates:**
  - **Gate G1:** Design Council GO mandatory for COMPLEX tasks.
  - **Gate G2:** Implementation plan saved to disk for STANDARD+.
  - **Gate G2.5:** Impeccable Quality Gate for coding standards, error handling, and test conventions.
  - **Gate G2.5b:** Resilience & Observability Strategy verification for greenfield code.
  - **Gate G2.6:** UI Quality Gate for frontend code (anti-pattern and accessibility scans).
  - **Gate G3:** Ship Council GO mandatory prior to documentation and release.
- **Parallel Workflow Engine:** Runs TDD tasks across isolated git worktrees in parallel, merges changes deterministically, runs self-healing auto-debug loops, and executes adversarial review refutation.
- **Session Recovery & Handoff:** State persistence in `.dev-pipeline-state.json` paired with a human-readable `HANDOFF.md` to safely resume interrupted tasks across `/clear`, compaction, or terminal restarts.

---

## 📦 Prerequisites

1. **Git** (available in system `PATH`)
2. **Node.js** (v18+ recommended; already required by Claude Code)
3. **Claude Code CLI** (`npm install -g @anthropic-ai/claude-code`)

---

## 🚀 Quickstart Installation (Option 2)

Setup scripts verify prerequisites, install required dependencies (`superpowers` and `llm-council`), and register the `/dev` suite.

### macOS / Linux
```bash
git clone <REPO_URL>
cd antigravity-dev-suite
chmod +x setup.sh
./setup.sh
```

### Windows (PowerShell)
```powershell
git clone <REPO_URL>
cd antigravity-dev-suite
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

### Or via Claude Code Marketplace
```bash
/plugin marketplace add <owner>/<repo>
/plugin install dev --marketplace <owner>/<repo>
```

---

## 🧩 Dependencies Installed by Setup

The setup script automatically wires together:

| Dependency | Type | Role in Pipeline |
|---|---|---|
| `superpowers@claude-plugins-official` | Claude Code Plugin | Brainstorming, plan generation, git worktree management, branch finalization |
| `llm-council` | Claude Code Skill | Multi-perspective Design Council (Phase 2) and Ship Council (Phase 9) |
| `dev` | Plugin / Skill | SDLC pipeline orchestrator, handoff detector hook, parallel workflow execution |

---

## 🛠️ Usage

Inside any Claude Code session in your project root:

```bash
# Interactive launch
/dev

# Or with task description
/dev implement retry with exponential backoff on HTTP client
```

### Resuming Interrupted Work

When a session is cleared or interrupted:
- The `SessionStart` hook detects any active `HANDOFF.md` in progress.
- Run `/dev`: the pipeline inspects state and prompts you to resume from the exact interrupted phase without repeating completed work.

---

## 🗑️ Uninstallation

- **macOS / Linux:** `./uninstall.sh`
- **Windows:** `powershell -ExecutionPolicy Bypass -File .\uninstall.ps1`

---

## 📄 License

MIT License. See [LICENSE](./LICENSE).
