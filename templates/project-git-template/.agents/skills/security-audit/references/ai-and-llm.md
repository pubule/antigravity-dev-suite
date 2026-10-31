# 🤖 AI, LLM & Agentic Tool Execution Audit Guide

Use this reference when auditing applications integrating Large Language Models, autonomous agents, prompt pipelines, and tool execution frameworks.

---

## 1. Prompt Injection & Instruction Overrides
- **Direct & Indirect Prompt Injection**:
  - Identify where untrusted data (user messages, email bodies, web pages, retrieved documents) enters prompt context.
  - Verify separation between system instructions and untrusted input blocks.
  - Check for instruction delimiters and structured role segregation.
- **Context Poisoning & Retrieval (RAG)**:
  - Inspect document chunking and indexing pipelines for malicious payload injection.
  - Ensure embeddings and retrieval filters enforce tenant access boundaries.

---

## 2. Agent Tool-Use & Autonomous Execution
- **Arbitrary Command / Tool Execution**:
  - Never allow LLMs to directly execute shell commands without strict command whitelisting.
  - Validate and sanitize all tool arguments with typed schemas (e.g., Pydantic, Zod) prior to execution.
  - Prevent command chaining via shell operators (`;`, `&&`, `||`, `|`, `$(...)`).
- **Filesystem & Resource Sandboxing**:
  - Enforce chroot or workspace path scoping on all file-reading and writing tools.
  - Reject absolute paths (`/etc/passwd`), Windows drive letters (`C:\`), and path traversal tokens (`../`).
  - Restrict file modification to explicitly authorized directory trees.

---

## 3. Credential & Data Leakage
- **Secret Extraction via Agents**:
  - Ensure API keys, bearer tokens, and internal endpoints are omitted from LLM prompts.
  - Sanitize LLM completion outputs before sending responses to end users.
  - Restrict subagent inter-process communication to avoid privilege escalation.
