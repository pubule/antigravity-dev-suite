#!/usr/bin/env python3
"""Integrity checks of the Stop gate: the shortcuts a fast model takes to look done.

All checks read only the lines the change added or removed (git diff against the
session's base commit), so legacy code never blocks agy.

Failures (the change is not done):
- elided code: `// ... existing code ...`, `# rest of the code unchanged`. A model that
  writes these into a file deletes the code it did not repeat;
- focused or disabled tests: `it.only`, `fit`, `it.skip`, `xit`, `@pytest.mark.skip`,
  `@unittest.skip`, `xfail`, `#[ignore]`, `@Disabled`. A green run that skips the test
  that fails proves nothing;
- debugger statements: `debugger`, `breakpoint()`, `pdb.set_trace()`, `binding.pry`, `dbg!`;
- JS/TS imports of packages that are not declared and not installed (invented packages).

Reviews (agy must look once and explain):
- stubs and new TODOs: `raise NotImplementedError`, `throw new Error("not implemented")`,
  `todo!()`, `// TODO`, `implement this later`;
- weakened tests: assertions removed from existing tests, expected values changed,
  test files deleted, conditional skips added;
- `console.log` left in production code;
- Python imports that resolve to no local module, installed package or declared dependency.

Python 3.9+ standard library only. Works on macOS, Linux and Windows.
"""

from __future__ import annotations

import difflib
import importlib.util
import json
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

logger = logging.getLogger("integrity")

Finding = Tuple[str, str]  # (title, detail)

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
MAX_ITEMS = 15

JS_EXT = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte", ".astro"}
PY_EXT = {".py", ".pyi"}

TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|__tests__|spec|specs|testing|e2e)/"
    r"|(^|/)test_[^/]+$|_test\.[A-Za-z0-9]+$|\.(test|spec)\.[A-Za-z0-9]+$"
    r"|_spec\.rb$|Tests?\.(java|kt|cs|swift)$|(^|/)conftest\.py$"
)


def is_test(rel: str) -> bool:
    return bool(TEST_PATH_RE.search(rel))


# ------------------------------------------------------------------------ diff

def git(args: List[str], cwd: Path, timeout: int = 30) -> Tuple[int, str]:
    try:
        res = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True,
                             timeout=timeout, check=False, encoding="utf-8", errors="replace")
        return res.returncode, res.stdout or ""
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


class FileDiff:
    def __init__(self, rel: str) -> None:
        self.rel = rel
        self.added: List[Tuple[int, str]] = []  # (line number in the new file, text)
        self.removed: List[str] = []
        self.new_file = False


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def file_diff(root: Path, base: str, rel: str) -> FileDiff:
    """Added and removed lines of `rel` between `base` and the work tree."""
    d = FileDiff(rel)
    code, out = git(["diff", "-U0", "--no-color", "--no-ext-diff", base or "HEAD", "--", rel], root)
    tracked = git(["ls-files", "--error-unmatch", "--", rel], root)[0] == 0
    if code != 0 or (not out.strip() and not tracked) or "\nnew file mode" in "\n" + out:
        d.new_file = True
    if code != 0 or (not out.strip() and not tracked):
        d.added = list(enumerate(_read(root / rel).splitlines(), 1))
        return d
    line_no = 0
    for line in out.splitlines():
        m = HUNK_RE.match(line)
        if m:
            line_no = int(m.group(3))
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            d.added.append((line_no, line[1:]))
            line_no += 1
        elif line.startswith("-"):
            d.removed.append(line[1:])
    return d


def deleted_files(root: Path, base: str) -> List[str]:
    code, out = git(["diff", "--name-only", "--diff-filter=D", "-z", base or "HEAD"], root)
    return [p for p in out.split("\0") if p] if code == 0 else []


# ---------------------------------------------------------------- elided code

COMMENT_RE = re.compile(r"^\s*(?://+|#+|/\*+|\*|<!--|\{\s*/\*+|--)\s*(?P<text>.*?)\s*(?:\*+/\s*\}?|-->)?\s*$")
DOTS = ("...", "…")
# "// ... other methods" (dots first) or "// existing code ..." (dots last).
ELISION_LEAD_RE = re.compile(
    r"\b(existing|rest|remaining|unchanged|previous|same|other|omitted|truncated|original|"
    r"esistente|resto|invariat[oaie]|precedente|altr[oaie])\b", re.IGNORECASE)
ELISION_TRAIL_RE = re.compile(
    r"\b(existing|rest\s+of|remaining|unchanged|omitted|truncated|esistente|resto|invariat[oaie])\b",
    re.IGNORECASE)
ELISION_PHRASE_RE = re.compile(
    r"^\[?\(?\s*(the\s+)?rest\s+of\s+(the\s+)?(code|file|implementation|function|class|component|"
    r"methods?|module|logic|tests?|styles?)\b"
    r"|\b(code|implementation|content|logic|everything\s+else)\s+(remains?|stays?|is)\s+(the\s+same|unchanged)\b"
    r"|^\[?\(?\s*(keep|leave)\s+(the\s+)?(rest|existing|remaining)\b"
    r"|^\[?\(?\s*(existing|previous|original)\s+(code|implementation|logic|content|imports?|methods?|styles?)"
    r"\s*(here|unchanged|as\s+(is|before))?\s*\]?\)?\s*$",
    re.IGNORECASE)


def is_elision(line: str) -> bool:
    m = COMMENT_RE.match(line)
    if not m:
        return False
    text = m.group("text").strip().strip("[](){}").strip()
    if text in DOTS:
        return True
    if text.startswith(DOTS) and ELISION_LEAD_RE.search(text):
        return True
    if text.endswith(DOTS) and ELISION_TRAIL_RE.search(text):
        return True
    return bool(ELISION_PHRASE_RE.search(text))


# --------------------------------------------------------------------- tests

FOCUS_RE = re.compile(r"\b(?:it|test|describe|context|suite|specify)\.only\s*\(|(?<![\w.])(?:fit|fdescribe|ftest)\s*\(")
SKIP_RE = re.compile(
    r"\b(?:it|test|describe|context|suite|specify)\.skip\s*\("
    r"|(?<![\w.])(?:xit|xdescribe|xtest|xcontext|xspecify)\s*\("
    r"|@pytest\.mark\.skip\b(?!if)"
    r"|@pytest\.mark\.xfail\b"
    r"|@unittest\.skip\b(?!If|Unless)"
    r"|@unittest\.expectedFailure\b"
    r"|#\[ignore\]"
    r"|@(?:Disabled|Ignore)\b"
)
COND_SKIP_RE = re.compile(r"@pytest\.mark\.skipif\b|@unittest\.skip(?:If|Unless)\b|\.skipIf\s*\(|\.runIf\s*\(")
# Skip calls inside a test body: fine under an `if`, a disabled test otherwise.
SKIP_CALL_RE = re.compile(r"\bpytest\.skip\s*\(|\bself\.skipTest\s*\(|\bt\.Skip(?:f|Now)?\s*\(")
GUARD_LINE_RE = re.compile(r"^\s*(?:\}\s*)?(?:if|elif|else|except|try|catch)\b|^\s*\}?\s*else\b")
ASSERT_RE = re.compile(
    r"(?<![\w.])assert\b|\bexpect\s*\(|\.assert[A-Z_]\w*\s*\(|(?<![\w.])assert[A-Z_]\w*\s*\(|\bassert_\w*!\s*\("
    r"|\bt\.(?:Error|Errorf|Fatal|Fatalf|Fail)\b|\brequire\.\w+\s*\(|\.should\b|\bpytest\.raises\s*\("
    r"|\.to(?:Be|Equal|Have|Throw|Match|Contain|StrictEqual)\w*\s*\("
)


STRING_RE = re.compile(r"""(['"`])(?:\\.|(?!\1).)*\1""")


def code_part(text: str) -> str:
    """The line with the content of string literals removed, so a test that writes
    `"@pytest.mark.skip"` into a fixture, or a regex that names `debugger`, is not a finding."""
    return STRING_RE.sub(lambda m: m.group(1) * 2, text)


def _comment_only(text: str) -> bool:
    return bool(re.match(r"^\s*(?://|#|/\*|\*|<!--)", text))


def _guarded(lines: List[str], n: int) -> bool:
    """True when line `n` (1-based) sits on or right under an if/else/except line."""
    if 0 < n <= len(lines) and re.match(r"^\s*if\b.*:\s*\S", lines[n - 1]):
        return True  # `if cond: pytest.skip(...)` on one line
    for i in range(n - 2, max(-1, n - 4), -1):
        prev = lines[i] if 0 <= i < len(lines) else ""
        if not prev.strip():
            continue
        return bool(GUARD_LINE_RE.search(prev))
    return False


def test_findings(root: Path, diffs: List[FileDiff], deleted: List[str]) -> Tuple[List[str], List[str], List[str]]:
    """(disabled or focused tests, weakened tests, conditional skips)."""
    disabled: List[str] = []
    weakened: List[str] = []
    conditional: List[str] = []
    for d in diffs:
        if not is_test(d.rel):
            continue
        lines = _read(root / d.rel).splitlines()
        for n, raw in d.added:
            if _comment_only(raw):
                continue
            text = code_part(raw)
            if FOCUS_RE.search(text):
                disabled.append(f"{d.rel}:{n}: focused test (runs only this one): {raw.strip()}")
            elif SKIP_RE.search(text):
                disabled.append(f"{d.rel}:{n}: disabled test: {raw.strip()}")
            elif COND_SKIP_RE.search(text):
                conditional.append(f"{d.rel}:{n}: {raw.strip()}")
            elif SKIP_CALL_RE.search(text) and not _guarded(lines, n):
                disabled.append(f"{d.rel}:{n}: unconditional skip: {raw.strip()}")
        if d.new_file:
            continue
        removed_asserts = [r.strip() for r in d.removed if ASSERT_RE.search(r) and not _comment_only(r)]
        added_asserts = [a.strip() for _, a in d.added if ASSERT_RE.search(a) and not _comment_only(a)]
        added_set = set(added_asserts)
        gone = [r for r in removed_asserts if r not in added_set]
        if not gone:
            continue
        if len(removed_asserts) > len(added_asserts):
            weakened.append(f"{d.rel}: {len(removed_asserts) - len(added_asserts)} fewer assertion(s) "
                            f"(-{len(removed_asserts)} +{len(added_asserts)})")
        pool = [a for a in added_asserts if a not in set(removed_asserts)]
        for r in gone[:6]:
            match = difflib.get_close_matches(r, pool, n=1, cutoff=0.6)
            if match:
                weakened.append(f"{d.rel}: expectation changed:\n    was: {r[:160]}\n    now: {match[0][:160]}")
    for rel in deleted:
        if is_test(rel):
            weakened.append(f"{rel}: test file deleted")
    return disabled, weakened, conditional


# ------------------------------------------------------------- stubs, debug

STUB_RE = re.compile(
    r"\braise\s+NotImplementedError\b"
    r"|\bthrow\s+new\s+\w*Error\s*\(\s*['\"`][^'\"`]*\b(?:not\s+(?:yet\s+)?implemented|todo|implement\s+me)\b"
    r"|(?<![\w.])(?:todo|unimplemented)!\s*\("
    r"|\bpanic\s*\(\s*\"(?:TODO|not\s+implemented)"
    r"|\bthrow\s+new\s+(?:UnsupportedOperationException|NotImplementedException)\s*\(",
    re.IGNORECASE,
)
TODO_RE = re.compile(
    r"(?://|#|/\*|\*|<!--|--)\s*.*?(?:\b(?:TODO|FIXME|XXX|HACK)\b"
    r"|\bimplement\s+(?:this|me|later|here)\b|\byour\s+(?:code|logic|implementation)\s+here\b"
    r"|\badd\s+(?:your\s+|the\s+)?(?:logic|implementation)\s+here\b)",
    re.IGNORECASE,
)
DEBUGGER_RE = re.compile(
    r"^\s*debugger\s*;?\s*(?://.*)?$|(?<![\w.])breakpoint\s*\(\s*\)|\bimport\s+i?pdb\b|\bi?pdb\.set_trace\s*\("
    r"|\bbinding\.(?:pry|irb)\b|(?<![\w.])dbg!\s*\("
)
# `throw new Error("not implemented")` needs the message: the stripped line keeps only the call.
THROW_RE = re.compile(r"\bthrow\s+new\s+\w*Error\s*\(\s*(['\"`])\1|\bpanic\s*\(\s*\"\"")
CONSOLE_RE = re.compile(r"\bconsole\.(?:log|debug|trace|dir)\s*\(")
CONSOLE_OK_RE = re.compile(r"(^|/)(scripts?|bin|cli|tools?|examples?|docs?)/|\.config\.\w+$|(^|/)(cli|server)\.\w+$")


def stub_and_debug_findings(root: Path, diffs: List[FileDiff]) -> Tuple[List[str], List[str], List[str]]:
    """(debugger statements, stubs/TODOs, console.log in production code)."""
    debug: List[str] = []
    stubs: List[str] = []
    console: List[str] = []
    for d in diffs:
        suffix = Path(d.rel).suffix.lower()
        test = is_test(d.rel)
        abstract = suffix in PY_EXT and re.search(r"abstractmethod|\bProtocol\b", _read(root / d.rel))
        for n, raw in d.added:
            text = code_part(raw)
            comment = _comment_only(raw)
            if DEBUGGER_RE.search(text) and not comment:
                debug.append(f"{d.rel}:{n}: {raw.strip()}")
            if test:
                continue
            if STUB_RE.search(raw) and not comment and (STUB_RE.search(text) or THROW_RE.search(text)):
                if not (abstract and "NotImplementedError" in text):
                    stubs.append(f"{d.rel}:{n}: {raw.strip()}")
            elif TODO_RE.search(text):
                stubs.append(f"{d.rel}:{n}: {raw.strip()}")
            if suffix in JS_EXT and CONSOLE_RE.search(text) and not comment \
                    and not CONSOLE_OK_RE.search(d.rel):
                console.append(f"{d.rel}:{n}: {raw.strip()}")
    return debug, stubs, console


# ------------------------------------------------------------------- imports

NODE_BUILTINS = {
    "assert", "async_hooks", "buffer", "child_process", "cluster", "console", "constants", "crypto",
    "dgram", "diagnostics_channel", "dns", "domain", "events", "fs", "http", "http2", "https",
    "inspector", "module", "net", "os", "path", "perf_hooks", "process", "punycode", "querystring",
    "readline", "repl", "stream", "string_decoder", "sys", "timers", "tls", "trace_events", "tty",
    "url", "util", "v8", "vm", "wasi", "worker_threads", "zlib", "test",
}
JS_IMPORT_RES = (
    re.compile(r"^\s*(?:import|export)\b[^'\"`]*?\bfrom\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"^\s*\}?[\w\s,{}*]*\bfrom\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"^\s*import\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"\brequire\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"),
    re.compile(r"\bimport\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"),
)
DEP_KEYS = ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
BUNDLER_CONFIGS = ("vite.config", "vitest.config", "webpack.config", "next.config", "nuxt.config",
                   "svelte.config", "astro.config", "rollup.config", "babel.config", ".babelrc", "jest.config")

PY_IMPORT_RE = re.compile(r"^(?P<indent>\s*)(?:import\s+(?P<mods>[\w.]+(?:\s*,\s*[\w.]+)*)|from\s+(?P<from>[\w.]+)\s+import\b)")
# Import name -> distribution name, for the most common mismatches.
PY_DIST_NAMES = {
    "PIL": "pillow", "yaml": "pyyaml", "cv2": "opencv", "sklearn": "scikit-learn", "bs4": "beautifulsoup4",
    "dateutil": "python-dateutil", "dotenv": "python-dotenv", "jwt": "pyjwt", "attr": "attrs",
    "OpenSSL": "pyopenssl", "Crypto": "pycryptodome", "serial": "pyserial", "docx": "python-docx",
    "magic": "python-magic", "multipart": "python-multipart", "google": "google", "jose": "python-jose",
    "pkg_resources": "setuptools", "zmq": "pyzmq", "MySQLdb": "mysqlclient", "psycopg2": "psycopg2",
    "win32api": "pywin32", "win32con": "pywin32", "pythoncom": "pywin32", "Levenshtein": "levenshtein",
}
PY_DEP_FILES = ("pyproject.toml", "setup.cfg", "setup.py", "Pipfile", "environment.yml", "environment.yaml")


def _strip_jsonc(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"(?m)(^|[^:\"'])//.*$", r"\1", text)


def _load_json(p: Path) -> Dict:
    try:
        data = json.loads(_strip_jsonc(_read(p)))
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def _package_name(spec: str) -> str:
    spec = spec.split("?")[0]
    parts = spec.split("/")
    return "/".join(parts[:2]) if spec.startswith("@") and len(parts) > 1 else parts[0]


def _ancestors(root: Path, rel: str) -> List[Path]:
    out: List[Path] = []
    cur = (root / rel).parent
    while True:
        out.append(cur)
        if cur == root or root not in cur.parents:
            break
        cur = cur.parent
    if root not in out:
        out.append(root)
    return out


class JsResolver:
    def __init__(self, root: Path, tracked: List[str]) -> None:
        self.root = root
        self.workspace_names: Set[str] = set()
        self.alias_keys: List[str] = []
        self.base_dirs: List[Path] = [root / "src"]
        self.config_text = ""
        for rel in tracked:
            name = rel.rsplit("/", 1)[-1]
            if name == "package.json" and "node_modules/" not in rel:
                pkg = _load_json(root / rel).get("name")
                if isinstance(pkg, str):
                    self.workspace_names.add(pkg)
            elif re.match(r"^[tj]sconfig(\.[\w-]+)?\.json$", name) and "node_modules/" not in rel:
                opts = _load_json(root / rel).get("compilerOptions") or {}
                for key in (opts.get("paths") or {}):
                    self.alias_keys.append(str(key).rstrip("*").rstrip("/"))
                if isinstance(opts.get("baseUrl"), str):
                    self.base_dirs.append((root / rel).parent / opts["baseUrl"])
            elif name.startswith(BUNDLER_CONFIGS) and "node_modules/" not in rel:
                self.config_text += _read(root / rel)

    def declared(self, rel: str) -> Tuple[Set[str], bool]:
        """Declared dependency names visible from `rel`, and whether any package.json exists."""
        names: Set[str] = set()
        found = False
        for d in _ancestors(self.root, rel):
            pj = d / "package.json"
            if pj.is_file():
                found = True
                data = _load_json(pj)
                for key in DEP_KEYS:
                    deps = data.get(key)
                    if isinstance(deps, dict):
                        names.update(deps)
        return names, found

    def installed(self, rel: str, pkg: str) -> Tuple[bool, bool]:
        """(package found in a node_modules, any node_modules exists)."""
        any_nm = False
        for d in _ancestors(self.root, rel):
            nm = d / "node_modules"
            if nm.is_dir():
                any_nm = True
                if (nm / pkg).exists():
                    return True, True
        return False, any_nm

    def is_alias(self, spec: str) -> bool:
        for key in self.alias_keys:
            if key and (spec == key or spec.startswith(key + "/")):
                return True
        first = spec.split("/")[0]
        if first and re.search(r"['\"]" + re.escape(first) + r"['\"/]", self.config_text):
            return True
        for bd in self.base_dirs:
            cand = bd / first
            if cand.exists() or any(cand.with_name(first + ext).exists() for ext in (".ts", ".tsx", ".js", ".jsx")):
                return True
        return False


def _js_specs(text: str) -> List[str]:
    specs: List[str] = []
    for rx in JS_IMPORT_RES:
        for m in rx.finditer(text):
            if m.group(1) not in specs:
                specs.append(m.group(1))
    return specs


def js_import_findings(root: Path, diffs: List[FileDiff], tracked: List[str]) -> Tuple[List[str], List[str]]:
    """(missing packages with node_modules present, missing packages without node_modules)."""
    hard: List[str] = []
    soft: List[str] = []
    resolver: Optional[JsResolver] = None
    seen: Set[Tuple[str, str]] = set()
    for d in diffs:
        if Path(d.rel).suffix.lower() not in JS_EXT:
            continue
        for n, text in d.added:
            if _comment_only(text):
                continue
            for spec in _js_specs(text):
                if spec.startswith((".", "/", "~", "#", "$", "@/")) or ":" in spec or not spec.strip():
                    continue
                pkg = _package_name(spec)
                if pkg in NODE_BUILTINS or (pkg, d.rel) in seen:
                    continue
                seen.add((pkg, d.rel))
                if resolver is None:
                    resolver = JsResolver(root, tracked)
                declared, has_pkg_json = resolver.declared(d.rel)
                if not has_pkg_json or pkg in declared or pkg in resolver.workspace_names:
                    continue
                if pkg.startswith("@types/") or resolver.is_alias(spec):
                    continue
                installed, any_nm = resolver.installed(d.rel, pkg)
                if installed:
                    continue
                line = f"{d.rel}:{n}: '{pkg}' ({text.strip()[:120]})"
                (hard if any_nm else soft).append(line)
    return hard, soft


def _py_local_modules(tracked: List[str]) -> Set[str]:
    mods: Set[str] = set()
    for rel in tracked:
        p = Path(rel)
        if p.suffix in (".py", ".pyi", ".pyx", ".so", ".pyd"):
            mods.add(p.name.split(".")[0])
            mods.update(part for part in p.parts[:-1])
    return mods


def _py_site_packages(root: Path) -> List[Path]:
    out: List[Path] = []
    for env in (".venv", "venv", "env", ".env"):
        base = root / env
        if not base.is_dir():
            continue
        out.extend(base.glob("lib/python*/site-packages"))
        out.extend(base.glob("lib64/python*/site-packages"))
        if (base / "Lib" / "site-packages").is_dir():
            out.append(base / "Lib" / "site-packages")
    return out


def _py_installed(top: str, sites: List[Path]) -> bool:
    for sp in sites:
        if (sp / top).exists() or (sp / f"{top}.py").exists() or any(sp.glob(f"{top}.*.so")) \
                or any(sp.glob(f"{top}*.pyd")) or (sp / f"{top}.pth").exists():
            return True
    try:
        return importlib.util.find_spec(top) is not None
    except (ImportError, ValueError):
        return False


def _py_declared_text(root: Path, tracked: List[str]) -> str:
    chunks: List[str] = []
    for rel in tracked:
        name = rel.rsplit("/", 1)[-1]
        if name in PY_DEP_FILES or re.match(r"^requirements.*\.(txt|in)$", name):
            chunks.append(_read(root / rel).lower())
    return "\n".join(chunks)


def py_import_findings(root: Path, diffs: List[FileDiff], tracked: List[str]) -> List[str]:
    found: List[str] = []
    local: Optional[Set[str]] = None
    sites: List[Path] = []
    declared = ""
    stdlib = set(getattr(sys, "stdlib_module_names", ())) | set(sys.builtin_module_names)
    seen: Set[str] = set()
    for d in diffs:
        if Path(d.rel).suffix.lower() not in PY_EXT:
            continue
        guarded = bool(re.search(r"except\s*\(?[^)\n]*(ImportError|ModuleNotFoundError)", _read(root / d.rel)))
        for n, text in d.added:
            m = PY_IMPORT_RE.match(text)
            if not m:
                continue
            if m.group("indent") and guarded:
                continue  # optional import inside try/except ImportError
            mods = [m.group("from")] if m.group("from") else [x.strip() for x in m.group("mods").split(",")]
            for mod in mods:
                if not mod or mod.startswith("."):
                    continue
                top = mod.split(".")[0]
                if top in seen or top in stdlib or top == "__future__":
                    continue
                seen.add(top)
                if local is None:
                    local = _py_local_modules(tracked)
                    sites = _py_site_packages(root)
                    declared = _py_declared_text(root, tracked)
                if top in local or _py_installed(top, sites):
                    continue
                names = {top.lower(), top.lower().replace("_", "-"), PY_DIST_NAMES.get(top, top).lower()}
                if any(re.search(r"(?<![\w-])" + re.escape(nm) + r"(?![\w-])", declared) for nm in names):
                    continue
                found.append(f"{d.rel}:{n}: '{top}' ({text.strip()[:120]})")
    return found


# ----------------------------------------------------------------------- main

def _tracked_files(root: Path) -> List[str]:
    code, out = git(["ls-files", "-co", "--exclude-standard", "-z"], root)
    return [p for p in out.split("\0") if p] if code == 0 else []


def _bullets(items: Iterable[str]) -> str:
    items = list(items)
    text = "\n".join(f"- {i}" for i in items[:MAX_ITEMS])
    if len(items) > MAX_ITEMS:
        text += f"\n- ... and {len(items) - MAX_ITEMS} more"
    return text


def check_integrity(root: Path, base: str, files: List[str]) -> Tuple[List[Finding], List[Finding]]:
    """Returns (failures, reviews) for the changed code files."""
    failures: List[Finding] = []
    reviews: List[Finding] = []
    diffs = [file_diff(root, base, rel) for rel in files]
    deleted = deleted_files(root, base)

    elided = [f"{d.rel}:{n}: {t.strip()}" for d in diffs for n, t in d.added if is_elision(t)]
    if elided:
        failures.append((
            "Code replaced by a placeholder comment",
            _bullets(elided) + "\nThese comments stand for code you did not write out. In a file edit they "
            "DELETE that code. Open each file, restore the missing code from `git diff` or the original, and "
            "write the complete content.",
        ))

    disabled, weakened, conditional = test_findings(root, diffs, deleted)
    if disabled:
        failures.append((
            "Tests disabled or focused",
            _bullets(disabled) + "\nA passing run that skips tests proves nothing. Remove the skip/only and "
            "make the test pass by fixing the code. If a test really must be disabled, stop and ask the user.",
        ))

    debug, stubs, console = stub_and_debug_findings(root, diffs)
    if debug:
        failures.append(("Debugger statements left in the code", _bullets(debug) + "\nRemove them."))

    tracked: Optional[List[str]] = None
    if any(Path(d.rel).suffix.lower() in JS_EXT | PY_EXT for d in diffs):
        tracked = _tracked_files(root)
    if tracked is not None:
        hard, soft = js_import_findings(root, diffs, tracked)
        if hard:
            failures.append((
                "Imports of packages that are not installed or declared",
                _bullets(hard) + "\nThese packages are in no package.json and not in node_modules. If the "
                "name is wrong, use the real module. If you need a new dependency, install it with the "
                "project's package manager (it updates package.json) and say so in your answer.",
            ))
        if soft:
            reviews.append((
                "Imports of packages not declared in package.json",
                _bullets(soft) + "\nnode_modules is missing, so they could not be checked. Add each real "
                "dependency to package.json; fix the name if a package does not exist.",
            ))
        py_missing = py_import_findings(root, diffs, tracked)
        if py_missing:
            reviews.append((
                "Python imports that resolve to nothing",
                _bullets(py_missing) + "\nNo local module, installed package or declared dependency has "
                "these names. Fix invented or misspelled modules. For a real new dependency, add it to "
                "requirements/pyproject and say so.",
            ))

    if weakened:
        reviews.append((
            "Existing tests weakened",
            _bullets(weakened) + "\nIf an old expectation was right, the bug is in your code: restore the "
            "test and fix the code. Change an expectation only when the user asked for the new behaviour, "
            "and say which one and why.",
        ))
    if conditional:
        reviews.append((
            "Conditional skips added to tests",
            _bullets(conditional) + "\nCheck that the condition is real (platform, missing optional tool) "
            "and that the test still runs in this project.",
        ))
    if stubs:
        reviews.append((
            "Unfinished code: stubs and TODOs",
            _bullets(stubs) + "\nImplement what the task needs now. Keep a TODO only for work outside the "
            "task, and list it in your answer.",
        ))
    if console:
        reviews.append((
            "console.log left in production code",
            _bullets(console) + "\nRemove debug output, or use the project's logger.",
        ))
    return failures, reviews


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Integrity checks on the diff against a base commit.")
    ap.add_argument("dir", nargs="?", default=".")
    ap.add_argument("--base", default="HEAD")
    args = ap.parse_args()
    top = Path(args.dir).resolve()
    rc, out = git(["rev-parse", "--show-toplevel"], top)
    repo = Path(out.strip()) if rc == 0 else top
    rc, out = git(["diff", "--name-only", args.base], repo)
    rc2, out2 = git(["ls-files", "-o", "--exclude-standard"], repo)
    from agy_hook import is_code
    changed = sorted({p for p in (out + "\n" + out2).splitlines() if p and is_code(p) and (repo / p).is_file()})
    fails, revs = check_integrity(repo, args.base, changed)
    for title, detail in fails + revs:
        print(f"## {title}\n{detail}\n")
    sys.exit(1 if fails else 0)
