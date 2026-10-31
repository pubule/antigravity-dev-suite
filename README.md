# 🚀 Antigravity Dev Suite (Native AGY Plugin)

Enterprise-grade development suite for **Google Antigravity (AGY)**, bringing Claude Code-style **Autonomous Auto-Debug**, **Dual-Viewport Playwright Visual QA (Desktop + Mobile 375px)**, **Zero-Preamble Discipline**, and **Adversarial Critic Subagents** natively into Antigravity.

---

## 🌟 Key Capabilities & Native Architecture

1. **Native AGY Plugin Standard**: 100% compliant with Antigravity Plugin specification:
   - Root `hooks.json` & `mcp_config.json` discovery.
   - Native Markdown Subagents (`agents/*.md`).
   - Native System Rules (`rules/AGENTS.md`).
   - Dedicated Skills (`skills/auto-debug/`, `skills/visual-qa/`).
2. **Autonomous Auto-Debug & Self-Healing Hook**:
   - Listens to `PostToolUse` events on `write_file` and `edit_file`.
   - Parses tool payloads over `stdin` JSON, executes project unit/integration tests (`npm`, `pytest`, `cargo`, `mvn`, `go`), and outputs standard `{}` on `stdout`.
3. **Dual-Viewport Playwright Visual QA**:
   - Native Playwright MCP integration (`mcp_config.json`).
   - Automatically inspects local dev servers on standard ports (`5173`, `3000`, `8080`, `4200`, `8000`).
   - Captures and verifies full-page screenshots at:
     - **Desktop**: 1280x800
     - **Mobile**: 375x667 (iPhone SE standard)
4. **Claude-Style Discipline & Verification Mandate**:
   - Zero polite filler and immediate technical execution.
   - Negative constraint evaluation and strict TDD (Red-Green-Refactor).
   - Strict verification before assertions.
5. **Adversarial Subagent Critics**:
   - `claude-critic`: Adversarial inspection of negative constraints, edge cases, concurrency, and security.
   - `visual-qa-critic`: Multimodal UI/UX review of layout clipping, contrast, tap targets, and responsive overflow.

---

## 📁 Plugin Layout

```text
antigravity-dev-suite/
├── plugin.json                 # Standard AGY plugin metadata & prompts
├── hooks.json                  # Root PostToolUse hook configuration
├── mcp_config.json             # Root Playwright MCP server definition
├── agents/                     # Subagent personas (Native Markdown)
│   ├── claude-critic.md
│   └── visual-qa-critic.md
├── rules/                      # System rules injected into context
│   └── AGENTS.md
├── skills/                     # Skill modules for autonomous workflows
│   ├── auto-debug/SKILL.md
│   └── visual-qa/SKILL.md
├── scripts/                    # Runtime runner scripts
│   ├── auto_debug_runner.sh
│   └── visual_qa.py
├── templates/                  # Zero-setup per-repository template
│   └── project-git-template/
├── install.sh                  # Symlink & global setup script
└── uninstall.sh                # Clean uninstallation & rollback
```

---

## 📦 1-Click Installation (For You and Your Team)

### Option 1: Quick Install via Git
```bash
git clone https://ghb.internal.unicreditgroup.eu/scm/~c332376/antigravity-dev-suite.git ~/.gemini/config/plugins/antigravity-dev-suite
cd ~/.gemini/config/plugins/antigravity-dev-suite
./install.sh
```

### Option 2: Local Installation from Workspace
```bash
cd /Users/FABIO.STOCCO/Progetti/tool/antigravity-dev-suite
./install.sh
```

---

## 👥 Zero-Setup Team Sharing (Per-Repository)

To enable these rules and subagents for all colleagues on a specific repository without requiring global plugin installation:

1. Copy the contents of `templates/project-git-template/` into your project root:
   ```bash
   cp -r /Users/FABIO.STOCCO/Progetti/tool/antigravity-dev-suite/templates/project-git-template/* /path/to/your/project/
   ```
2. Commit and push:
   ```bash
   git add GEMINI.md .agents/
   git commit -m "chore: enable Antigravity Dev Suite & Visual QA rules"
   git push
   ```

---

## 🛠️ Testing & Verification

Run the built-in Playwright visual test to verify your environment:
```bash
python3 scripts/visual_qa.py --test-mode
```

---

## 🔄 Uninstallation & Rollback

To cleanly remove the suite:
```bash
./uninstall.sh
```

---

## 📄 License
Internal Enterprise License — UniCredit Group.
