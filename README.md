# 🚀 Antigravity Dev Suite (AGY Native Standard v1.2.0)

**Enterprise-grade, 100% Cross-Platform Development Suite for Google Antigravity (AGY)**.
Brings Claude Code-style **Autonomous Auto-Debug**, **Dual-Viewport Playwright Visual QA (Desktop 1280px + Mobile 375px)**, **Zero-Preamble Discipline**, and **Adversarial Critic Subagents** natively into Antigravity across **macOS, Linux, and Windows 10/11**.

---

## 🌟 Key Capabilities & Native Architecture

1. **Native AGY Plugin Standard**: Fully compliant with the Antigravity Plugin specification:
   - Root `hooks.json` & `mcp_config.json` automatic discovery.
   - Native Markdown Subagents (`agents/*.md`).
   - Native System Rules (`rules/AGENTS.md`).
   - Dedicated Progressive Disclosure Skills (`skills/auto-debug/`, `skills/visual-qa/`).
2. **100% Cross-Platform Native Support**:
   - **macOS (Apple Silicon & Intel)**: Mach Port rendezvous-safe headless Chromium runner with single-process optimization.
   - **Linux (Ubuntu, Debian, RHEL, Fedora, Arch, Alpine)**: Memory-isolated headless browser engine with fallback-safe dependency resolution.
   - **Windows 10/11**: Native PowerShell 1-click installation via NTFS Directory Junctions (`mklink /J`) without requiring administrator privileges or Developer Mode.
3. **Autonomous Auto-Debug & Self-Healing Hook**:
   - Listens to `PostToolUse` events on `write_file` and `edit_file`.
   - Universally dispatches via Python (`python3 scripts/auto_debug_runner.py || python scripts/auto_debug_runner.py`).
   - Reads `stdin` JSON payloads safely and guarantees non-blocking `{}` responses on `stdout`.
4. **Dual-Viewport Playwright Visual QA**:
   - Automatically detects active dev servers on common local ports (`5173`, `3000`, `8080`, `4200`, `8000`, etc.) or static HTML/component entry points.
   - Captures and asserts full-page screenshots at:
     - **Desktop Viewport**: 1280x800 (Full-page layout, grid/flex structure)
     - **Mobile Viewport**: 375x667 (iPhone SE standard — touch targets, text wrapping, zero horizontal scroll overflow)
5. **Claude-Style Discipline & Verification Mandate**:
   - Zero polite conversational filler; immediate structured technical execution.
   - Negative constraint evaluation and strict TDD (Red-Green-Improve).
   - Strict evidence verification before assertions.
6. **Adversarial Subagent Critics**:
   - `claude-critic`: Adversarial inspection of negative constraints, edge cases, concurrency, and security.
   - `visual-qa-critic`: Multimodal UI/UX review of layout clipping, contrast, tap targets, and responsive overflow.

---

## 📁 Directory Structure

```text
antigravity-dev-suite/
├── plugin.json                 # Standard AGY plugin manifest (v1.2.0)
├── hooks.json                  # Root PostToolUse hook configuration (Cross-platform)
├── mcp_config.json             # Root Playwright MCP server definition
├── agents/                     # Subagent personas (Native Markdown)
│   ├── claude-critic.md        # Adversarial logic & constraints critic
│   └── visual-qa-critic.md     # Multimodal visual QA critic
├── rules/                      # System rules injected into context
│   ├── AGENTS.md               # Master rules file
│   ├── claude_discipline.md    # Standalone Claude discipline directives
│   └── visual_qa_mandate.md    # Standalone Visual QA directives
├── skills/                     # Skill modules for autonomous workflows
│   ├── auto-debug/SKILL.md     # Auto-debug workflow skill
│   └── visual-qa/SKILL.md      # Visual QA inspection skill
├── scripts/                    # Runtime runner scripts (Pure Python / Cross-Platform)
│   ├── auto_debug_runner.py    # Universal PostToolUse hook processor
│   ├── auto_debug_runner.sh    # Legacy bash hook runner (POSIX fallback)
│   ├── critic_loop.py          # Critic loop orchestrator CLI
│   ├── clean_legacy_plugins.sh # Conflicting plugins cleaner
│   └── visual_qa.py            # Playwright dual-viewport screenshot engine
├── templates/                  # Zero-setup per-repository template
│   └── project-git-template/   # .agents/ & GEMINI.md template for team sharing
├── install.sh                  # 1-Click installer for macOS & Linux
├── install.ps1                 # 1-Click installer for Windows (PowerShell)
├── uninstall.sh                # Clean uninstaller for macOS & Linux
└── uninstall.ps1               # Clean uninstaller for Windows (PowerShell)
```

---

## 📦 1-Click Installation (For You and Your Team)

### 🍎 macOS & 🐧 Linux
```bash
# Clone or navigate to the directory
cd antigravity-dev-suite
chmod +x install.sh
./install.sh
```

### 🪟 Windows (PowerShell 5.1 / 7+)
```powershell
# Open PowerShell and run:
cd antigravity-dev-suite
.\install.ps1
```

---

## 👥 Zero-Setup Team Sharing (Per-Repository)

To enable these rules and subagents for all team members on a specific repository without requiring global plugin installation on every machine:

1. Copy the contents of `templates/project-git-template/` into your project root:
   ```bash
   cp -r templates/project-git-template/* /path/to/your/project/
   ```
2. Commit and push:
   ```bash
   git add GEMINI.md .agents/
   git commit -m "chore: enable Antigravity Dev Suite & Visual QA rules"
   git push
   ```

---

## 🛠️ Testing & Verification

Execute the built-in self-test verification commands:

```bash
# Test Visual QA Screenshot Engine
python3 scripts/visual_qa.py --test-mode

# Test Critic Loop Orchestrator
python3 scripts/critic_loop.py --mode visual --test-mode

# Test Cross-Platform Hook Runner
echo '{"toolCall": {"name": "write_file", "args": {"Path": "/tmp/test.html"}}}' | python3 scripts/auto_debug_runner.py
```

---

## 🔄 Uninstallation & Rollback

### macOS & Linux
```bash
./uninstall.sh
```

### Windows (PowerShell)
```powershell
.\uninstall.ps1
```

---

## 📄 License
Internal Enterprise License — UniCredit Group.
