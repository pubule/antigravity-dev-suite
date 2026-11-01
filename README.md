# 🚀 Antigravity Dev Suite (Claude Opus 5.5 + ASD-STE100 v1.12.0)

**Enterprise-Grade, 100% Cross-Platform Development & Cognitive Reasoning Suite for Google Antigravity (AGY)**.  
Combines the best engineering patterns from **`mega-mind`**, **`ECC (Everything Claude Code)`**, **`superpowers`**, the **Claude Opus 5.5 Standard**, and **ASD-STE100 (Simplified Technical English)**. Calibrated for maximum efficiency with **Flash and Pro models** across **macOS (Intel & Apple Silicon), Linux, and Windows 10/11**.

---

## 📐 ASD-STE100 Technical Communication Standard
The suite strictly enforces ASD-STE100 across all agent interactions, diagnostic reports, and code comments:
- **Active Voice & Imperative Mood**: Direct procedural instructions (`Execute test suite`, `Validate inputs`).
- **Controlled Sentence Length**: Maximum 20 words per procedural instruction, maximum 25 words per descriptive sentence.
- **Unambiguous Terminology**: One word = one meaning; zero conversational filler, jargon, or pleasantries.
- **Deterministic Tables & Schemas**: Dense tabular outputs, atomic tasks, and clickable markdown links.

---

## ⚡ Complete Slash Commands Matrix

Every skill in the suite is exposed as a first-class native slash command in Antigravity:

| Slash Command | Skill Module | Cognitive Phase | Key Capabilities |
| :--- | :--- | :--- | :--- |
| **`/opus-dev`** | `skills/opus-dev` | **Autonomous Meta-Engine** | Autonomous closed-loop engineering (*Design & Invariants $\to$ Plan $\to$ TDD & Properties $\to$ Auto-Debug & Benchmark $\to$ Adversarial Critic Loop until `PASS`*). |
| **`/brainstorm`**| `skills/brainstorm`| **Ideation & Architecture** | Explores **2-3 architectural approaches**, evaluates KISS/YAGNI trade-off matrix, defines algorithmic bounds ($O(n)$) and formal inductive invariants ($P, I, V, Q$). |
| **`/plan`** | `skills/plan` | **Milestone Decomposition** | Breaks down tasks into atomic Red-Green steps with explicit TDD targets, typestate transitions, and formal inductive invariants. |
| **`/auto-debug`**| `skills/auto-debug` | **Closed-Loop Auto-Fix** | Auto-detects 10+ test, coverage & mutation frameworks, parses stacktraces at AST level, auto-fixes up to 3 cycles. |
| **`/code-review`**|`skills/code-review`| **Adversarial Audit** | **5-Pass Inspection**: Invariants & Bounds, Concurrency & Leaks, OWASP Top 10 Security, Typestate & Strict Types, Property Fuzzing & Mutation Gate. |
| **`/commit`** | `skills/commit` | **Pre-Commit Verification** | 4-Phase pre-commit pipeline executing secret scans, static audits, test validation, and Conventional Commits formatting. |
| **`/benchmark`** | `skills/benchmark` | **Performance & Hotspots** | 4-Phase microbenchmark & profiling harness (Ecosystem detection, Hotspots $O(n^2)$, Memory leaks, >5% regression threshold). |
| **`/refactor`** | `skills/refactor` | **Tech Debt Remediation** | Safe refactoring & KISS simplification with baseline verification, preserving 100% green tests and public APIs. |
| **`/visual-qa`** | `skills/visual-qa` | **Multimodal UI Inspector** | Dual-viewport Playwright screenshots (**Desktop 1280x800 + Mobile 375x667 iPhone SE**). |
| **`/security-audit`** | `skills/security-audit` | **Vulnerability Harness** | Cloudflare 4-phase audit (Recon, Coverage Sweeps, Hunter/Verifier, Supply Chain CVEs, `findings.json` & `SECURITY-REPORT.md`). |

---

## 🔄 Autonomous Closed-Loop Verification Pipeline (`/opus-dev`)

```mermaid
flowchart TD
    P1["1. Design & KISS/YAGNI Gate (/brainstorm)"] --> P2["2. Milestone & Atomic Planning (/plan)"]
    P2 --> P3["3. Strict TDD (RED: Failing Tests → GREEN: Minimal Code)"]
    P3 --> P4["4. Closed-Loop Auto-Debug (/auto-debug)"]
    P4 --> P5["5. Adversarial Audit & Visual QA (claude-critic / visual-qa)"]
    P5 --> CheckPass{"Audit Status"}
    CheckPass -- "RETRY (Defects Found)" --> SurgicalFix["Apply Minimal Surgical Fixes"]
    SurgicalFix --> P3
    CheckPass -- "PASS (0 Defects)" --> Done["✅ Verified Production Delivery"]
```

---

## 🤖 Specialized Subagent Personas

| Subagent | Persona File | Role & Expertise |
| :--- | :--- | :--- |
| **`opus-architect`** | `agents/opus-architect.md` | System design, design pattern selection, complexity analysis ($O(n)$), KISS/YAGNI anti-overengineering gate, and API stability. |
| **`claude-critic`** | `agents/claude-critic.md` | Strict 7-pillar adversarial inspector for negative constraints, KISS/YAGNI compliance, concurrency, edge cases, and OWASP Top 10 vulnerabilities. |
| **`visual-qa-critic`**| `agents/visual-qa-critic.md`| Multimodal UI/UX and accessibility critic inspecting mobile horizontal overflow, tap targets (≥44px), and console errors. |

---

## 🌐 100% Cross-Platform Native Architecture

- **🍎 macOS (Apple Silicon & Intel)**: Adaptive Chromium launcher with process isolation for sandboxed execution and rapid non-blocking dual-stack socket probing.
- **🐧 Linux (Debian, Ubuntu, RHEL, Fedora, Arch, Alpine)**: Memory-isolated headless browser runner with non-blocking fallback-safe execution.
- **🪟 Windows 10/11 (PowerShell 5.1 & 7+)**: 1-click installation via native NTFS Directory Junctions (`New-Item -ItemType Junction`) and BOM-less UTF-8 configuration writing.

---

## 📁 Directory Structure

```text
antigravity-dev-suite/
├── plugin.json                 # Standard AGY plugin manifest (v1.12.0)
├── hooks.json                  # Root PreToolUse & PostToolUse hook configuration
├── mcp_config.json             # Root Playwright MCP server definition
├── agents/                     # Subagent personas (Native Markdown)
│   ├── opus-architect.md       # System design, ADR persistence & scalability architect
│   ├── claude-critic.md        # Adversarial logic, migration & constraints critic (Opus 5.5 Standard)
│   └── visual-qa-critic.md     # Multimodal visual QA critic (Dual-Viewport)
├── rules/                      # System rules injected into context
│   └── AGENTS.md               # Master Claude Opus 5.5 Enterprise Rulebook (14 Architectural Rules)
├── skills/                     # Skill modules & First-Class Slash Commands
│   ├── opus-dev/SKILL.md       # /opus-dev: Unified autonomous engineering meta-engine
│   ├── brainstorm/SKILL.md     # /brainstorm: Architectural trade-off analysis & ADR persistence
│   ├── plan/SKILL.md           # /plan: Atomic milestone & TDD planning
│   ├── auto-debug/SKILL.md     # /auto-debug: Multi-ecosystem closed-loop auto-debugger (Tests, Types, Race, Fuzz)
│   ├── code-review/            # /code-review: 5-Pass adversarial security, invariants & typing gate
│   │   ├── SKILL.md            # Multi-pass code review workflow
│   │   └── references/         # Modular pattern reference catalog
│   │       └── patterns.md     # Typestate, Branded Types, Structured Concurrency & Property Testing
│   ├── commit/SKILL.md         # /commit: Pre-commit verification pipeline & Conventional Commits
│   ├── benchmark/SKILL.md      # /benchmark: Microbenchmark & latency profiling harness
│   ├── refactor/SKILL.md       # /refactor: Safe tech debt remediation with invariants
│   ├── visual-qa/SKILL.md      # /visual-qa: Dual-viewport Playwright visual QA skill
│   └── security-audit/         # /security-audit: Cloudflare-inspired vulnerability harness
│       ├── SKILL.md            # 4-phase recon, sweep, falsification, and reporting workflow
│       └── references/         # Modular vulnerability threat profiles & audit vectors
│           ├── web-and-auth.md # Web, API, BOLA/IDOR, and authentication vulnerabilities
│           ├── ai-and-llm.md   # Prompt injection, tool isolation, and context poisoning
│           ├── memory-and-injection.md # SQLi, command injection, path traversal, memory bugs
│           └── supply-chain.md # Dependency auditing, lockfile integrity, typosquatting
├── scripts/                    # Runtime runner scripts (Pure Python / Cross-Platform)
│   ├── validator_core.py       # Core AST, regex, JSONC, polyglot raw strings, and delimiter parser
│   ├── auto_debug_runner.py    # Universal PostToolUse hook processor, tests, typecheck, race & fuzz runner
│   ├── auto_debug_runner.sh    # Resilient Unix wrapper for auto-debug hook execution
│   ├── install_git_hooks.py    # Native cross-platform pre-commit Git hook installer
│   ├── pre_tool_guard.py       # PreToolUse safety guardrail (Blocks catastrophic commands & leaks)
│   ├── critic_loop.py          # Critic loop orchestrator CLI (Opus 5.5 Standard)
│   ├── visual_qa.py            # Playwright dual-viewport screenshot engine (Platform-adaptive)
│   ├── run_audit_loop.sh       # Multi-pass autonomous audit loop runner (Unix)
│   ├── run_audit_loop.ps1      # Multi-pass autonomous audit loop runner (PowerShell)
│   ├── clean_legacy_plugins.sh # Conflicting plugins cleaner (macOS & Linux)
│   └── clean_legacy_plugins.ps1# Conflicting plugins cleaner (Windows PowerShell)
├── tests/                      # Automated Verification & TDD Suite
│   └── test_plugin_suite.py    # Full unit and integration test suite (110 automated checks)
├── templates/                  # Zero-setup per-repository template
│   └── project-git-template/   # .agents/ & GEMINI.md template for team sharing
├── install.sh                  # 1-Click installer for macOS & Linux
├── install.ps1                 # 1-Click installer for Windows (PowerShell)
├── uninstall.sh                # Clean uninstaller for macOS & Linux
└── uninstall.ps1               # Clean uninstaller for Windows (PowerShell)
```

---

## 📦 1-Click Installation

### 🍎 macOS & 🐧 Linux
```bash
cd antigravity-dev-suite
chmod +x install.sh
./install.sh

# Optional: Install Playwright Chromium browser binaries (~150MB)
./install.sh --with-browsers
# or set AGY_INSTALL_BROWSERS=1 ./install.sh
```

### 🪟 Windows (PowerShell 5.1 / 7+)
```powershell
cd antigravity-dev-suite
.\install.ps1

# Optional: Install Playwright Chromium browser binaries
.\install.ps1 -WithBrowsers
```

---

## ⚡ CLI Utilities & Diagnostic Tools

Every component includes standalone CLI execution for terminal inspection:

### 1. Auto-Debug Runner (`auto_debug_runner.py`)
```bash
# Auto-detect ecosystem and test/lint commands (10+ ecosystems)
python3 scripts/auto_debug_runner.py --detect

# Run detected test suite autonomously
python3 scripts/auto_debug_runner.py --run-tests

# Run detected microbenchmarks autonomously
python3 scripts/auto_debug_runner.py --benchmark

# Validate single file syntax and bracket balance
python3 scripts/auto_debug_runner.py --check <path/to/file>

# Read cached syntax error from recent hook execution
python3 scripts/auto_debug_runner.py --last-error

# Clear cached syntax error
python3 scripts/auto_debug_runner.py --clear-last-error
```

### 2. Critic Loop Orchestrator (`critic_loop.py`)
```bash
# Run full static audit across target directory
python3 scripts/critic_loop.py --mode all --target .

# Run semantic AST audit (mutable defaults, ReDoS, unawaited promises)
python3 scripts/critic_loop.py --mode semantic --target .

# Run syntax and bracket validation only
python3 scripts/critic_loop.py --mode syntax --target src/

# Run OWASP Top 10 secrets and empty exception scans only
python3 scripts/critic_loop.py --mode security --target .

# Inspect synthetic self-test mode
python3 scripts/critic_loop.py --mode all --test-mode
```

### 3. Visual QA Runner (`visual_qa.py`)
```bash
# Capture dual-viewport screenshots against detected or default dev server
python3 scripts/visual_qa.py

# Target specific dev server URL or port
python3 scripts/visual_qa.py --dev-server http://localhost:5173
python3 scripts/visual_qa.py --port 3000
```

### 4. Autonomous Multi-Pass Audit Loops
```bash
# Unix (macOS / Linux)
./scripts/run_audit_loop.sh -n 3 -m all -w .

# Windows (PowerShell)
.\scripts\run_audit_loop.ps1 -MaxCycles 3 -Mode all -WorkspacePath .
```

---

## 👥 Zero-Setup Team Sharing (Per-Repository)

To enable these rules, skills, and subagents for all team members on a specific repository:

1. Copy the template into your project root:
   ```bash
   cp -r templates/project-git-template/* /path/to/your/project/
   ```
2. Commit and push:
   ```bash
   git add GEMINI.md .agents/
   git commit -m "chore: enable Antigravity Dev Suite & Claude Opus 5.5 skills"
   git push
   ```

---

## 🛠️ Testing & Verification Suite

Execute the built-in automated test suite:

```bash
# Run Complete Test Suite
python3 tests/test_plugin_suite.py

# Test Visual QA Screenshot Engine directly
python3 scripts/visual_qa.py --test-mode

# Test Critic Loop Orchestrator
python3 scripts/critic_loop.py --mode all --test-mode
```

---

## 📄 License
Internal Enterprise License — UniCredit Group.
