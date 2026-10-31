# 🚀 Antigravity Dev Suite (Hybrid A + B + C Engine)

Enterprise-grade development suite for **Google Antigravity & Gemini**, bringing Claude Code-style **Auto-Debug**, **Playwright Visual QA (Desktop + Mobile 375px)**, **Zero-Preamble Discipline**, and **Autonomous Critic Loops** to every project.

---

## 🌟 Key Capabilities

1. **Autonomous Auto-Debug & Self-Healing**: Automatically runs project unit/integration tests (`npm`, `pytest`, `cargo`, `mvn`) upon file edits, parses failures, and auto-corrects code before completing tasks.
2. **Dual-Viewport Playwright Visual QA**: Automatically detects active local dev servers (ports `5173`, `3000`, `8080`, `4200`) and captures full-page screenshots at:
   - **Desktop**: 1280x800
   - **Mobile**: 375x667 (iPhone SE standard)
3. **Claude-Style Discipline & Verification Mandate**: Zero polite filler, strict pre-execution Chain-of-Thought (CoT) critique, strict TDD (Red-Green-Refactor), and evidence before assertions.
4. **Autonomous Critic Subagents**:
   - `claude-critic`: Adversarial validation against negative constraints, edge cases, and safety.
   - `visual-qa-critic`: Multimodal UI/UX review of layout clipping, contrast, and responsiveness.
5. **Conflict-Free Architecture**: Automatically disables conflicting or redundant plugins (such as `ponytail` or legacy plugins) to guarantee maximum prompt efficiency and zero context dilution.

---

## 📦 1-Click Installation (For You and Your Team)

### Option 1: Quick Install via Git
```bash
git clone https://ghb.internal.unicreditgroup.eu/scm/~c332376/antigravity-dev-suite.git ~/.gemini/config/plugins/antigravity-dev-suite
cd ~/.gemini/config/plugins/antigravity-dev-suite
./install.sh
```

### Option 2: Local Installation from this Repo
```bash
cd /Users/FABIO.STOCCO/Progetti/tool/antigravity-dev-suite
./install.sh
```

---

## 👥 Zero-Setup Team Sharing (Per-Repository)

To enable these rules for all colleagues on a specific repository without requiring them to install global plugins:

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

To cleanly remove the suite and restore standard Antigravity settings:
```bash
./uninstall.sh
```

---

## 📄 License
Internal Enterprise License — UniCredit Group.
