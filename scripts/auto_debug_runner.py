#!/usr/bin/env python3
"""
Antigravity Auto-Debug Hook Runner & Framework Engine (Cross-Platform)
100% Portable across Windows 10/11, macOS (Intel & Apple Silicon), and Linux.
Performs fast, non-blocking syntax probes, framework detection, and test suite execution.
"""

import sys
import os
import json
import time
import tempfile
import subprocess
from pathlib import Path

# Add current scripts directory to sys.path for robust relative import
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from validator_core import validate_code_file, extract_target_file, resolve_target_file
except ImportError:
    import validator_core
    validate_code_file = validator_core.validate_code_file
    extract_target_file = validator_core.extract_target_file
    resolve_target_file = getattr(validator_core, "resolve_target_file", extract_target_file)

DIAGNOSTIC_FILE_NAME = "agy_last_syntax_error.json"

def get_diagnostic_file_path() -> Path:
    return Path(tempfile.gettempdir()) / DIAGNOSTIC_FILE_NAME

def get_last_syntax_error() -> dict | None:
    """Reads the last recorded syntax error from the temporary diagnostic cache."""
    diag_file = get_diagnostic_file_path()
    if diag_file.is_file():
        try:
            with open(diag_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
    return None

def clear_last_syntax_error() -> bool:
    """Clears the cached syntax error record."""
    diag_file = get_diagnostic_file_path()
    if diag_file.is_file():
        try:
            diag_file.unlink()
            return True
        except (OSError, PermissionError):
            return False
    return False

def detect_project_framework(workspace_dir: str | Path | None = None) -> dict:
    """
    Detects project test and linting framework from filesystem markers.
    Returns structured dictionary with ecosystem, test command, and lint command.
    """
    ws = Path(workspace_dir or Path.cwd()).resolve()

    # 1. Rust Cargo
    if (ws / "Cargo.toml").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "Rust (Cargo)",
            "test_command": "cargo test",
            "lint_command": "cargo clippy --all-targets",
            "markers": ["Cargo.toml"]
        }

    # 2. Go
    if (ws / "go.mod").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "Go",
            "test_command": "go test -v ./...",
            "lint_command": "go vet ./... && staticcheck ./...",
            "markers": ["go.mod"]
        }

    # 3. Python (uv, poetry, or pytest)
    if (ws / "uv.lock").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "Python (uv)",
            "test_command": "uv run pytest",
            "lint_command": "uv run ruff check . && uv run mypy .",
            "markers": ["uv.lock"]
        }
    if (ws / "poetry.lock").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "Python (poetry)",
            "test_command": "poetry run pytest",
            "lint_command": "poetry run mypy .",
            "markers": ["poetry.lock"]
        }
    py_markers = [m for m in ("pytest.ini", "pyproject.toml", "setup.cfg") if (ws / m).is_file()]
    if (ws / "tests").is_dir() or (ws / "test").is_dir():
        py_markers.append("tests/")
    if py_markers:
        return {
            "status": "DETECTED",
            "ecosystem": "Python (pytest)",
            "test_command": "pytest -v",
            "lint_command": "ruff check . && mypy .",
            "markers": py_markers
        }

    # 4. Node / TypeScript / JS
    has_pkg = (ws / "package.json").is_file()
    if (ws / "vitest.config.ts").is_file() or (ws / "vitest.config.js").is_file() or (ws / "vite.config.ts").is_file() or (ws / "vite.config.js").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "Node / TypeScript (Vitest)",
            "test_command": "npx vitest run",
            "lint_command": "npx tsc --noEmit && npx eslint .",
            "markers": ["vite.config.ts"] if (ws / "vite.config.ts").is_file() else ["vitest.config.ts"]
        }
    if (ws / "bun.lockb").is_file() or (ws / "bunfig.toml").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "Bun",
            "test_command": "bun test",
            "lint_command": "bunx tsc --noEmit && bunx eslint .",
            "markers": ["bun.lockb"] if (ws / "bun.lockb").is_file() else ["bunfig.toml"]
        }
    if (ws / "deno.json").is_file() or (ws / "deno.jsonc").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "Deno",
            "test_command": "deno test",
            "lint_command": "deno lint && deno check",
            "markers": ["deno.json"] if (ws / "deno.json").is_file() else ["deno.jsonc"]
        }
    if (ws / "pnpm-lock.yaml").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "Node (pnpm)",
            "test_command": "pnpm test",
            "lint_command": "pnpm run typecheck",
            "markers": ["pnpm-lock.yaml"]
        }
    if has_pkg:
        return {
            "status": "DETECTED",
            "ecosystem": "Node (npm)",
            "test_command": "npm test",
            "lint_command": "npx tsc --noEmit",
            "markers": ["package.json"]
        }

    # 5. .NET / C#
    cs_files = list(ws.glob("*.sln")) + list(ws.glob("*.csproj"))
    if cs_files:
        return {
            "status": "DETECTED",
            "ecosystem": ".NET / C#",
            "test_command": "dotnet test",
            "lint_command": "dotnet build",
            "markers": [cs_files[0].name]
        }

    # 6. Java / Kotlin
    if (ws / "pom.xml").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "Java (Maven)",
            "test_command": "mvn test",
            "lint_command": "mvn compile",
            "markers": ["pom.xml"]
        }
    if (ws / "build.gradle").is_file() or (ws / "build.gradle.kts").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "Java/Kotlin (Gradle)",
            "test_command": "./gradlew test",
            "lint_command": "./gradlew check",
            "markers": ["build.gradle"]
        }

    # 7. C / C++ (CMake)
    if (ws / "CMakeLists.txt").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "C / C++ (CMake)",
            "test_command": "ctest --output-on-failure",
            "lint_command": "cmake --build build",
            "markers": ["CMakeLists.txt"]
        }

    # 8. Ruby
    if (ws / "Gemfile").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "Ruby (Bundler)",
            "test_command": "bundle exec rspec",
            "lint_command": "bundle exec rubocop",
            "markers": ["Gemfile"]
        }

    # 9. PHP
    if (ws / "composer.json").is_file() or (ws / "phpunit.xml").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "PHP",
            "test_command": "vendor/bin/phpunit",
            "lint_command": "vendor/bin/phpstan analyse",
            "markers": ["composer.json"] if (ws / "composer.json").is_file() else ["phpunit.xml"]
        }

    # 10. Swift
    if (ws / "Package.swift").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "Swift",
            "test_command": "swift test",
            "lint_command": "swift build",
            "markers": ["Package.swift"]
        }

    return {
        "status": "UNKNOWN",
        "ecosystem": "Generic",
        "test_command": "npm test || pytest || cargo test || go test",
        "lint_command": "",
        "markers": []
    }

def run_project_tests(workspace_dir: str | Path | None = None, command_override: str = "") -> dict:
    """Executes detected or specified test command and captures output."""
    ws = Path(workspace_dir or Path.cwd()).resolve()
    cmd = command_override
    if not cmd:
        det = detect_project_framework(ws)
        cmd = det["test_command"]

    t0 = time.time()
    try:
        res = subprocess.run(
            cmd,
            shell=True,
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=120
        )
        duration = round(time.time() - t0, 3)
        return {
            "status": "PASS" if res.returncode == 0 else "FAIL",
            "command": cmd,
            "returncode": res.returncode,
            "duration_seconds": duration,
            "stdout": res.stdout,
            "stderr": res.stderr
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "TIMEOUT",
            "command": cmd,
            "returncode": -1,
            "duration_seconds": round(time.time() - t0, 3),
            "stdout": "",
            "stderr": f"Execution timed out after 120s: {cmd}"
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "command": cmd,
            "returncode": -1,
            "duration_seconds": round(time.time() - t0, 3),
            "stdout": "",
            "stderr": str(e)
        }

def handle_cli_mode() -> bool:
    """Handles explicit CLI command flags. Returns True if CLI command was processed."""
    args = sys.argv[1:]
    if not args:
        return False

    first = args[0]
    if first in ("--detect", "-d"):
        ws = args[1] if len(args) > 1 else None
        info = detect_project_framework(ws)
        print(json.dumps(info, indent=2))
        return True

    if first == "--last-error":
        err = get_last_syntax_error()
        print(json.dumps(err or {}, indent=2))
        return True

    if first == "--clear-last-error":
        clear_last_syntax_error()
        print(json.dumps({"status": "CLEARED"}, indent=2))
        return True

    if first == "--check":
        if len(args) < 2:
            print(json.dumps({"status": "ERROR", "errors": ["Missing file path argument"]}, indent=2))
            sys.exit(1)
        target = Path(args[1]).expanduser().resolve()
        if not target.is_file():
            print(json.dumps({"status": "ERROR", "errors": [f"File not found: {target}"]}, indent=2))
            sys.exit(1)
        errors = validate_code_file(target)
        status = "PASS" if not errors else "ERROR"
        print(json.dumps({"file": str(target), "status": status, "errors": errors}, indent=2))
        sys.exit(0 if not errors else 1)

    if first == "--run-tests":
        ws = args[1] if len(args) > 1 else None
        res = run_project_tests(ws)
        print(json.dumps(res, indent=2))
        sys.exit(0 if res["status"] == "PASS" else 1)

    return False

def main():
    # 0. Check CLI mode
    if handle_cli_mode():
        return

    # 1. Feature flag check
    auto_debug_enabled = os.environ.get("AGY_AUTO_DEBUG", "1").lower() not in ["0", "false", "off", "no"]
    if not auto_debug_enabled:
        return

    # 2. Read stdin JSON payload safely
    payload_str = ""
    try:
        if not sys.stdin.isatty():
            payload_str = sys.stdin.read()
    except (OSError, UnicodeDecodeError):
        payload_str = ""

    # 3. Extract and resolve changed file path
    changed_file = ""
    if payload_str.strip():
        changed_file = resolve_target_file(payload_str)

    if not changed_file and len(sys.argv) > 1:
        # Fallback to positional file argument if not a flag
        if not sys.argv[1].startswith("-"):
            changed_file = sys.argv[1]

    # 4. Perform syntax probe on modified file
    if changed_file:
        file_path = Path(changed_file).expanduser()
        if file_path.is_file():
            errors = validate_code_file(file_path)
            if errors:
                for err in errors:
                    print(f"⚠️ [Antigravity Auto-Debug] {err}", file=sys.stderr)
                # Persist diagnostic record for auto-debug inspection
                try:
                    diag_file = get_diagnostic_file_path()
                    with open(diag_file, "w", encoding="utf-8") as f:
                        json.dump({
                            "file": str(file_path),
                            "errors": errors
                        }, f, indent=2)
                except (OSError, PermissionError) as write_err:
                    print(f"⚠️ [Antigravity Auto-Debug] Diagnostic cache write failed: {write_err}", file=sys.stderr)

if __name__ == "__main__":
    is_cli = len(sys.argv) > 1 and sys.argv[1] in ("--detect", "-d", "--last-error", "--clear-last-error", "--check", "--run-tests")
    try:
        main()
    finally:
        if not is_cli:
            # Guarantee valid JSON {} output on stdout for PostToolUse protocol
            print("{}")
