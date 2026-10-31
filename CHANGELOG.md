# 📝 Changelog — Antigravity Dev Suite

All notable changes to this project are documented in this file.

---

## [1.7.1] — 2026-10-31

### 🛠️ Bug Fixes & Improvements
- **JS/TS Nested Template Literal Tracking**: Fixed state machine in `validator_core.py` to correctly handle nested template literals, bracket delimiters in expressions, and string quotes inside `${ ... }`.
- **HTML Document Tag Closure Validation**: Integrated `DefensiveHTMLValidator` to check matching opening and closing HTML tags while respecting HTML5 void elements.
- **Windows Python Interpreter Priority**: Updated `hooks.json` to prioritize `py -3` before `python3` to avoid Microsoft Store redirection dialogs on Windows.
- **Subagent Definition Verification**: Added automated tests verifying YAML frontmatter integrity across all subagent markdown files.

---

## [1.7.0] — 2026-10-31

### 🚀 Highlights
- **Codified Autonomous Closed-Loop Engineering**: Mandated iterative verification loop (`TDD → Auto-Debug → Adversarial Critic Audit → Surgical Fix → Re-Audit`) until achieving a clean `PASS` verdict (0 violations).
- **Rust & C++ Raw String & Lifetime Support**: Enhanced `validator_core.py` with full support for Rust raw strings (`r#"..."#`, `r"..."`, `br#"..."#`), Rust generic lifetimes (`<'a, 'b>`, `where 'a: 'b`), and C++ raw string literals (`R"(...)"`, `R"delim(...)delim"`).
- **JS/TS Division vs Regex Disambiguation**: Implemented lookback token parser to distinguish division operations (`10 / 2`, `(a+b) / 2`, `arr[0] / 2`) from regular expression literals.
- **JSONC Trailing Comma & Comment Parser**: Preserves comma tokens inside string literals while stripping trailing object/array commas.
- **Dual-Stack Socket Probing**: Support for IPv4 (`127.0.0.1`) and IPv6 (`::1`) dev server probes in Visual QA runner.
- **Deterministic Resource Management**: Wrapped Playwright browser lifecycle in `try...finally: browser.close()`.
- **PowerShell BOM-Less UTF-8**: Ensured `uninstall.ps1` and `install.ps1` emit strict BOM-less UTF-8 configurations across PowerShell 5.1 and 7+.

### 🧪 Test Coverage
- Expanded `tests/test_plugin_suite.py` to 18 automated integration test suites with 100% pass rate.
