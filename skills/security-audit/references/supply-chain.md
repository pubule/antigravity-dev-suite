# 📦 Supply Chain & Dependency Threat Vectors

This reference catalog details attack classes for software supply chain security, package managers, and third-party dependencies.

---

## 1. Known CVEs in Transitive Dependencies

### Vulnerability Mechanics
Applications inherit vulnerabilities from transitive dependencies. Even if direct dependencies appear secure, sub-dependencies may expose critical flaws.

### Audit Checklist
1. **Automated Package Scans**:
   - Python: Execute `pip-audit` or `safety check`.
   - Node / JavaScript: Execute `npm audit --audit-level=high` or `pnpm audit`.
   - Rust: Execute `cargo audit`.
   - Go: Execute `govulncheck ./...`.
2. **Reachability Analysis**:
   - Verify if the vulnerable function in the dependency is actually imported or called by the application.
   - Do not report CVEs from uncalled, non-reachable modules as high-severity findings.

---

## 2. Lockfile Integrity & Dependency Confusion

### Vulnerability Mechanics
- Attackers register malicious packages on public registries (PyPI, npm, crates.io) using internal organization package names.
- Build tools prioritize public registries over private package feeds unless scoped registries are configured.

### Audit Checklist
1. **Scoped Package Configuration**:
   - Ensure internal packages use organization scopes (`@org/package` in npm).
   - Configure `.npmrc` or `pip.conf` with explicit index-url restrictions.
2. **Lockfile Enforcement**:
   - Verify that CI/CD pipelines use deterministic install commands (`npm ci`, `poetry install --sync`, `cargo build --locked`).
   - Flag uncommitted or missing lockfiles (`package-lock.json`, `poetry.lock`, `Cargo.lock`, `pnpm-lock.yaml`).

---

## 3. Malicious Lifecycle Install Hooks

### Vulnerability Mechanics
Package managers allow packages to execute shell scripts during installation (`postinstall` in npm, `setup.py` arbitrary execution, `build.rs` in Cargo). Attackers exploit these hooks to exfiltrate environment variables and tokens during `npm install`.

### Audit Checklist
1. **Install Scripts Audit**:
   - Search for `postinstall`, `preinstall`, and `install` fields in `package.json` dependencies.
   - Run npm installs with `--ignore-scripts` where build scripts are unnecessary.
2. **Build Script Sandboxing**:
   - Inspect custom `build.rs` scripts for network access, process execution, or filesystem writes outside the build target directory.

---

## 4. Typosquatting & Unpinned Dependencies

### Vulnerability Mechanics
Attackers publish packages with names resembling popular libraries (`cross-env` vs `crossenv`, `reqeusts` vs `requests`). Loose version constraints (`*`, `latest`, `^`) allow unexpected breaking or malicious updates.

### Audit Checklist
1. **Pinned Ranges**:
   - Verify that all production dependencies specify pinned or tightly bounded versions.
   - Reject wildcards (`*`, `latest`) in dependencies.
2. **Registry Integrity**:
   - Check package integrity checksums (SHA-512 hashes in lockfiles).
   - Reject unverified git repository dependencies without commit hashes.
