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

try:
    from install_git_hooks import install_git_hook
except ImportError:
    install_git_hook = None

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

def condense_test_output(raw_stdout: str, raw_stderr: str, max_lines: int = 40) -> str:
    """
    Compresses voluminous test or tool output to preserve LLM context window token hygiene.
    Extracts summary lines, failures, assertion errors, and tracebacks.
    """
    combined = []
    if raw_stdout:
        combined.extend(raw_stdout.splitlines())
    if raw_stderr:
        combined.extend(raw_stderr.splitlines())

    if len(combined) <= max_lines:
        return "\n".join(combined)

    signal_keywords = (
        "FAIL", "ERROR", "AssertionError", "assert ", "panic:", "Exception",
        "Traceback (most recent call last):", "fatal:", "Error:", "=== FAIL",
        "--- FAIL", "failed", "passed", "skipped", "warnings", "warning"
    )

    head = combined[:5]
    tail = combined[-10:]

    high_signal = []
    for idx, line in enumerate(combined[5:-10], start=5):
        stripped = line.strip()
        if any(kw in line for kw in signal_keywords) or stripped.startswith(">") or stripped.startswith("E "):
            high_signal.append(line)
            if idx + 1 < len(combined) - 10:
                high_signal.append(combined[idx + 1])

    # Deduplicate while preserving order
    seen = set()
    filtered_signals = []
    for s in high_signal:
        if s not in seen:
            seen.add(s)
            filtered_signals.append(s)

    middle_budget = max(5, max_lines - len(head) - len(tail) - 2)
    truncated_middle = filtered_signals[:middle_budget]

    omitted = len(combined) - len(head) - len(tail) - len(truncated_middle)
    result = []
    result.extend(head)
    if omitted > 0:
        result.append(f"\n[... Truncated {omitted} verbose lines for context window hygiene ...]\n")
    result.extend(truncated_middle)
    result.append("--- Output Summary ---")
    result.extend(tail)

    return "\n".join(result)

def detect_project_framework(workspace_dir: str | Path | None = None) -> dict:
    """
    Detects project test, linting, race, typecheck, and fuzzing framework from filesystem markers.
    Returns structured dictionary with ecosystem and executable verification commands.
    """
    ws = Path(workspace_dir or Path.cwd()).resolve()

    # 1. Rust Cargo
    if (ws / "Cargo.toml").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "Rust (Cargo)",
            "test_command": "cargo test",
            "lint_command": "cargo clippy --all-targets",
            "typecheck_command": "cargo check --all-targets",
            "race_command": "cargo test",
            "fuzz_command": "cargo test -- --ignored property",
            "benchmark_command": "cargo bench",
            "coverage_command": "cargo tarpaulin --out Stdout || cargo test",
            "mutation_command": "cargo mutants",
            "markers": ["Cargo.toml"]
        }

    # 2. Go
    if (ws / "go.mod").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "Go",
            "test_command": "go test -v ./...",
            "lint_command": "go vet ./... && staticcheck ./...",
            "typecheck_command": "go vet ./...",
            "race_command": "go test -race -v ./...",
            "fuzz_command": "go test -fuzz=. -fuzztime=5s ./...",
            "benchmark_command": "go test -bench=. -benchmem ./...",
            "coverage_command": "go test -v -cover ./...",
            "mutation_command": "go-mutesting ./...",
            "markers": ["go.mod"]
        }

    # 3. Python (uv, poetry, or pytest)
    if (ws / "uv.lock").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "Python (uv)",
            "test_command": "uv run pytest",
            "lint_command": "uv run ruff check . && uv run mypy .",
            "typecheck_command": "uv run mypy .",
            "race_command": "uv run pytest -m race || uv run pytest",
            "fuzz_command": "uv run pytest -m property || uv run pytest",
            "benchmark_command": "uv run pytest -v --benchmark-only",
            "coverage_command": "uv run pytest -v --cov=. --cov-report=term-missing",
            "mutation_command": "uv run mutmut run",
            "markers": ["uv.lock"]
        }
    if (ws / "poetry.lock").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "Python (poetry)",
            "test_command": "poetry run pytest",
            "lint_command": "poetry run mypy .",
            "typecheck_command": "poetry run mypy .",
            "race_command": "poetry run pytest -m race || poetry run pytest",
            "fuzz_command": "poetry run pytest -m property || poetry run pytest",
            "benchmark_command": "poetry run pytest -v --benchmark-only",
            "coverage_command": "poetry run pytest -v --cov=. --cov-report=term-missing",
            "mutation_command": "poetry run mutmut run",
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
            "typecheck_command": "mypy .",
            "race_command": "pytest -m race || pytest -v",
            "fuzz_command": "pytest -m property || pytest -v",
            "benchmark_command": "pytest -v --benchmark-only",
            "coverage_command": "pytest -v --cov=. --cov-report=term-missing",
            "mutation_command": "mutmut run",
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
            "typecheck_command": "npx tsc --noEmit",
            "race_command": "npx vitest run",
            "fuzz_command": "npx vitest run --testNamePattern=fuzz|property",
            "benchmark_command": "npx vitest bench",
            "coverage_command": "npx vitest run --coverage",
            "mutation_command": "npx stryker run",
            "markers": ["vite.config.ts"] if (ws / "vite.config.ts").is_file() else ["vitest.config.ts"]
        }
    if (ws / "bun.lockb").is_file() or (ws / "bunfig.toml").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "Bun",
            "test_command": "bun test",
            "lint_command": "bunx tsc --noEmit && bunx eslint .",
            "typecheck_command": "bunx tsc --noEmit",
            "race_command": "bun test",
            "fuzz_command": "bun test --test-name-pattern=fuzz|property",
            "benchmark_command": "bun test --bench",
            "coverage_command": "bun test --coverage",
            "mutation_command": "bunx stryker run",
            "markers": ["bun.lockb"] if (ws / "bun.lockb").is_file() else ["bunfig.toml"]
        }
    if (ws / "deno.json").is_file() or (ws / "deno.jsonc").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "Deno",
            "test_command": "deno test",
            "lint_command": "deno lint && deno check",
            "typecheck_command": "deno check",
            "race_command": "deno test",
            "fuzz_command": "deno test --filter=fuzz|property",
            "benchmark_command": "deno bench",
            "coverage_command": "deno test --coverage",
            "mutation_command": "deno test",
            "markers": ["deno.json"] if (ws / "deno.json").is_file() else ["deno.jsonc"]
        }
    if (ws / "pnpm-lock.yaml").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "Node (pnpm)",
            "test_command": "pnpm test",
            "lint_command": "pnpm run typecheck",
            "typecheck_command": "pnpm run typecheck || npx tsc --noEmit",
            "race_command": "pnpm test -- --detectOpenHandles",
            "fuzz_command": "pnpm test -- --testNamePattern=fuzz|property",
            "benchmark_command": "pnpm run bench",
            "coverage_command": "pnpm test -- --coverage",
            "mutation_command": "pnpm exec stryker run",
            "markers": ["pnpm-lock.yaml"]
        }
    if has_pkg:
        return {
            "status": "DETECTED",
            "ecosystem": "Node (npm)",
            "test_command": "npm test",
            "lint_command": "npx tsc --noEmit",
            "typecheck_command": "npx tsc --noEmit",
            "race_command": "npm test -- --detectOpenHandles",
            "fuzz_command": "npm test -- --testNamePattern=fuzz|property",
            "benchmark_command": "npm run bench",
            "coverage_command": "npm test -- --coverage",
            "mutation_command": "npx stryker run",
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
            "typecheck_command": "dotnet build",
            "race_command": "dotnet test",
            "fuzz_command": "dotnet test --filter *Fuzz*",
            "benchmark_command": "dotnet test -c Release --filter *Benchmark*",
            "coverage_command": "dotnet test --collect:\"XPlat Code Coverage\"",
            "mutation_command": "dotnet stryker",
            "markers": [cs_files[0].name]
        }

    # 6. Java / Kotlin
    if (ws / "pom.xml").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "Java (Maven)",
            "test_command": "mvn test",
            "lint_command": "mvn compile",
            "typecheck_command": "mvn compile-no-fork || mvn test-compile",
            "race_command": "mvn test -Dtest=*Concurrency*",
            "fuzz_command": "mvn test -Dtest=*Property*",
            "benchmark_command": "mvn test-compile exec:java -Dexec.classpathScope=test",
            "coverage_command": "mvn test jacoco:report",
            "mutation_command": "mvn org.pitest:pitest-maven:mutationCoverage",
            "markers": ["pom.xml"]
        }
    if (ws / "build.gradle").is_file() or (ws / "build.gradle.kts").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "Java/Kotlin (Gradle)",
            "test_command": "./gradlew test",
            "lint_command": "./gradlew check",
            "typecheck_command": "./gradlew compileTestJava",
            "race_command": "./gradlew test --tests *Concurrency*",
            "fuzz_command": "./gradlew test --tests *Property*",
            "benchmark_command": "./gradlew jmh",
            "coverage_command": "./gradlew test jacocoTestReport",
            "mutation_command": "./gradlew pitest",
            "markers": ["build.gradle"]
        }

    # 7. C / C++ (CMake)
    if (ws / "CMakeLists.txt").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "C / C++ (CMake)",
            "test_command": "ctest --output-on-failure",
            "lint_command": "cmake --build build",
            "typecheck_command": "cmake --build build",
            "race_command": "ctest -R race --output-on-failure",
            "fuzz_command": "ctest -R fuzz --output-on-failure",
            "benchmark_command": "ctest -R bench",
            "coverage_command": "ctest -T coverage",
            "mutation_command": "dextool mutate",
            "markers": ["CMakeLists.txt"]
        }

    # 8. Ruby
    if (ws / "Gemfile").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "Ruby (Bundler)",
            "test_command": "bundle exec rspec",
            "lint_command": "bundle exec rubocop",
            "typecheck_command": "bundle exec srb tc || bundle exec rubocop",
            "race_command": "bundle exec rspec --tag race",
            "fuzz_command": "bundle exec rspec --tag property",
            "benchmark_command": "bundle exec rake bench",
            "coverage_command": "COVERAGE=true bundle exec rspec",
            "mutation_command": "bundle exec mutant --include lib --require my_app --use rspec '::MyApp*'",
            "markers": ["Gemfile"]
        }

    # 9. PHP
    if (ws / "composer.json").is_file() or (ws / "phpunit.xml").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "PHP",
            "test_command": "vendor/bin/phpunit",
            "lint_command": "vendor/bin/phpstan analyse",
            "typecheck_command": "vendor/bin/phpstan analyse",
            "race_command": "vendor/bin/phpunit --group race",
            "fuzz_command": "vendor/bin/phpunit --group property",
            "benchmark_command": "vendor/bin/phpbench run",
            "coverage_command": "vendor/bin/phpunit --coverage-text",
            "mutation_command": "vendor/bin/infection",
            "markers": ["composer.json"] if (ws / "composer.json").is_file() else ["phpunit.xml"]
        }

    # 10. Swift
    if (ws / "Package.swift").is_file():
        return {
            "status": "DETECTED",
            "ecosystem": "Swift",
            "test_command": "swift test",
            "lint_command": "swift build",
            "typecheck_command": "swift build",
            "race_command": "swift test --sanitize=thread",
            "fuzz_command": "swift test --filter Property",
            "benchmark_command": "swift test -c release",
            "coverage_command": "swift test --enable-code-coverage",
            "mutation_command": "swift test",
            "markers": ["Package.swift"]
        }

    return {
        "status": "UNKNOWN",
        "ecosystem": "Generic",
        "test_command": "npm test || pytest || cargo test || go test",
        "lint_command": "",
        "typecheck_command": "mypy . || npx tsc --noEmit || cargo check || go vet ./...",
        "race_command": "go test -race ./... || pytest -m race || npm test -- --detectOpenHandles",
        "fuzz_command": "pytest -m property || cargo test -- --ignored property",
        "benchmark_command": "npm run bench || cargo bench || go test -bench=.",
        "coverage_command": "npm test -- --coverage || pytest --cov=. || go test -cover ./...",
        "mutation_command": "npx stryker run || mutmut run || cargo mutants",
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
            shell=True,  # nosec: runner-shell
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
            "stderr": res.stderr,
            "condensed_output": condense_test_output(res.stdout, res.stderr)
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "TIMEOUT",
            "command": cmd,
            "returncode": -1,
            "duration_seconds": round(time.time() - t0, 3),
            "stdout": "",
            "stderr": f"Execution timed out after 120s: {cmd}",
            "condensed_output": f"Execution timed out after 120s: {cmd}"
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "command": cmd,
            "returncode": -1,
            "duration_seconds": round(time.time() - t0, 3),
            "stdout": "",
            "stderr": str(e),
            "condensed_output": str(e)
        }

def run_project_typecheck(workspace_dir: str | Path | None = None, command_override: str = "") -> dict:
    """Executes detected or specified static type check command and captures output."""
    ws = Path(workspace_dir or Path.cwd()).resolve()
    cmd = command_override
    if not cmd:
        det = detect_project_framework(ws)
        cmd = det.get("typecheck_command", "")
    if not cmd:
        return {
            "status": "UNSUPPORTED",
            "command": "",
            "returncode": -1,
            "duration_seconds": 0.0,
            "stdout": "",
            "stderr": "No typecheck command detected for workspace",
            "condensed_output": "No typecheck command detected for workspace"
        }

    t0 = time.time()
    try:
        res = subprocess.run(
            cmd,
            shell=True,  # nosec: runner-shell
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=180
        )
        duration = round(time.time() - t0, 3)
        return {
            "status": "PASS" if res.returncode == 0 else "FAIL",
            "command": cmd,
            "returncode": res.returncode,
            "duration_seconds": duration,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "condensed_output": condense_test_output(res.stdout, res.stderr)
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "TIMEOUT",
            "command": cmd,
            "returncode": -1,
            "duration_seconds": round(time.time() - t0, 3),
            "stdout": "",
            "stderr": f"Typecheck execution timed out after 180s: {cmd}",
            "condensed_output": f"Typecheck execution timed out after 180s: {cmd}"
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "command": cmd,
            "returncode": -1,
            "duration_seconds": round(time.time() - t0, 3),
            "stdout": "",
            "stderr": str(e),
            "condensed_output": str(e)
        }

def run_project_race(workspace_dir: str | Path | None = None, command_override: str = "") -> dict:
    """Executes detected or specified concurrency race detection command and captures output."""
    ws = Path(workspace_dir or Path.cwd()).resolve()
    cmd = command_override
    if not cmd:
        det = detect_project_framework(ws)
        cmd = det.get("race_command", "")
    if not cmd:
        return {
            "status": "UNSUPPORTED",
            "command": "",
            "returncode": -1,
            "duration_seconds": 0.0,
            "stdout": "",
            "stderr": "No race command detected for workspace",
            "condensed_output": "No race command detected for workspace"
        }

    t0 = time.time()
    try:
        res = subprocess.run(
            cmd,
            shell=True,  # nosec: runner-shell
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=180
        )
        duration = round(time.time() - t0, 3)
        return {
            "status": "PASS" if res.returncode == 0 else "FAIL",
            "command": cmd,
            "returncode": res.returncode,
            "duration_seconds": duration,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "condensed_output": condense_test_output(res.stdout, res.stderr)
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "TIMEOUT",
            "command": cmd,
            "returncode": -1,
            "duration_seconds": round(time.time() - t0, 3),
            "stdout": "",
            "stderr": f"Race detection timed out after 180s: {cmd}",
            "condensed_output": f"Race detection timed out after 180s: {cmd}"
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "command": cmd,
            "returncode": -1,
            "duration_seconds": round(time.time() - t0, 3),
            "stdout": "",
            "stderr": str(e),
            "condensed_output": str(e)
        }

def run_project_fuzz(workspace_dir: str | Path | None = None, command_override: str = "") -> dict:
    """Executes detected or specified property-based fuzzing command and captures output."""
    ws = Path(workspace_dir or Path.cwd()).resolve()
    cmd = command_override
    if not cmd:
        det = detect_project_framework(ws)
        cmd = det.get("fuzz_command", "")
    if not cmd:
        return {
            "status": "UNSUPPORTED",
            "command": "",
            "returncode": -1,
            "duration_seconds": 0.0,
            "stdout": "",
            "stderr": "No fuzzing command detected for workspace",
            "condensed_output": "No fuzzing command detected for workspace"
        }

    t0 = time.time()
    try:
        res = subprocess.run(
            cmd,
            shell=True,  # nosec: runner-shell
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=240
        )
        duration = round(time.time() - t0, 3)
        return {
            "status": "PASS" if res.returncode == 0 else "FAIL",
            "command": cmd,
            "returncode": res.returncode,
            "duration_seconds": duration,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "condensed_output": condense_test_output(res.stdout, res.stderr)
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "TIMEOUT",
            "command": cmd,
            "returncode": -1,
            "duration_seconds": round(time.time() - t0, 3),
            "stdout": "",
            "stderr": f"Fuzzing execution timed out after 240s: {cmd}",
            "condensed_output": f"Fuzzing execution timed out after 240s: {cmd}"
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "command": cmd,
            "returncode": -1,
            "duration_seconds": round(time.time() - t0, 3),
            "stdout": "",
            "stderr": str(e),
            "condensed_output": str(e)
        }

def run_project_benchmarks(workspace_dir: str | Path | None = None, command_override: str = "") -> dict:
    """Executes detected or specified benchmark command and captures performance output."""
    ws = Path(workspace_dir or Path.cwd()).resolve()
    cmd = command_override
    if not cmd:
        det = detect_project_framework(ws)
        cmd = det.get("benchmark_command", "")
    if not cmd:
        return {
            "status": "UNSUPPORTED",
            "command": "",
            "returncode": -1,
            "duration_seconds": 0.0,
            "stdout": "",
            "stderr": "No benchmark command detected for workspace",
            "condensed_output": "No benchmark command detected for workspace"
        }

    t0 = time.time()
    try:
        res = subprocess.run(
            cmd,
            shell=True,  # nosec: runner-shell
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=180
        )
        duration = round(time.time() - t0, 3)
        return {
            "status": "PASS" if res.returncode == 0 else "FAIL",
            "command": cmd,
            "returncode": res.returncode,
            "duration_seconds": duration,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "condensed_output": condense_test_output(res.stdout, res.stderr)
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "TIMEOUT",
            "command": cmd,
            "returncode": -1,
            "duration_seconds": round(time.time() - t0, 3),
            "stdout": "",
            "stderr": f"Benchmark execution timed out after 180s: {cmd}",
            "condensed_output": f"Benchmark execution timed out after 180s: {cmd}"
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "command": cmd,
            "returncode": -1,
            "duration_seconds": round(time.time() - t0, 3),
            "stdout": "",
            "stderr": str(e),
            "condensed_output": str(e)
        }

def run_project_coverage(workspace_dir: str | Path | None = None, command_override: str = "") -> dict:
    """Executes detected or specified test coverage command and captures output."""
    ws = Path(workspace_dir or Path.cwd()).resolve()
    cmd = command_override
    if not cmd:
        det = detect_project_framework(ws)
        cmd = det.get("coverage_command", "")
    if not cmd:
        return {
            "status": "UNSUPPORTED",
            "command": "",
            "returncode": -1,
            "duration_seconds": 0.0,
            "stdout": "",
            "stderr": "No coverage command detected for workspace",
            "condensed_output": "No coverage command detected for workspace"
        }

    t0 = time.time()
    try:
        res = subprocess.run(
            cmd,
            shell=True,  # nosec: runner-shell
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=180
        )
        duration = round(time.time() - t0, 3)
        return {
            "status": "PASS" if res.returncode == 0 else "FAIL",
            "command": cmd,
            "returncode": res.returncode,
            "duration_seconds": duration,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "condensed_output": condense_test_output(res.stdout, res.stderr)
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "TIMEOUT",
            "command": cmd,
            "returncode": -1,
            "duration_seconds": round(time.time() - t0, 3),
            "stdout": "",
            "stderr": f"Coverage execution timed out after 180s: {cmd}",
            "condensed_output": f"Coverage execution timed out after 180s: {cmd}"
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "command": cmd,
            "returncode": -1,
            "duration_seconds": round(time.time() - t0, 3),
            "stdout": "",
            "stderr": str(e),
            "condensed_output": str(e)
        }

def get_diff_modified_files(ws: Path) -> list[str]:
    """Finds modified source files via git diff."""
    try:
        res = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(ws),
            capture_output=True,
            text=True,
            check=False
        )
        if res.returncode == 0 and res.stdout.strip():
            return [line.strip() for line in res.stdout.splitlines() if line.strip()]
        res_staged = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(ws),
            capture_output=True,
            text=True,
            check=False
        )
        files = []
        for line in res_staged.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                files.append(parts[-1])
        return files
    except Exception:
        return []

def run_project_mutations(workspace_dir: str | Path | None = None, command_override: str = "", diff_only: bool = False) -> dict:
    """Executes detected or specified mutation test command and captures output."""
    ws = Path(workspace_dir or Path.cwd()).resolve()
    cmd = command_override
    if not cmd:
        det = detect_project_framework(ws)
        cmd = det.get("mutation_command", "")
    if not cmd:
        return {
            "status": "UNSUPPORTED",
            "command": "",
            "returncode": -1,
            "duration_seconds": 0.0,
            "stdout": "",
            "stderr": "No mutation command detected for workspace",
            "condensed_output": "No mutation command detected for workspace"
        }

    diff_files = []
    if diff_only:
        diff_files = get_diff_modified_files(ws)
        if diff_files:
            if "mutmut" in cmd:
                cmd = f"{cmd} --paths-to-mutate={','.join(diff_files)}"
            elif "stryker" in cmd:
                cmd = f"{cmd} --mutate {' '.join(diff_files)}"
            elif "cargo mutants" in cmd:
                cmd = f"{cmd} -f {' -f '.join(diff_files)}"

    t0 = time.time()
    try:
        res = subprocess.run(
            cmd,
            shell=True,  # nosec: runner-shell
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=240
        )
        duration = round(time.time() - t0, 3)
        return {
            "status": "PASS" if res.returncode == 0 else "FAIL",
            "command": cmd,
            "diff_scoped": diff_only,
            "diff_files": diff_files,
            "returncode": res.returncode,
            "duration_seconds": duration,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "condensed_output": condense_test_output(res.stdout, res.stderr)
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "TIMEOUT",
            "command": cmd,
            "diff_scoped": diff_only,
            "diff_files": diff_files,
            "returncode": -1,
            "duration_seconds": round(time.time() - t0, 3),
            "stdout": "",
            "stderr": f"Mutation test execution timed out after 240s: {cmd}",
            "condensed_output": f"Mutation test execution timed out after 240s: {cmd}"
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "command": cmd,
            "diff_scoped": diff_only,
            "diff_files": diff_files,
            "returncode": -1,
            "duration_seconds": round(time.time() - t0, 3),
            "stdout": "",
            "stderr": str(e),
            "condensed_output": str(e)
        }

def run_project_flaky_check(workspace_dir: str | Path | None = None, test_target: str = "", iterations: int = 5, command_override: str = "") -> dict:
    """Executes target test suite N times consecutively to detect timing races and flakiness."""
    ws = Path(workspace_dir or Path.cwd()).resolve()
    cmd = command_override
    if not cmd:
        det = detect_project_framework(ws)
        base_cmd = det.get("test_command", "")
        if test_target:
            if "pytest" in base_cmd:
                cmd = f"{base_cmd.split()[0]} -v {test_target}"
            elif "cargo test" in base_cmd:
                cmd = f"cargo test {test_target}"
            elif "go test" in base_cmd:
                cmd = f"go test -v -run {test_target} ./..."
            elif "vitest" in base_cmd or "jest" in base_cmd:
                cmd = f"{base_cmd} {test_target}"
            else:
                cmd = f"{base_cmd} {test_target}"
        else:
            cmd = base_cmd

    if not cmd:
        return {
            "status": "UNSUPPORTED",
            "iterations": iterations,
            "flakiness_rate": 0.0,
            "stderr": "No test command available for flaky check"
        }

    results = []
    failures = 0
    failure_traces = []

    for i in range(1, iterations + 1):
        t0 = time.time()
        try:
            res = subprocess.run(
                cmd,
                shell=True,  # nosec: runner-shell
                cwd=str(ws),
                capture_output=True,
                text=True,
                timeout=60
            )
            passed = res.returncode == 0
            if not passed:
                failures += 1
                failure_traces.append(f"--- Iteration {i} Failure ---\n{condense_test_output(res.stdout, res.stderr, max_lines=15)}")
            results.append({
                "iteration": i,
                "passed": passed,
                "duration": round(time.time() - t0, 3)
            })
        except Exception as e:
            failures += 1
            failure_traces.append(f"--- Iteration {i} Error: {str(e)} ---")
            results.append({"iteration": i, "passed": False, "error": str(e)})

    flakiness_rate = round(failures / iterations, 2)
    status = "PASS" if failures == 0 else "FAIL"

    return {
        "status": status,
        "test_command": cmd,
        "iterations": iterations,
        "failures": failures,
        "flakiness_rate": flakiness_rate,
        "runs": results,
        "failure_summary": "\n".join(failure_traces) if failure_traces else "All iterations passed consistently."
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

    if first in ("--run-benchmark", "--run-benchmarks", "--benchmark"):
        ws = args[1] if len(args) > 1 else None
        res = run_project_benchmarks(ws)
        print(json.dumps(res, indent=2))
        sys.exit(0 if res["status"] == "PASS" else 1)

    if first in ("--run-coverage", "--coverage"):
        ws = args[1] if len(args) > 1 else None
        res = run_project_coverage(ws)
        print(json.dumps(res, indent=2))
        sys.exit(0 if res["status"] == "PASS" else 1)

    if first in ("--run-mutation", "--run-mutations", "--mutation", "--mutations"):
        ws = None
        diff_only = False
        for arg in args[1:]:
            if arg in ("--diff", "--diff-only"):
                diff_only = True
            elif not arg.startswith("-") and ws is None:
                ws = arg
        res = run_project_mutations(ws, diff_only=diff_only)
        print(json.dumps(res, indent=2))
        sys.exit(0 if res["status"] == "PASS" else 1)

    if first in ("--detect-flaky", "--flaky"):
        ws = None
        target = ""
        iterations = 5
        idx = 1
        while idx < len(args):
            arg = args[idx]
            if arg in ("--iterations", "-n") and idx + 1 < len(args):
                try:
                    iterations = int(args[idx + 1])
                except ValueError as parse_err:
                    iterations = 5
                idx += 2
                continue
            if not arg.startswith("-"):
                if not target:
                    target = arg
                elif not ws:
                    ws = arg
            idx += 1
        res = run_project_flaky_check(ws, test_target=target, iterations=iterations)
        print(json.dumps(res, indent=2))
        sys.exit(0 if res["status"] == "PASS" else 1)

    if first in ("--run-typecheck", "--typecheck"):
        ws = args[1] if len(args) > 1 else None
        res = run_project_typecheck(ws)
        print(json.dumps(res, indent=2))
        sys.exit(0 if res["status"] == "PASS" else 1)

    if first in ("--run-race", "--race"):
        ws = args[1] if len(args) > 1 else None
        res = run_project_race(ws)
        print(json.dumps(res, indent=2))
        sys.exit(0 if res["status"] == "PASS" else 1)

    if first in ("--run-fuzz", "--fuzz"):
        ws = args[1] if len(args) > 1 else None
        res = run_project_fuzz(ws)
        print(json.dumps(res, indent=2))
        sys.exit(0 if res["status"] == "PASS" else 1)

    if first in ("--install-git-hooks", "--install-hook"):
        ws = args[1] if len(args) > 1 else None
        if install_git_hook:
            res = install_git_hook(ws, force=True)
        else:
            res = {"status": "ERROR", "message": "install_git_hooks module unavailable"}
        print(json.dumps(res, indent=2))
        sys.exit(0 if res.get("status") in ("SUCCESS", "ALREADY_INSTALLED") else 1)

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
    is_cli = len(sys.argv) > 1 and sys.argv[1] in (
        "--detect", "-d", "--last-error", "--clear-last-error", "--check",
        "--run-tests", "--run-benchmark", "--run-benchmarks", "--benchmark",
        "--run-coverage", "--coverage", "--run-mutation", "--run-mutations", "--mutation", "--mutations",
        "--detect-flaky", "--flaky",
        "--run-typecheck", "--typecheck", "--run-race", "--race", "--run-fuzz", "--fuzz",
        "--install-git-hooks", "--install-hook"
    )
    try:
        main()
    finally:
        if not is_cli:
            # Guarantee valid JSON {} output on stdout for PostToolUse protocol
            print("{}")
