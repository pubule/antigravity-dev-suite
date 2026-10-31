# 🧠 Memory Safety, Deserialization & Injection Audit Guide

Use this reference when auditing backend services, native extensions, data serialization, and database interaction layers.

---

## 1. Injection Vulnerabilities
- **SQL & NoSQL Injection**:
  - Verify all database queries use parameterized placeholders or safe query builders.
  - Check for raw string concatenation, template literals, or f-strings in SQL statements.
  - Audit NoSQL query parameters for operator injection (e.g., MongoDB `$gt`, `$ne`, `$where`).
- **Command & Code Injection**:
  - Check invocations of `os.system`, `subprocess.Popen(shell=True)`, `eval()`, `exec()`, `Function()`.
  - Prefer passing argument lists over single interpolated shell strings.
- **Path Traversal**:
  - Canonicalize file paths with `resolve()` or `realpath()` before opening file descriptors.
  - Verify base directory containment checks (`child_path.is_relative_to(base_path)`).

---

## 2. Insecure Deserialization
- **Object Deserialization**:
  - Prohibit deserialization of untrusted payloads with Python `pickle`, Java `ObjectInputStream`, or Ruby `Marshal`.
  - Use schema-validated JSON, Protocol Buffers, or safe YAML loaders (`yaml.safe_load`).
- **Prototype Pollution (JavaScript / TypeScript)**:
  - Check deep merge, object assign, and recursive property setter implementations.
  - Guard against `__proto__`, `constructor`, and `prototype` property overrides.

---

## 3. Native Memory Safety (C / C++ / Rust Unsafe)
- **Bounds Checking**:
  - Verify array indexing and slice accesses have explicit bounds validation.
  - Inspect pointer arithmetic for integer overflow and sign conversion errors.
- **Resource Lifecycle**:
  - Check for use-after-free, double-free, and dangling pointers.
  - Verify Rust `unsafe` blocks enforce invariant validation and do not leak undefined behavior.
