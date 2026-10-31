# 📝 Changelog — Antigravity Dev Suite

All notable changes to this project are documented in this file.

---

## [1.8.9] — 2026-10-31

### 🚀 Highlights & Critical Fixes Remediated
- **Comprehensive Project Framework Detection**: Added multi-ecosystem test and typecheck runner detection to `scripts/auto_debug_runner.py` supporting Python (`pytest`, `uv`, `poetry`), Node/TS (`Vitest`, `Jest`, `Bun`, `Deno`, `pnpm`), Rust (`Cargo`), Go, Java/Kotlin (`Maven`, `Gradle`), .NET/C#, C/C++ (`CMake`/`CTest`), Ruby (`RSpec`), PHP (`PHPUnit`), and Swift (`SwiftPM`).
- **PostToolUse Hook Error Cache & Bridge**: Integrated persistent diagnostic caching (`get_last_syntax_error()` / `clear_last_syntax_error()`) between post-tool-use hooks and the critic loop, bridging the Antigravity hook stdout contract (`{}`).
- **Auto-Debug Runner CLI Flags**: Added `--detect`, `--run-tests`, `--check`, `--last-error`, and `--clear-last-error` CLI options for autonomous test execution and diagnostics.
- **Visual QA Multi-Service Port Selection**: Added `--dev-server <URL>` and `--port <PORT>` CLI flags and preferred port matching in `scripts/visual_qa.py` to prevent incorrect port binding in microservice architectures.
- **Safe Installation & Opt-In Browser Binaries**: Hardened `install.sh` pip fallback hierarchy (safe `--user` before `--break-system-packages`) and made Playwright Chromium browser binary downloads opt-in via `--with-browsers` / `AGY_INSTALL_BROWSERS=1`.
- **Pre-Flight Static Audit Integration**: Integrated `critic_loop.py` deterministic audit into `code-review` and `opus-dev` skill workflows before subagent review.
- **Expanded Test Suite**: Expanded `tests/test_plugin_suite.py` to 100 passing test cases with 100% green verification.

---

## [1.8.8] — 2026-10-31

### 🚀 Highlights & Critical Fixes Remediated
- **Shell Runner Script Stability**: Fixed `set -u` unbound variable error in `auto_debug_runner.sh` when invoked with no arguments (`"$@"`), and eliminated duplicate `{}` stdout outputs caused by redundant shell trap.
- **Astro Frontmatter TS Generics**: Added frontmatter (`--- ... ---`) masking in `validator_core.py` for `.astro` components, preventing TypeScript generic parameters (`Array<string>`, `Map<K, V>`) from triggering false unclosed HTML tag errors.
- **PHP & Ruby Heredocs/Nowdocs**: Implemented syntax-aware heredoc tokenizers for PHP (`<<<EOF ... EOF;`, `<<<'NOWDOC' ... NOWDOC;`) and Ruby (`<<~SQL ... SQL`, `<<-EOF ... EOF`), preventing prose text and quotes inside heredocs from causing false delimiter/string errors.
- **Java 15+ Multiline Text Blocks**: Added `.java` support for triple-quoted string literals (`"""..."""`) in `validator_core.py`.
- **JSON5 Standalone Tokenizer Normalization**: Single-quoted strings are now converted before unquoted property conversion in JSON5 fallback mode, preventing strings with colons from getting corrupted.
- **YAML Multiline Block Scalars**: Added block scalar literal (`|`) and folded (`>`) indentation tracking to the YAML fallback validator, preventing bracket balancing errors on prose text.
- **CommonMark Multi-Backtick Fences**: Enforced CommonMark compliance in Markdown validator, verifying closing fence length and structure.
- **Cloud & Blockchain Polyglot Validation**: Added `.prisma`, `.sol` (Solidity), and `.tf`/`.hcl` (Terraform) validation with appropriate comment and delimiter parsing.
- **OWASP Hardcoded Secrets & Empty Exception Audit**: Added static AST and regex scans in `critic_loop.py` for API keys, tokens, private keys, and empty exception handling blocks across the codebase.
- **Visual QA Expanded Ports & HTTP Status Tracking**: Expanded `COMMON_DEV_PORTS` in `visual_qa.py` with modern dev ports (`4173`, `8888`, `3004`, `3005`, `5177-5179`) and added HTTP $\ge 400$ response logging.
- **Defensive Config Updates**: Added safe dict type validation across `install.sh`, `install.ps1`, `uninstall.sh`, and `uninstall.ps1`.
- **Autonomous Audit Verification**: Passed 100% automated test suite with 83 test cases and 0 remaining defects on `critic_loop.py --mode all`.

---

## [1.8.7] — 2026-10-31

### 🚀 Highlights & Critical Fixes Remediated
- **Polyglot & Multi-Format Validation**: Added validation support in `validator_core.py` for XML, SVG, Plist, XAML, Vue SFC, Svelte SFC, Astro, PowerShell (`.ps1`, `.psm1`, `.psd1`), Jupyter Notebooks (`.ipynb` with Python cell AST & IPython magic handling), GraphQL (`.graphql`, `.gql`), Protobuf (`.proto`), INI (`.ini`, `.cfg`), and environment configurations (`.env`, `.properties`).
- **Extended Language Comments & Delimiters**: Implemented Ruby `=begin`/`=end` block comments, Julia `#=`/`=#` comments, Nim `#[`/`]#` comments, Clojure `;`, Elixir `#`, Erlang `%` comments, and PowerShell `<# #>` block comments and `@'...'@`/`@"..."@` here-strings.
- **URI Prefix Normalization**: Added `file://` URI prefix stripping and Windows drive letter resolution to `extract_target_file()` and `resolve_target_file()`.
- **Advanced JSON5 Normalizations**: Added `NaN` / `Infinity` and multiline escape (`\\n`) normalizations to the JSON5 fallback parser.
- **Enhanced Critic Loop Orchestrator**: Added support for comma-separated targets and glob expression expansion (`*.py`, `src/**/*.ts`) in `critic_loop.py`.
- **Expanded Mobile Touch Target Checks & Astro Component Recognition**: Expanded `visual_qa.py` to inspect `<select>`, `<textarea>`, `<input>`, and ARIA interactive elements for touch target compliance (<44px), plus `.astro` component routing.
- **Enhanced Autonomous Audit Loop CLI**: Added `-n`, `-d`, `-p`, `-m`, `-w`, `-l` argument flags to `run_audit_loop.sh` and `run_audit_loop.ps1`.
- **Comprehensive Test Suite Expansion**: Added 11 new automated test suites in `tests/test_plugin_suite.py` (73 total checks) with 100% pass rate.

---

## [1.8.6] — 2026-10-31

### 🚀 Highlights & Critical Fixes Remediated
- **Dynamic Multi-Workspace PostToolUse Hook Dispatch**: Re-architected `hooks.json` command dispatcher using `runpy.run_path` across standard installation locations (`~/.gemini/config/plugins/...`, `%USERPROFILE%`, and cwd), eliminating `[Errno 2] No such file or directory` failures when editing files in external project workspaces.
- **Enhanced JSON5 Standalone Fallback Parser**: Fixed single-quote escape normalization (`\'` unescaped for valid RFC 8259 JSON) and added support for signed hexadecimal numbers (`-0x10`, `+0x10`) and signed decimals (`-.5`, `+.75`, `42.`) in fallback parser.
- **MySQL Hash Comments, Backtick Identifiers & SQL Brackets**: Added support for MySQL `#` line comments, backtick identifiers (`` `identifier` ``), ANSI double-quoted identifiers, and curly bracket (`{}`) balancing in `validator_core.py` SQL validator.
- **Python AST Syntax Error Diagnostic Safety**: Wrapped AST error formatting in `validator_core.py` with fallback defaults for `e.lineno` and `e.offset` when compiler reports `None`.
- **Extended Test Suite**: Added 3 new comprehensive test suites in `tests/test_plugin_suite.py` (62 total automated checks) with 100% pass rate.

---

## [1.8.5] — 2026-10-31

### 🚀 Highlights & Critical Fixes Remediated
- **True JSON5 Multi-Tier Parser**: Implemented multi-tier JSON5 validation in `validator_core.py` (native `json5`/`pyjson5` when installed, plus dependency-free AST comment/regex normalizer converting unquoted identifiers, single-quoted strings, hex numbers, and trailing commas into RFC 8259 JSON).
- **C# 11 Multiline Raw Strings & Verbatim Strings**: Added C# 11 raw string literals (`"""..."""` / `""""...""""`) and verbatim string prefixes (`$@"`, `@$"`) with curly brace interpolation parsing.
- **Dart Raw & Multiline String Literals**: Integrated Dart raw strings (`r"..."`, `r'...'`, `r"""..."""`, `r'''...'''`) and multiline strings (`"""`, `'''`) with escape parsing.
- **Dependency-Free YAML Plain Apostrophes**: Enhanced YAML fallback scanner to distinguish unquoted apostrophes (`It's`, `don't`) from single-quoted scalar boundaries, handling escaped single quotes (`''`).
- **Dependency-Free TOML Multiline Strings**: Upgraded TOML fallback parser to track multiline basic (`"""..."""`) and literal (`'''...'''`) strings across line breaks while validating bracket parity.
- **Shell Heredoc vs Arithmetic Bitshifts**: Corrected heredoc regex delimiter matching to `(?<!<)<<-?\s*['"]?([a-zA-Z_][a-zA-Z0-9_]*)['"]?`, eliminating false positives on arithmetic bitshifts (`$(( 1 << 4 ))`).
- **Critic Loop URL & Target Normalization**: Enhanced `scripts/critic_loop.py` to disambiguate web targets (`http://`, `https://`, `localhost`) from filesystem targets, defaulting workspace audits to current working directory.
- **Enhanced Mobile Visual QA**: Upgraded `scripts/visual_qa.py` viewport evaluation to `Math.max(document.body.scrollWidth, document.documentElement.scrollWidth)` and integrated touch target size inspection for interactive controls `< 44x44px`.
- **Installer & Environment Resilience**: Expanded `install.sh` `chmod +x` scope to include root shell scripts and updated `install.ps1` to execute `$CleanerScript` directly for PowerShell 7 (`pwsh`) cross-platform compatibility.
- **Extended Test Suite**: Added 6 new test suites in `tests/test_plugin_suite.py` (59 total automated checks) with 100% pass rate.

---

## [1.8.4] — 2026-10-31

### 🚀 Highlights & Critical Fixes Remediated
- **Polyglot Language Parser Support**: Expanded `validator_core.py` syntax and delimiter validation to C# (`.cs`), Kotlin (`.kt`, `.kts`), Swift (`.swift`), Dart (`.dart`), Scala (`.scala`), PHP (`.php`), Ruby (`.rb`), Lua (`.lua`), and modern C++ headers/sources (`.hpp`, `.hxx`, `.hh`, `.cc`, `.cxx`).
- **Advanced Multi-Language Comment & String Tokenizer**:
  - Implemented C# verbatim string literals (`@"..."`) with doubled-quote escaping (`""`).
  - Added Kotlin and Swift triple-quoted multiline strings (`"""..."""`).
  - Added Swift recursive nested block comments (`/* /* nested */ */`).
  - Added Lua multiline comments (`--[[...]]`) and multiline bracket strings (`[[...]]`).
  - Added Ruby and PHP hash comments (`#`).
- **Universal Tool Payload Resolution**: Enhanced `extract_target_file()` and `resolve_target_file()` to parse and normalize diverse LLM tool schemas (`toolUse.input`, `tool_input`, `parameters`, `params`, `arguments`, `cwd`, `workspacePath`).
- **Filesystem Scan Noise Reduction**: Added `.pytest_cache`, `.hypothesis`, `coverage`, `.nyc_output`, `vendor`, `.gemini`, and `.agents` to `IGNORED_DIRS`.
- **Extended Dev Server Port Discovery**: Expanded `COMMON_DEV_PORTS` in `visual_qa.py` with modern frontend/backend development ports (`5174-5176`, `3002-3003`, `8001-8002`).
- **Comprehensive Integration Test Matrix**: Added 7 new test suites in `tests/test_plugin_suite.py` (53 total suites) with 100% pass rate.

---

## [1.8.3] — 2026-10-31

### 🚀 Highlights & Critical Fixes Remediated
- **Shell Parser Robustness & Case/Heredoc Support**: Upgraded `validator_core.py` shell parser with combined native dry-run syntax checks (`bash -n` / `sh -n`) and resilient delimiter scanning that supports heredoc content (`<<'EOF'`) and shell `case ... in pattern) ... esac` blocks without false-positive bracket mismatch errors.
- **PostgreSQL Dollar-Quoted Strings & SQL Escapes**: Integrated token scanner in `validator_core.py` supporting PostgreSQL dollar-quoted literals (`$$...$$`, `$tag$...$tag$`) and standard SQL quote escapes (`''`).
- **Python Type Stubs & JSON5 Support**: Added `.pyi` and `.json5` file format parsing and validation to `validator_core.py`.
- **YAML Escape Parsing**: Fixed backslash-escaped quote tracking (`\"`, `\'`) in the dependency-free YAML fallback parser.
- **Unclosed JS/TS Regex Literal Detection**: Added EOF validation to catch unterminated regular expression literals in JavaScript and TypeScript files.
- **Visual QA Fragment/Query Path Resolution**: Added URL fragment (`#anchor`) and query (`?param`) stripping before resolving local file targets in `visual_qa.py`.
- **Ecosystem Test Runner Matrix Expansion**: Expanded `skills/auto-debug/SKILL.md` test framework matrix with Bun (`bun test`), Deno (`deno test`), pnpm (`pnpm test`), Python uv (`uv run pytest`), ruff (`ruff check`), CMake/CTest (`ctest`), Ruby (`bundle exec rspec`), PHP (`vendor/bin/phpunit`), and Swift (`swift test`).
- **Target Path Tilde Resolution in Critic Loop**: Added `.expanduser()` resolution to `scripts/critic_loop.py` for user-relative path audits.
- **Expanded Test Suite**: Extended automated test suite in `tests/test_plugin_suite.py` to 46 test suites with 100% pass rate.

---

## [1.8.2] — 2026-10-31

### 🚀 Highlights & Critical Fixes Remediated
- **Dependency-Free TOML Fallback Parser**: Added resilient structural and bracket balancer fallback for TOML in `validator_core.py`, eliminating false-positive `TOMLDecodeError` when `tomllib` and `tomli` are not installed (e.g. standard Python 3.10 environments).
- **Universal Self-Closing Tag Handling in HTML/SVG**: Overrode `handle_startendtag` in `DefensiveHTMLValidator` to cleanly handle arbitrary self-closing elements (`<animate ... />`, `<custom-tag ... />`, `<feDropShadow ... />`) without triggering false tag nesting mismatches.
- **Extended JS/TS Regex Starter Tokens**: Expanded regex literal boundary detection in `validator_core.py` to support `else`, `do`, `in`, `instanceof`, and `of` keywords preceding regex expressions.
- **Tilde & Home Directory Path Expansion**: Added `expanduser()` to `resolve_target_file()` and `auto_debug_runner.py` for seamless handling of user-relative (`~/...`) tool call targets.
- **Resilient Playwright Navigation & Adaptive Sockets**: Enhanced `visual_qa.py` with `domcontentloaded` lifecycle handling and a 150ms socket probe timeout, preventing timeouts on heavy network assets while preserving non-blocking execution.
- **Extended Test Suite**: Added 4 new automated test suites in `tests/test_plugin_suite.py` (41 total suites) with 100% pass rate.

---

## [1.8.1] — 2026-10-31

### 🚀 Highlights & Gaps Remediated
- **Zero Hardcoded Developer Paths**: Replaced static user paths with dynamic script-relative resolution across Bash (`run_audit_loop.sh`) and PowerShell (`run_audit_loop.ps1`) audit loop runners.
- **Workspace-Relative Path Resolution**: Enhanced `auto_debug_runner.py` with `resolve_target_file()` to resolve relative file paths against `workspacePaths` in tool call payloads.
- **Multi-Document YAML Parsing**: Upgraded `DefensiveYAMLValidator` to parse multi-document YAML manifests using `yaml.safe_load_all()`.
- **Extended JS/TS Regex Starter Recognition**: Added support for spread operator (`...`) and member dot access (`.`) preceding regex literal delimiters in `validator_core.py`.
- **SVG Self-Closing Element Support**: Added SVG void/self-closing elements (`circle`, `path`, `rect`, `line`, `polygon`, `polyline`, `ellipse`, `use`, `stop`) to `DefensiveHTMLValidator`.
- **Mobile Horizontal Overflow & URL Normalization**: Added automated mobile viewport horizontal scroll overflow detection (`scrollWidth > innerWidth`), protocol-less URL normalization, and dev server probing in `visual_qa.py`.
- **Hook Matcher Consolidation**: Consolidated `write_file` and `edit_file` event dispatch in `hooks.json` using `"matcher": "write_file|edit_file"`.
- **Expanded Test Coverage**: Extended integration test suite in `tests/test_plugin_suite.py` to 37 test suites verifying all edge cases with 100% pass rate.

---

## [1.8.0] — 2026-10-31

### 🚀 Highlights & Gaps Remediated
- **Expanded Multi-Language Syntax Validation**: Integrated native syntax validators in `validator_core.py` for TOML (`pyproject.toml`, `Cargo.toml`), CSS/SCSS/LESS stylesheets, Shell scripts (`.sh`, `.bash`, `.zsh`), SQL scripts (`.sql`), YAML files, and Markdown documents.
- **Markdown Fenced Code Block & Frontmatter Verification**: Auto-detects unclosed triple-backticks / tildes and unclosed `---` YAML frontmatter blocks to prevent corrupted skill/agent loading.
- **Enhanced Syntax Error Line Pinpointing**: Bracket mismatch error messages now pinpoint the exact line where the opening delimiter was declared (`opened at line X`).
- **Dynamic Repository Root Resolution in Shell Scripts**: Removed hardcoded absolute user workspace paths from `scripts/run_audit_loop.sh` in favor of dynamic script-relative path resolution.
- **Unified Cross-Platform Hook Command Dispatch**: Updated `hooks.json` to prioritize `python3` before `py -3`, eliminating spurious `sh: py: command not found` stderr warnings on Unix while preserving full Windows compatibility.
- **Template Parity & Integrity Guard**: Synchronized all skills, rules, and subagents in `templates/project-git-template/.agents/` with root manifests and added automated bit-level parity tests.
- **Hardcoded Path Audit Guard**: Added automated tests guaranteeing zero hardcoded developer machine paths across scripts, manifests, and documentation.

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
