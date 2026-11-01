---
name: handoff
description: Compact and serialize the current conversation state into a structured handoff document for another agent, session, or worktree to pick up. Triggered by the /handoff slash command.
---

# 📋 Session Handoff Pipeline (`/handoff`)

Use this skill when completing an agent session, hitting context boundaries, or transferring execution to a fresh agent, another model, or a parallel worktree. It generates a portable, zero-fluff Markdown handoff document in the operating system temporary directory (`$TMPDIR`) without polluting the workspace git repository.

---

## 🚀 Operational Workflow

```mermaid
flowchart TD
    H1["User Triggers /handoff [goal]"] --> H2["Inspect Active Git State & Telemetry"]
    H2 --> H3["Scrub Sensitive Keys & Secrets (OWASP Rule 7)"]
    H3 --> H4["Generate ASD-STE100 Briefing in OS Tempdir"]
    H4 --> H5["Recommend Next Suggested Skills"]
    H5 --> Done["✅ Display Handoff File Path & Next Steps"]
```

---

### Step 1: Parse Input & Target Objective
- Capture the optional goal or focus provided by the user (e.g. `/handoff complete the payment retry logic`).
- If no argument is provided, synthesize the immediate next milestone from the active plan or task list.

### Step 2: Deterministic Telemetry & Context Extraction
Execute the deterministic handoff runner:
```bash
python3 scripts/handoff.py "<target-goal>" --summary "<implementation-notes>"
```
Or via the auto debug runner:
```bash
python3 scripts/auto_debug_runner.py --handoff "<target-goal>"
```

The script autonomously:
1. Queries current Git branch, modified files, and last commit hash.
2. Injects the last recorded test run status (`PASS` / `FAIL`).
3. Injects the last recorded critic loop audit status.
4. Redacts all API keys, access tokens, and private keys.
5. Emits a clean Markdown document into `tempfile.gettempdir()`.

### Step 3: ASD-STE100 Handoff Document Structure
The created briefing document adheres to strict engineering invariants:
- **Portability**: Stored in the system temporary directory (`/tmp` or `%TEMP%`).
- **No Token Duplication**: Links to files and ADRs by path (`file:///...`), never copy-pasting entire code blocks.
- **Architectural Constraints**: Explicitly lists KISS, YAGNI, and invariant requirements.
- **Dead-Ends**: Documents failed approaches so the subsequent agent does not repeat them.
- **Suggested Skills**: Specifies exact slash commands for the incoming session:
  - `/opus-dev`: For end-to-end TDD and closed-loop verification.
  - `/plan`: For milestone decomposition.
  - `/auto-debug`: When test failures require autonomous resolution.
  - `/code-review`: When static hygiene or security violations require inspection.
  - `/commit`: When changes are verified green and ready for atomic conventional commit.

### Step 4: Present Output to User
Output the absolute path to the generated handoff file and summarize the recommended starting command for the next session.
