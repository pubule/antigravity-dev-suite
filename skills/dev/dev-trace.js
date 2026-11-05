#!/usr/bin/env node
/**
 * dev-trace — production traces for /dev pipeline runs.
 *
 * Stop guessing what the agent did. Every Claude Code session that has the `dev`
 * plugin installed records, automatically and without relying on the model:
 *
 *   - tool calls      name, summarized + redacted input, outcome, error text
 *   - latency         per tool call (PreToolUse → PostToolUse) and per model call
 *   - reasoning steps the thinking/text that preceded each tool call (from the transcript)
 *   - failures        PostToolUseFailure + transcript tool_result is_error
 *   - pipeline        /dev phase transitions and gate verdicts (from .dev-pipeline-state.json)
 *   - subagents       SubagentStart/Stop + their own tool calls and reasoning
 *   - workflow agents per-agent spans returned by implement-and-review.js
 *   - nested AI      headless CLI runs (claude -p, gemini -p, agy -p, codex exec, ...):
 *                    model, turns, tokens, cost, the nested agent's tool calls and
 *                    errors (parsed from --output-format json/stream-json), and a
 *                    link to the child session's own trace
 *
 * Storage: one append-only JSONL file per session in `<git-common-dir>/dev-trace/`
 * (shared by every worktree of the repo, never in the working tree, never committed).
 * Outside a git repo: `~/.claude/dev-trace/<cwd-hash>/`.
 *
 * Usage:
 *   node dev-trace.js hook                 hook entry point (reads the event JSON on stdin)
 *   node dev-trace.js list                 recent sessions
 *   node dev-trace.js summary [sid|latest] phases, per-tool latency, failures, slowest calls
 *   node dev-trace.js show [sid] [--failures] [--slow N]   chronological timeline
 *   node dev-trace.js failures [sid]       each failure with the reasoning that led to it
 *   node dev-trace.js export [sid]         OTLP/JSON (Jaeger, Phoenix, Langfuse, Tempo ...)
 *   node dev-trace.js doctor               is tracing working for this repo/session?
 *   node dev-trace.js path                 print the trace directory
 *   node dev-trace.js --selftest
 *
 * Environment:
 *   DEV_TRACE=0                 disable recording entirely
 *   DEV_TRACE_DIR=<dir>         override the storage directory
 *   DEV_TRACE_CONTENT=summary   summary (default) | full (longer inputs) | minimal (names and paths only)
 *   DEV_TRACE_GATE=0            disable the Stop check on unresolved verification failures
 *   DEV_TRACE_RETENTION_DAYS=14 sessions older than this are pruned at SessionStart
 *
 * Node >= 18, stdlib only. The hook path never throws and never blocks, except the
 * deliberate one-time Stop block described in `stopGate`.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const crypto = require('crypto');

const SCHEMA = 1;
const MAX_WALK_UP = 12;

// ─── configuration ──────────────────────────────────────────────────

function contentMode() {
  const m = (process.env.DEV_TRACE_CONTENT || 'summary').toLowerCase();
  return ['full', 'minimal'].includes(m) ? m : 'summary';
}

function limits() {
  const mode = contentMode();
  if (mode === 'full') return { field: 8000, reason: 4000, error: 4000 };
  if (mode === 'minimal') return { field: 0, reason: 0, error: 300 };
  return { field: 2000, reason: 800, error: 1500 };
}

// ─── redaction ──────────────────────────────────────────────────────

const SECRET_PATTERNS = [
  [/-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g, '[REDACTED:private-key]'],
  [/\bsk-ant-[A-Za-z0-9_-]{10,}/g, '[REDACTED]'],
  [/\bsk-[A-Za-z0-9_-]{20,}/g, '[REDACTED]'],
  [/\bgh[pousr]_[A-Za-z0-9]{20,}/g, '[REDACTED]'],
  [/\bgithub_pat_[A-Za-z0-9_]{20,}/g, '[REDACTED]'],
  [/\bAKIA[0-9A-Z]{16}\b/g, '[REDACTED]'],
  [/\bAIza[0-9A-Za-z_-]{30,}/g, '[REDACTED]'],
  [/\bxox[baprs]-[A-Za-z0-9-]{10,}/g, '[REDACTED]'],
  [/\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/g, '[REDACTED:jwt]'],
  [/(\bBearer\s+)[A-Za-z0-9._~+/-]{8,}=*/gi, '$1[REDACTED]'],
  [/(:\/\/[^/\s:@]+:)[^@\s/]+@/g, '$1[REDACTED]@'],
  [/((?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret|authorization)["']?\s*[:=]\s*)("[^"]*"|'[^']*'|[^\s,;&]+)/gi, '$1[REDACTED]'],
];

function redact(s) {
  if (typeof s !== 'string' || !s) return s;
  let out = s;
  for (const [re, rep] of SECRET_PATTERNS) out = out.replace(re, rep);
  return out;
}

function clip(s, n) {
  if (s === undefined || s === null) return s;
  const str = typeof s === 'string' ? s : JSON.stringify(s);
  if (!n) return '';
  return str.length > n ? str.slice(0, n) + `… [+${str.length - n} chars]` : str;
}

const clean = (s, n) => clip(redact(typeof s === 'string' ? s : JSON.stringify(s)), n);

// ─── locations ──────────────────────────────────────────────────────

/** The git common dir for `start` (shared by all worktrees), without spawning git. */
function gitCommonDir(start) {
  let dir = path.resolve(start || process.cwd());
  for (let i = 0; i < MAX_WALK_UP; i++) {
    const dotgit = path.join(dir, '.git');
    let st = null;
    try { st = fs.statSync(dotgit); } catch { /* not here */ }
    if (st && st.isDirectory()) return dotgit;
    if (st && st.isFile()) {
      const m = fs.readFileSync(dotgit, 'utf8').match(/^gitdir:\s*(.+)$/m);
      if (!m) return null;
      const gitdir = path.resolve(dir, m[1].trim());
      try {
        const common = fs.readFileSync(path.join(gitdir, 'commondir'), 'utf8').trim();
        return path.resolve(gitdir, common);
      } catch {
        return gitdir;
      }
    }
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
  return null;
}

function traceDir(cwd) {
  if (process.env.DEV_TRACE_DIR) return path.resolve(process.env.DEV_TRACE_DIR);
  const common = gitCommonDir(cwd);
  if (common) return path.join(common, 'dev-trace');
  const hash = crypto.createHash('sha256').update(path.resolve(cwd || process.cwd())).digest('hex').slice(0, 12);
  return path.join(os.homedir(), '.claude', 'dev-trace', hash);
}

const safeId = (s) => String(s || 'unknown').replace(/[^A-Za-z0-9._-]/g, '_').slice(0, 120);
const sessionFile = (dir, sid) => path.join(dir, safeId(sid) + '.jsonl');
const sideFile = (dir, sid, kind) => path.join(dir, '.' + safeId(sid) + '.' + kind + '.json');

/** Walk up from cwd to the repo root looking for an active /dev pipeline state file. */
function findPipelineState(cwd) {
  let dir = path.resolve(cwd || process.cwd());
  for (let i = 0; i < MAX_WALK_UP; i++) {
    const f = path.join(dir, '.dev-pipeline-state.json');
    if (fs.existsSync(f)) return f;
    if (fs.existsSync(path.join(dir, '.git'))) return null;
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
  return null;
}

function readJson(file, fallback) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return fallback; }
}

function writeJson(file, obj) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = file + '.' + process.pid + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(obj));
  fs.renameSync(tmp, file);
}

// ─── writing events ─────────────────────────────────────────────────

function append(dir, sid, evt) {
  fs.mkdirSync(dir, { recursive: true });
  const now = evt.t || Date.now();
  const line = JSON.stringify({ v: SCHEMA, t: now, ts: new Date(now).toISOString(), sid, ...evt });
  fs.appendFileSync(sessionFile(dir, sid), line + '\n');
}

// ─── input / output summaries ───────────────────────────────────────

function summarizeInput(tool, input) {
  const L = limits();
  const minimal = contentMode() === 'minimal';
  const i = input && typeof input === 'object' ? input : {};
  switch (tool) {
    case 'Bash':
    case 'PowerShell':
      return { command: minimal ? clean(i.command, 120) : clean(i.command, L.field), description: clip(i.description, 200), background: i.run_in_background || undefined };
    case 'Read':
      return { file_path: i.file_path, offset: i.offset, limit: i.limit };
    case 'Write':
      return { file_path: i.file_path, bytes: typeof i.content === 'string' ? Buffer.byteLength(i.content) : undefined };
    case 'Edit':
      return { file_path: i.file_path, old_len: (i.old_string || '').length, new_len: (i.new_string || '').length, replace_all: i.replace_all || undefined };
    case 'MultiEdit':
      return { file_path: i.file_path, edits: Array.isArray(i.edits) ? i.edits.length : undefined };
    case 'NotebookEdit':
      return { notebook_path: i.notebook_path, edit_mode: i.edit_mode };
    case 'Grep':
      return { pattern: clean(i.pattern, 300), path: i.path, glob: i.glob, output_mode: i.output_mode };
    case 'Glob':
      return { pattern: i.pattern, path: i.path };
    case 'Task':
    case 'Agent':
      return { subagent_type: i.subagent_type, description: clip(i.description, 200), prompt: minimal ? undefined : clean(i.prompt, Math.min(L.field, 600)) };
    case 'Skill':
      return { skill: i.skill || i.command, args: clean(i.args, 300) };
    case 'Workflow':
      return { scriptPath: i.scriptPath, args: minimal ? undefined : clean(i.args, 800) };
    case 'WebFetch':
      return { url: clean(i.url, 500) };
    case 'WebSearch':
      return { query: clean(i.query, 300) };
    default:
      return minimal ? {} : { raw: clean(i, Math.min(L.field, 600)) };
  }
}

function responseSize(resp) {
  if (resp === undefined || resp === null) return 0;
  try { return Buffer.byteLength(typeof resp === 'string' ? resp : JSON.stringify(resp)); } catch { return 0; }
}

/** Bash responses carry no exit code in PostToolUse; detect the obvious failure shapes. */
function responseFailure(tool, resp) {
  if (!resp || typeof resp !== 'object') return null;
  if (resp.is_error === true || resp.isError === true) return clean(resp.error || resp.content || 'tool reported is_error', limits().error);
  if (resp.interrupted === true) return 'interrupted';
  if (typeof resp.exitCode === 'number' && resp.exitCode !== 0) return clean(`Exit code ${resp.exitCode}\n${resp.stderr || ''}`, limits().error);
  if (resp.success === false) return clean(resp.error || resp.message || 'success=false', limits().error);
  return null;
}

// ─── devTrace ingestion from the implement-and-review.js Workflow result ──

function findDevTrace(obj, depth = 0) {
  if (depth > 6 || obj === null || obj === undefined) return null;
  if (typeof obj === 'string') {
    if (!obj.includes('devTrace')) return null;
    try { return findDevTrace(JSON.parse(obj), depth + 1); } catch { /* fall through */ }
    const m = obj.match(/\{[\s\S]*"devTrace"[\s\S]*\}/);
    if (m) { try { return findDevTrace(JSON.parse(m[0]), depth + 1); } catch { /* ignore */ } }
    return null;
  }
  if (Array.isArray(obj)) {
    for (const x of obj) { const r = findDevTrace(x, depth + 1); if (r) return r; }
    return null;
  }
  if (typeof obj === 'object') {
    if (obj.devTrace && Array.isArray(obj.devTrace.spans)) return obj.devTrace;
    for (const k of Object.keys(obj)) { const r = findDevTrace(obj[k], depth + 1); if (r) return r; }
  }
  return null;
}

// ─── transcript ingestion (reasoning, model latency, tokens, tool_result errors) ──

function textOf(content) {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) return content.map((c) => (c && (c.text || c.content)) || '').filter((x) => typeof x === 'string').join('\n');
  return '';
}

/**
 * Read the new part of a transcript JSONL (from the stored byte offset) and emit
 * `llm`, `reasoning` and `tool.result` events. Offsets are kept per transcript path,
 * so parent and subagent transcripts are each read exactly once.
 */
function ingestTranscript(dir, sid, transcriptPath, agent) {
  if (!transcriptPath || !fs.existsSync(transcriptPath)) return 0;
  const cursorFile = sideFile(dir, sid, 'cursor');
  const cursors = readJson(cursorFile, {});
  const cur = cursors[transcriptPath] || { offset: 0, lastTs: null };
  const size = fs.statSync(transcriptPath).size;
  if (size < cur.offset) { cur.offset = 0; } // transcript rewritten (compaction): start over
  if (size === cur.offset) return 0;

  const fd = fs.openSync(transcriptPath, 'r');
  let chunk;
  try {
    const len = size - cur.offset;
    const buf = Buffer.alloc(len);
    fs.readSync(fd, buf, 0, len, cur.offset);
    chunk = buf.toString('utf8');
  } finally {
    fs.closeSync(fd);
  }
  const lastNl = chunk.lastIndexOf('\n');
  if (lastNl < 0) return 0; // only a partial line so far
  const complete = chunk.slice(0, lastNl);
  const consumed = Buffer.byteLength(chunk.slice(0, lastNl + 1));

  const L = limits();
  const messages = new Map(); // message.id -> aggregate
  const order = [];
  let lastTs = cur.lastTs;
  let emitted = 0;

  const flush = () => {
    for (const id of order) {
      const m = messages.get(id);
      const tools = m.toolUses.map((t) => t.id);
      const start = m.prevTs ? Date.parse(m.prevTs) : null;
      const end = Date.parse(m.lastTs);
      append(dir, sid, {
        t: end || undefined,
        ev: 'llm', id, agent, model: m.model,
        start: start || undefined, dur_ms: start && end ? Math.max(0, end - start) : undefined,
        in_tok: m.usage.input_tokens, out_tok: m.usage.output_tokens,
        cache_read: m.usage.cache_read_input_tokens, cache_write: m.usage.cache_creation_input_tokens,
        stop: m.stop, tools,
      });
      emitted++;
      const reasoning = [m.thinking.join('\n').trim(), m.text.join('\n').trim()].filter(Boolean).join('\n---\n');
      if (L.reason && reasoning) {
        append(dir, sid, {
          t: end || undefined,
          ev: 'reasoning', id, agent,
          kind: tools.length ? 'tool-decision' : 'answer',
          thinking: m.thinking.length > 0 && m.thinking.join('').trim().length > 0,
          for: tools.length ? m.toolUses.map((t) => `${t.name}#${t.id}`) : undefined,
          text: clean(reasoning, L.reason),
        });
        emitted++;
      }
    }
    messages.clear();
    order.length = 0;
  };

  for (const line of complete.split('\n')) {
    if (!line.trim()) continue;
    let e;
    try { e = JSON.parse(line); } catch { continue; }
    const ts = e.timestamp || null;
    if (e.type === 'assistant' && e.message) {
      const msg = e.message;
      const id = msg.id || e.uuid;
      if (!messages.has(id)) {
        messages.set(id, { prevTs: lastTs, lastTs: ts, model: msg.model, usage: {}, thinking: [], text: [], toolUses: [], stop: null });
        order.push(id);
      }
      const agg = messages.get(id);
      if (ts) agg.lastTs = ts;
      if (msg.usage) agg.usage = msg.usage;
      if (msg.stop_reason) agg.stop = msg.stop_reason;
      for (const b of Array.isArray(msg.content) ? msg.content : []) {
        if (!b) continue;
        if (b.type === 'thinking' && b.thinking) agg.thinking.push(b.thinking);
        else if (b.type === 'text' && b.text) agg.text.push(b.text);
        else if (b.type === 'tool_use') {
          agg.toolUses.push({ id: b.id, name: b.name });
          // transcript-side record of the call: keeps the trace complete even when
          // the Pre/PostToolUse hooks did not fire (older Claude Code, hooks disabled)
          append(dir, sid, { t: Date.parse(ts) || undefined, ev: 'tool.call', id: b.id, tool: b.name, agent, input: summarizeInput(b.name, b.input) });
          emitted++;
        }
      }
    } else if (e.type === 'user' && e.message) {
      flush();
      const content = e.message.content;
      if (Array.isArray(content)) {
        for (const b of content) {
          if (b && b.type === 'tool_result') {
            append(dir, sid, {
              t: Date.parse(ts) || undefined,
              ev: 'tool.result', id: b.tool_use_id, agent, ok: b.is_error !== true,
              error: b.is_error === true ? clean(textOf(b.content), L.error) : undefined,
            });
            emitted++;
          }
        }
      }
      if (ts) lastTs = ts;
    }
  }
  flush();

  cursors[transcriptPath] = { offset: cur.offset + consumed, lastTs };
  writeJson(cursorFile, cursors);
  return emitted;
}

// ─── nested AI calls: headless CLIs (claude -p, gemini -p, agy -p, codex exec, ...) ──

/**
 * Headless AI CLIs the agent may shell out to during a /dev run. `headless` decides
 * whether the invocation is a one-shot non-interactive run; `structured` lists the
 * output flags that make the run's internals (turns, tool calls, tokens, errors)
 * parseable; `requireStructured` CLIs are denied at PreToolUse while a pipeline is
 * active unless such a flag is present, because otherwise the nested agent is a
 * black box in the trace.
 */
const AI_CLIS = {
  claude: { headless: (a) => a.has('-p') || a.has('--print'), structured: ['--output-format'], requireStructured: true, fix: '--output-format stream-json --verbose (or json)' },
  gemini: { headless: (a) => a.has('-p') || a.has('--prompt'), structured: ['--output-format', '-o'], requireStructured: true, fix: '--output-format json (or stream-json)' },
  codex: { headless: (a, t) => t[0] === 'exec' || t[0] === 'e', structured: ['--json', '--experimental-json'], requireStructured: true, fix: 'exec --json' },
  'cursor-agent': { headless: (a) => a.has('-p') || a.has('--print'), structured: ['--output-format'], requireStructured: true, fix: '--output-format stream-json' },
  qwen: { headless: (a) => a.has('-p') || a.has('--prompt'), structured: ['--output-format', '-o'], requireStructured: false },
  agy: { headless: (a) => a.has('-p') || a.has('--print') || a.has('--prompt'), structured: ['--output-format', '--json', '-o'], requireStructured: false },
  antigravity: { headless: (a) => a.has('-p') || a.has('--print') || a.has('--prompt'), structured: ['--output-format', '--json', '-o'], requireStructured: false },
  opencode: { headless: (a, t) => t[0] === 'run', structured: ['--format'], requireStructured: false },
  ollama: { headless: (a, t) => t[0] === 'run', structured: ['--format'], requireStructured: false },
  aider: { headless: (a) => a.has('-m') || a.has('--message') || a.has('--message-file'), structured: [], requireStructured: false },
  llm: { headless: () => true, structured: [], requireStructured: false },
};
const NPX_ALIASES = { '@anthropic-ai/claude-code': 'claude', '@google/gemini-cli': 'gemini', '@openai/codex': 'codex' };

function shellTokens(segment) {
  const out = [];
  const re = /"((?:[^"\\]|\\.)*)"|'([^']*)'|(\S+)/g;
  let m;
  while ((m = re.exec(segment))) out.push(m[1] !== undefined ? m[1] : m[2] !== undefined ? m[2] : m[3]);
  return out;
}

/** Find headless AI CLI invocations in a shell command. */
function detectAiCalls(command) {
  if (typeof command !== 'string' || !command) return [];
  const found = [];
  // split on pipes / command separators / subshell openers (quoted text stays inside its segment well enough)
  for (const seg of command.split(/\|\||&&|[;|\n]|\$\(|`/)) {
    let toks = shellTokens(seg.trim());
    while (toks.length && (/^[A-Za-z_][A-Za-z0-9_]*=/.test(toks[0]) || ['env', 'time', 'nohup', 'exec', 'sudo', 'command', 'timeout'].includes(toks[0]) || /^\d+[smh]?$/.test(toks[0]))) toks = toks.slice(1);
    if (!toks.length) continue;
    let name = path.basename(toks[0]).replace(/\.(cmd|exe|ps1)$/i, '');
    let rest = toks.slice(1);
    if (name === 'npx' || name === 'bunx' || name === 'pnpx') {
      const pkg = rest.find((t) => !t.startsWith('-')) || '';
      name = NPX_ALIASES[pkg.replace(/@[^@/]*$/, '')] || NPX_ALIASES[pkg] || '';
      rest = rest.slice(rest.indexOf(pkg) + 1);
    }
    const spec = AI_CLIS[name];
    if (!spec) continue;
    const flags = new Set(rest.filter((t) => t.startsWith('-')).map((t) => t.split('=')[0]));
    const positional = rest.filter((t) => !t.startsWith('-'));
    if (!spec.headless(flags, positional)) continue;
    const val = (names) => {
      for (let i = 0; i < rest.length; i++) {
        const [k, v] = rest[i].split('=');
        if (names.includes(k)) return v !== undefined ? v : rest[i + 1];
      }
      return undefined;
    };
    const structuredFlag = spec.structured.find((f) => flags.has(f));
    const booleanFlag = ['--json', '--experimental-json'].includes(structuredFlag);
    const format = booleanFlag ? 'json' : structuredFlag ? (val([structuredFlag]) && !String(val([structuredFlag])).startsWith('-') ? val([structuredFlag]) : 'json') : undefined;
    found.push({
      cli: name,
      model: val(['--model', '-m']) && name !== 'aider' ? val(['--model', '-m']) : val(['--model']),
      output_format: format && format !== 'text' ? format : undefined,
      structured: !!format && format !== 'text',
      requireStructured: spec.requireStructured,
      fix: spec.fix,
      session_flag: val(['--session-id', '--resume', '-r']),
    });
  }
  return found;
}

/**
 * Parse the structured output of a nested AI CLI run (claude json/stream-json,
 * gemini json/stream-json, codex --json, or any JSONL event stream). Best effort:
 * returns null when stdout is plain text.
 */
function parseAiOutput(stdout) {
  if (typeof stdout !== 'string' || !stdout.trim()) return null;
  const docs = [];
  const whole = stdout.trim();
  try { docs.push(JSON.parse(whole)); } catch {
    for (const l of whole.split('\n')) { const t = l.trim(); if (t.startsWith('{')) { try { docs.push(JSON.parse(t)); } catch { /* not json */ } } }
  }
  if (!docs.length) return null;
  const r = { tools: {}, tool_errors: 0 };
  const addTool = (name) => { if (name) r.tools[name] = (r.tools[name] || 0) + 1; };
  for (const d of docs) {
    if (!d || typeof d !== 'object') continue;
    // Claude Code: final result object
    if (d.type === 'result' || d.session_id || d.total_cost_usd !== undefined) {
      if (d.session_id) r.child_session = d.session_id;
      if (d.num_turns !== undefined) r.turns = d.num_turns;
      if (d.duration_api_ms !== undefined) r.api_ms = d.duration_api_ms;
      if (d.total_cost_usd !== undefined) r.cost_usd = d.total_cost_usd;
      if (d.is_error === true || (d.subtype && d.subtype !== 'success')) r.error = clip(d.subtype || 'error', 200);
      if (d.usage) { r.in_tok = (d.usage.input_tokens || 0) + (d.usage.cache_read_input_tokens || 0) + (d.usage.cache_creation_input_tokens || 0); r.out_tok = d.usage.output_tokens; }
      if (d.modelUsage) r.model = Object.keys(d.modelUsage).join(',');
    }
    // stream events carrying tool calls (Claude stream-json assistant messages, generic tool_use events)
    if (d.message && Array.isArray(d.message.content)) for (const b of d.message.content) if (b && b.type === 'tool_use') addTool(b.name);
    if (d.message && Array.isArray(d.message.content)) for (const b of d.message.content) if (b && b.type === 'tool_result' && b.is_error) r.tool_errors++;
    if (d.type === 'tool_use' || d.type === 'tool_call') addTool(d.tool_name || d.name || (d.tool && d.tool.name));
    if ((d.type === 'tool_result' && (d.status === 'error' || d.is_error)) || d.type === 'error') r.tool_errors += d.type === 'error' ? 0 : 1;
    if (d.type === 'error' || (d.error && typeof d.error === 'object')) r.error = clean((d.error && (d.error.message || d.error.type)) || d.message || 'error', 300);
    // Gemini CLI json: { response, stats: { models, tools }, error? }
    if (d.stats && typeof d.stats === 'object') {
      const models = d.stats.models || {};
      r.model = Object.keys(models).join(',') || r.model;
      for (const m of Object.values(models)) {
        if (m.tokens) { r.in_tok = (r.in_tok || 0) + (m.tokens.prompt || m.tokens.input || 0); r.out_tok = (r.out_tok || 0) + (m.tokens.candidates || m.tokens.output || 0); }
        if (m.api) { r.api_ms = (r.api_ms || 0) + (m.api.totalLatencyMs || 0); r.api_errors = (r.api_errors || 0) + (m.api.totalErrors || 0); r.turns = (r.turns || 0) + (m.api.totalRequests || 0); }
      }
      const t = d.stats.tools;
      if (t) {
        r.tool_errors += t.totalFail || 0;
        for (const [name, v] of Object.entries(t.byName || {})) r.tools[name] = (r.tools[name] || 0) + (v.count || 0);
      }
    }
    // Codex --json usage events
    if (d.type === 'turn.completed' && d.usage) { r.in_tok = (r.in_tok || 0) + (d.usage.input_tokens || 0); r.out_tok = (r.out_tok || 0) + (d.usage.output_tokens || 0); r.turns = (r.turns || 0) + 1; }
    if (d.item && (d.item.type === 'command_execution' || d.item.type === 'mcp_tool_call') && d.type === 'item.completed') addTool(d.item.type === 'mcp_tool_call' ? d.item.tool : 'shell');
  }
  return r;
}

function aiCliGuard(input) {
  if (process.env.DEV_TRACE_GATE === '0') return null;
  if (input.tool_name !== 'Bash' && input.tool_name !== 'PowerShell') return null;
  if (!findPipelineState(input.cwd)) return null;
  const bad = detectAiCalls(input.tool_input && input.tool_input.command).filter((c) => c.requireStructured && !c.structured);
  if (!bad.length) return null;
  return {
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      permissionDecision: 'deny',
      permissionDecisionReason: `dev-trace: headless AI call without structured output — its tool calls, tokens and errors would be invisible in the trace. Re-run with ${bad.map((c) => `${c.cli} ${c.fix}`).join('; ')}. Keep the raw JSON on stdout (or tee it to a file) so the trace can parse it.`,
    },
  };
}

// ─── pipeline phases and gates ──────────────────────────────────────

function gateSnapshot(state) {
  const g = {};
  const gates = (state && state.gates) || {};
  for (const k of Object.keys(gates)) g[k] = gates[k];
  for (const k of ['impeccableGate', 'observabilityGate', 'uiQualityGate', 'agentTraceGate']) {
    if (state && state[k] && typeof state[k] === 'object' && 'passed' in state[k]) g[k] = state[k].passed;
  }
  return g;
}

function recordPipelineState(dir, sid, stateFile) {
  const state = readJson(stateFile, null);
  if (!state) return;
  const snapFile = sideFile(dir, sid, 'pipeline');
  const prev = readJson(snapFile, {});
  const now = {
    phase: state.currentPhase,
    completed: state.completedPhases || [],
    magnitude: state.magnitude,
    gates: gateSnapshot(state),
  };
  if (prev.phase !== now.phase || JSON.stringify(prev.completed) !== JSON.stringify(now.completed) || prev.magnitude !== now.magnitude) {
    append(dir, sid, { ev: 'phase', phase: now.phase, completed: now.completed, magnitude: now.magnitude, task: clip(state.task, 200), state_file: stateFile });
  }
  for (const k of Object.keys(now.gates)) {
    if (JSON.stringify((prev.gates || {})[k]) !== JSON.stringify(now.gates[k])) {
      append(dir, sid, { ev: 'gate', gate: k, value: now.gates[k], phase: now.phase });
    }
  }
  writeJson(snapFile, now);
}

function touchesPipelineState(tool, input) {
  if (!input) return false;
  const fp = input.file_path || input.notebook_path || '';
  if (fp && path.basename(fp) === '.dev-pipeline-state.json') return true;
  return (tool === 'Bash' || tool === 'PowerShell') && typeof input.command === 'string' && input.command.includes('.dev-pipeline-state.json');
}

function recordAiCalls(dir, sid, input, ok, resp) {
  if (input.tool_name !== 'Bash' && input.tool_name !== 'PowerShell') return;
  const calls = detectAiCalls(input.tool_input && input.tool_input.command);
  if (!calls.length) return;
  const stdout = resp && typeof resp === 'object' ? resp.stdout : typeof resp === 'string' ? resp : undefined;
  const parsed = calls.length === 1 ? parseAiOutput(stdout) : null;
  for (const c of calls) {
    append(dir, sid, {
      ev: 'ai.cli', id: input.tool_use_id, cli: c.cli, model: (parsed && parsed.model) || c.model,
      output_format: c.output_format, structured: c.structured, parsed: !!parsed,
      ok: ok && !(parsed && parsed.error), error: !ok ? clean(input.error || 'failed', limits().error) : parsed && parsed.error ? parsed.error : undefined,
      child_session: parsed && parsed.child_session, turns: parsed && parsed.turns, api_ms: parsed && parsed.api_ms,
      in_tok: parsed && parsed.in_tok, out_tok: parsed && parsed.out_tok, cost_usd: parsed && parsed.cost_usd,
      tools: parsed && Object.keys(parsed.tools).length ? parsed.tools : undefined,
      tool_errors: parsed && parsed.tool_errors ? parsed.tool_errors : undefined,
    });
  }
}

// ─── analysis (shared by the CLI and the Stop gate) ─────────────────

function readEvents(file) {
  if (!fs.existsSync(file)) return [];
  const out = [];
  for (const line of fs.readFileSync(file, 'utf8').split('\n')) {
    if (!line.trim()) continue;
    try { out.push(JSON.parse(line)); } catch { /* torn line: skip */ }
  }
  return out.sort((a, b) => (a.t || 0) - (b.t || 0));
}

function analyze(events) {
  const tools = new Map();
  const reasoningFor = new Map();
  const llm = [];
  const phases = [];
  const gates = [];
  const workflow = [];
  const aiCalls = [];
  const subagents = new Map();
  const prompts = [];
  let first = null;
  let last = null;
  let cwd = null;

  const call = (id) => {
    if (!tools.has(id)) tools.set(id, { id, tool: null, ok: null, error: null, start: null, end: null, dur_ms: null, input: null, agent: null });
    return tools.get(id);
  };

  for (const e of events) {
    for (const x of [e.t, e.start]) {
      if (typeof x === 'number' && x > 0) { first = first === null ? x : Math.min(first, x); last = last === null ? x : Math.max(last, x); }
    }
    if (e.cwd && !cwd) cwd = e.cwd;
    switch (e.ev) {
      case 'tool.start': {
        const c = call(e.id); c.tool = e.tool; c.start = e.t; c.input = e.input; c.agent = e.agent || c.agent; break;
      }
      case 'tool.end': {
        const c = call(e.id); c.tool = c.tool || e.tool; c.end = e.t;
        if (e.ok === false) { c.ok = false; c.error = e.error || c.error; c.interrupt = e.interrupt; }
        else if (c.ok === null) c.ok = true;
        if (!c.input && e.input) c.input = e.input;
        c.out_bytes = e.out_bytes; break;
      }
      case 'tool.call': {
        const c = call(e.id); c.tool = c.tool || e.tool; c.input = c.input || e.input; c.agent = c.agent || e.agent;
        c.callAt = e.t; break;
      }
      case 'tool.result': {
        if (!e.id) break;
        const c = call(e.id);
        if (e.ok === false) { c.ok = false; c.error = c.error || e.error; }
        else if (c.ok === null) c.ok = true;
        if (!c.end) c.end = e.t;
        break;
      }
      case 'reasoning':
        for (const f of e.for || []) reasoningFor.set(f.split('#').pop(), e.text);
        break;
      case 'llm': llm.push(e); break;
      case 'phase': phases.push(e); break;
      case 'gate': gates.push(e); break;
      case 'workflow.span': workflow.push(e); break;
      case 'ai.cli': aiCalls.push(e); break;
      case 'subagent.start': subagents.set(e.agent_id, { id: e.agent_id, type: e.agent_type, start: e.t }); break;
      case 'subagent.end': {
        const s = subagents.get(e.agent_id) || { id: e.agent_id, type: e.agent_type };
        s.end = e.t; s.dur_ms = s.start ? e.t - s.start : null; subagents.set(e.agent_id, s); break;
      }
      case 'prompt': prompts.push(e); break;
      default: break;
    }
  }

  const calls = [...tools.values()].filter((c) => c.tool || c.ok === false);
  for (const c of calls) {
    if (!c.start && c.callAt) c.start = c.callAt; // hooks missing: fall back to transcript timestamps
    if (c.start && c.end) c.dur_ms = Math.max(0, c.end - c.start);
    c.reasoning = reasoningFor.get(c.id) || null;
  }
  calls.sort((a, b) => (a.start || a.end || 0) - (b.start || b.end || 0));
  calls.forEach((c, i) => { c.n = i + 1; });

  for (const x of aiCalls) {
    const c = tools.get(x.id);
    if (c) { x.dur_ms = c.end && c.start ? c.end - c.start : null; x.start = c.start; if (c.ok === false) { x.ok = false; x.error = x.error || c.error; } }
  }
  return { first, last, cwd, calls, llm, phases, gates, workflow, aiCalls, subagents: [...subagents.values()], prompts };
}

const VERIFY_RE = /\b(test|tests|spec|pytest|jest|vitest|mocha|ava|tap|go\s+(test|build|vet)|cargo\s+(test|build|check|clippy)|npm\s+(run\s+)?(test|build|lint|typecheck|check)|pnpm\s+(run\s+)?(test|build|lint|typecheck)|yarn\s+(test|build|lint|typecheck)|npx\s+(tsc|jest|vitest|eslint|playwright|impeccable)|tsc|eslint|ruff|mypy|pyright|flake8|gradle|gradlew|mvn|make|dotnet\s+(test|build)|ctest|rspec|phpunit|playwright|tox|nox)\b/i;

const normCmd = (s) => String(s || '').replace(/\s+/g, ' ').trim();

/**
 * Verification commands (tests, builds, linters, type checkers) that failed in this
 * turn and were never re-run successfully afterwards. These are the runs an agent
 * most often "forgets" before saying it is done.
 */
function unresolvedVerificationFailures(events) {
  let turnStart = 0;
  for (const e of events) if (e.ev === 'prompt') turnStart = Math.max(turnStart, e.t || 0);
  const turn = events.filter((e) => (e.t || 0) >= turnStart);
  const { calls } = analyze(turn);
  const bash = calls.filter((c) => (c.tool === 'Bash' || c.tool === 'PowerShell') && c.input && c.input.command);
  const out = [];
  for (const f of bash) {
    if (f.ok !== false || f.interrupt) continue;
    if (/doesn't want to proceed|was rejected|permission/i.test(f.error || '')) continue;
    const cmd = normCmd(f.input.command);
    if (!VERIFY_RE.test(cmd)) continue;
    const t = f.start || f.end || 0;
    const fixed = bash.some((c) => c.ok === true && normCmd(c.input.command) === cmd && (c.start || c.end || 0) > t);
    if (!fixed) out.push(f);
  }
  // one entry per command: the latest failure
  const byCmd = new Map();
  for (const f of out) byCmd.set(normCmd(f.input.command), f);
  return [...byCmd.values()];
}

// ─── Stop gate ──────────────────────────────────────────────────────

/**
 * One-time Stop block while a /dev pipeline is active: if a verification command
 * failed this turn and was not re-run green, the agent must either fix it or say
 * plainly that it is still failing. `stop_hook_active` guarantees no loop.
 */
function stopGate(input, dir, sid) {
  if (process.env.DEV_TRACE_GATE === '0' || input.stop_hook_active) return null;
  if (!findPipelineState(input.cwd)) return null;
  const pending = unresolvedVerificationFailures(readEvents(sessionFile(dir, sid)));
  if (!pending.length) return null;
  const lines = pending.map((f) => `- [trace #${f.n} ${f.id}] \`${clip(f.input.command, 160)}\` → ${clip((f.error || 'failed').split('\n').slice(0, 3).join(' | '), 240)}`);
  append(dir, sid, { ev: 'gate', gate: 'trace.unresolved-verification', value: false, count: pending.length });
  return {
    decision: 'block',
    reason: [
      `dev-trace: ${pending.length} verification command(s) FAILED in this turn and were never re-run successfully:`,
      ...lines,
      'Do not guess. Read the failure with `node <dev-skill-dir>/dev-trace.js failures`, then either fix it and re-run the SAME command until it passes,',
      'or state explicitly in your reply that it is still failing and record it verbatim under "Failures & dead ends" in HANDOFF.md. This check fires once per turn.',
    ].join('\n'),
  };
}

// ─── retention ──────────────────────────────────────────────────────

function prune(dir) {
  const days = Number(process.env.DEV_TRACE_RETENTION_DAYS || 14);
  if (!(days > 0) || !fs.existsSync(dir)) return;
  const cutoff = Date.now() - days * 86400000;
  for (const name of fs.readdirSync(dir)) {
    const f = path.join(dir, name);
    try { if (fs.statSync(f).mtimeMs < cutoff) fs.unlinkSync(f); } catch { /* concurrent prune */ }
  }
}

// ─── hook entry point ───────────────────────────────────────────────

function handleHook(input) {
  if (process.env.DEV_TRACE === '0') return null;
  const ev = input.hook_event_name;
  const sid = input.session_id || process.env.CLAUDE_CODE_SESSION_ID || 'unknown';
  const cwd = input.cwd || process.cwd();
  const dir = traceDir(cwd);
  const agent = input.agent_id || undefined;

  switch (ev) {
    case 'SessionStart':
      prune(dir);
      append(dir, sid, { ev: 'session.start', source: input.source, cwd, model: input.model, transcript: input.transcript_path });
      return null;
    case 'UserPromptSubmit':
      ingestTranscript(dir, sid, input.transcript_path);
      append(dir, sid, { ev: 'prompt', cwd, prompt: clean(input.prompt, Math.min(limits().reason || 200, 400)) });
      return null;
    case 'PreToolUse': {
      const denied = aiCliGuard(input);
      append(dir, sid, { ev: 'tool.start', id: input.tool_use_id, tool: input.tool_name, agent, input: summarizeInput(input.tool_name, input.tool_input), denied: denied ? 'unstructured-ai-cli' : undefined });
      return denied;
    }
    case 'PostToolUse': {
      const failure = responseFailure(input.tool_name, input.tool_response);
      append(dir, sid, {
        ev: 'tool.end', id: input.tool_use_id, tool: input.tool_name, agent,
        ok: !failure, error: failure || undefined, out_bytes: responseSize(input.tool_response),
      });
      recordAiCalls(dir, sid, input, true, input.tool_response);
      if (input.tool_name === 'Workflow') {
        const dt = findDevTrace(input.tool_response);
        if (dt) {
          for (const s of dt.spans) {
            append(dir, sid, {
              t: s.end || undefined, ev: 'workflow.span', parent: input.tool_use_id,
              label: s.label, phase: s.phase, start: s.start, dur_ms: s.start && s.end ? s.end - s.start : undefined,
              ok: s.ok !== false, error: s.error ? clean(s.error, limits().error) : undefined,
            });
          }
        }
      }
      if (touchesPipelineState(input.tool_name, input.tool_input)) {
        const sf = (input.tool_input && input.tool_input.file_path && path.basename(input.tool_input.file_path) === '.dev-pipeline-state.json')
          ? input.tool_input.file_path : findPipelineState(cwd);
        if (sf && fs.existsSync(sf)) recordPipelineState(dir, sid, sf);
      }
      return null;
    }
    case 'PostToolUseFailure':
      recordAiCalls(dir, sid, input, false, null);
      append(dir, sid, {
        ev: 'tool.end', id: input.tool_use_id, tool: input.tool_name, agent, ok: false,
        interrupt: input.is_interrupt || undefined, error: clean(input.error || 'failed', limits().error),
      });
      return null;
    case 'SubagentStart':
      append(dir, sid, { ev: 'subagent.start', agent_id: input.agent_id, agent_type: input.agent_type });
      return null;
    case 'SubagentStop':
      ingestTranscript(dir, sid, input.agent_transcript_path, input.agent_id);
      append(dir, sid, { ev: 'subagent.end', agent_id: input.agent_id, agent_type: input.agent_type });
      return null;
    case 'PreCompact':
      ingestTranscript(dir, sid, input.transcript_path);
      append(dir, sid, { ev: 'compact', trigger: input.trigger });
      return null;
    case 'Stop': {
      ingestTranscript(dir, sid, input.transcript_path);
      const sf = findPipelineState(cwd);
      if (sf) recordPipelineState(dir, sid, sf);
      append(dir, sid, { ev: 'turn.end', retry: input.stop_hook_active || undefined });
      return stopGate(input, dir, sid);
    }
    case 'SessionEnd':
      ingestTranscript(dir, sid, input.transcript_path);
      append(dir, sid, { ev: 'session.end', reason: input.reason });
      return null;
    default:
      return null;
  }
}

// ─── CLI ────────────────────────────────────────────────────────────

function fmtDur(ms) {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return '–';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const m = Math.floor(ms / 60000);
  const s = Math.round((ms % 60000) / 1000);
  if (m < 60) return `${m}m${String(s).padStart(2, '0')}s`;
  return `${Math.floor(m / 60)}h${String(m % 60).padStart(2, '0')}m`;
}

const fmtTime = (t) => (t ? new Date(t).toISOString().slice(11, 19) : '--:--:--');

function pct(arr, p) {
  if (!arr.length) return null;
  const s = [...arr].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.ceil((p / 100) * s.length) - 1)];
}

function describeInput(c) {
  const i = c.input || {};
  if (i.command) return '`' + clip(normCmd(i.command), 140) + '`';
  if (i.file_path) return i.file_path;
  if (i.notebook_path) return i.notebook_path;
  if (i.pattern) return `${i.pattern}${i.path ? ' in ' + i.path : ''}`;
  if (i.skill) return `${i.skill}${i.args ? ' ' + clip(i.args, 80) : ''}`;
  if (i.subagent_type || i.description) return `${i.subagent_type || ''} ${i.description || ''}`.trim();
  if (i.url) return i.url;
  if (i.query) return i.query;
  if (i.scriptPath) return i.scriptPath;
  if (i.raw) return clip(i.raw, 120);
  return '';
}

function listSessions(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir)
    .filter((n) => n.endsWith('.jsonl') && !n.startsWith('.'))
    .map((n) => { const f = path.join(dir, n); return { sid: n.slice(0, -6), file: f, mtime: fs.statSync(f).mtimeMs }; })
    .sort((a, b) => b.mtime - a.mtime);
}

function resolveSession(dir, which) {
  const all = listSessions(dir);
  if (!all.length) return null;
  if (!which || which === 'latest') {
    const own = process.env.CLAUDE_CODE_SESSION_ID && all.find((s) => s.sid === safeId(process.env.CLAUDE_CODE_SESSION_ID));
    return own || all[0];
  }
  return all.find((s) => s.sid === safeId(which)) || all.find((s) => s.sid.startsWith(which)) || null;
}

function summaryData(events, sid) {
  const a = analyze(events);
  const byTool = new Map();
  for (const c of a.calls) {
    const k = c.tool || '?';
    if (!byTool.has(k)) byTool.set(k, { tool: k, calls: 0, fail: 0, durs: [] });
    const r = byTool.get(k);
    r.calls++;
    if (c.ok === false) r.fail++;
    if (c.dur_ms !== null) r.durs.push(c.dur_ms);
  }
  const toolStats = [...byTool.values()].map((r) => ({
    tool: r.tool, calls: r.calls, fail: r.fail,
    total_ms: r.durs.reduce((x, y) => x + y, 0), avg_ms: r.durs.length ? r.durs.reduce((x, y) => x + y, 0) / r.durs.length : null,
    p95_ms: pct(r.durs, 95), max_ms: r.durs.length ? Math.max(...r.durs) : null,
  })).sort((x, y) => y.total_ms - x.total_ms);
  const llmMs = a.llm.reduce((x, e) => x + (e.dur_ms || 0), 0);
  const toolMs = a.calls.filter((c) => !c.agent).reduce((x, c) => x + (c.dur_ms || 0), 0);
  const tokens = a.llm.reduce((acc, e) => ({ in: acc.in + (e.in_tok || 0) + (e.cache_read || 0) + (e.cache_write || 0), out: acc.out + (e.out_tok || 0) }), { in: 0, out: 0 });
  const phaseSpans = a.phases.map((p, i) => ({ phase: p.phase, magnitude: p.magnitude, start: p.t, end: (a.phases[i + 1] || {}).t || a.last, dur_ms: ((a.phases[i + 1] || {}).t || a.last) - p.t }));
  return {
    sid, cwd: a.cwd, start: a.first, end: a.last, wall_ms: a.first && a.last ? a.last - a.first : null,
    turns: a.prompts.length, llm_calls: a.llm.length, llm_ms: llmMs, tokens, tool_calls: a.calls.length, tool_ms: toolMs,
    failures: a.calls.filter((c) => c.ok === false), subagents: a.subagents, workflow: a.workflow,
    phases: phaseSpans, gates: a.gates, toolStats,
    slowest: [...a.calls].filter((c) => c.dur_ms !== null).sort((x, y) => y.dur_ms - x.dur_ms).slice(0, 5),
    slowestLlm: [...a.llm].filter((e) => e.dur_ms).sort((x, y) => y.dur_ms - x.dur_ms).slice(0, 3),
    unresolved: unresolvedVerificationFailures(events),
    aiCalls: a.aiCalls,
  };
}

function printSummary(d) {
  const p = (s = '') => console.log(s);
  p(`Session ${d.sid}${d.cwd ? '  (' + d.cwd + ')' : ''}`);
  p(`${d.start ? new Date(d.start).toISOString().replace('T', ' ').slice(0, 19) : '?'} → ${fmtTime(d.end)}  wall ${fmtDur(d.wall_ms)}`);
  p(`Turns ${d.turns} | model calls ${d.llm_calls} (${fmtDur(d.llm_ms)}, ${d.tokens.in} in / ${d.tokens.out} out tokens) | tool calls ${d.tool_calls} (${fmtDur(d.tool_ms)}) | failures ${d.failures.length} | subagents ${d.subagents.length}`);
  if (d.phases.length) {
    p('');
    p('Pipeline phases:');
    for (const ph of d.phases) p(`  ${fmtTime(ph.start)}  phase ${ph.phase}${ph.magnitude ? ' [' + ph.magnitude + ']' : ''}  ${fmtDur(ph.dur_ms)}`);
  }
  if (d.gates.length) {
    p('');
    p('Gates:');
    for (const g of d.gates) p(`  ${fmtTime(g.t)}  ${g.gate} = ${JSON.stringify(g.value)}`);
  }
  if (d.toolStats.length) {
    p('');
    const w = Math.max(14, ...d.toolStats.map((r) => r.tool.length)) + 2;
    p(`Tools:${' '.repeat(w - 4)}calls  fail   total     avg     p95     max`);
    for (const r of d.toolStats) {
      p(`  ${r.tool.padEnd(w)}${String(r.calls).padStart(5)}${String(r.fail).padStart(6)}${fmtDur(r.total_ms).padStart(8)}${fmtDur(r.avg_ms).padStart(8)}${fmtDur(r.p95_ms).padStart(8)}${fmtDur(r.max_ms).padStart(8)}`);
    }
  }
  if (d.aiCalls.length) {
    p('');
    p('Nested AI calls (headless CLIs):');
    for (const x of d.aiCalls) {
      const parts = [x.model, x.turns !== undefined ? `${x.turns} turns` : null, x.in_tok !== undefined ? `${x.in_tok} in / ${x.out_tok || 0} out tok` : null,
        x.cost_usd !== undefined ? `$${Number(x.cost_usd).toFixed(4)}` : null,
        x.tools ? 'tools ' + Object.entries(x.tools).map(([k, v]) => `${k}×${v}`).join(' ') : null,
        x.tool_errors ? `${x.tool_errors} tool errors` : null].filter(Boolean).join(', ');
      p(`  ${x.ok === false ? '✗' : '✓'} ${x.cli.padEnd(8)} ${fmtDur(x.dur_ms).padStart(7)}  ${parts}${x.error ? '  error: ' + clip(String(x.error).split('\n')[0], 120) : ''}`);
      if (!x.parsed) p(`      ⚠ internals not traced — ${x.structured ? 'structured output was not on stdout' : 'no structured output flag'}`);
      if (x.child_session) p(`      child trace: node dev-trace.js summary ${x.child_session}${d.childSessions && d.childSessions.includes(x.child_session) ? '' : '  (no trace file here: the child ran without the dev plugin or in another repo)'}`);
    }
  }
  if (d.workflow.length) {
    p('');
    p('Workflow agents (implement-and-review.js):');
    for (const w of d.workflow) p(`  ${w.ok ? '✓' : '✗'} ${String(w.phase || '').padEnd(10)} ${String(w.label).padEnd(28)} ${fmtDur(w.dur_ms)}${w.error ? '  ' + clip(w.error, 100) : ''}`);
  }
  if (d.failures.length) {
    p('');
    p('Failures:');
    for (const f of d.failures) {
      p(`  #${f.n} ${fmtTime(f.start || f.end)} ${f.tool} ${describeInput(f)}  (${fmtDur(f.dur_ms)})`);
      p(`      error: ${clip((f.error || '').split('\n').filter(Boolean).slice(0, 3).join(' | '), 220)}`);
      if (f.reasoning) p(`      why:   ${clip(f.reasoning.replace(/\s+/g, ' '), 220)}`);
    }
  }
  if (d.slowest.length) {
    p('');
    p('Slowest tool calls:');
    for (const c of d.slowest) p(`  #${c.n} ${fmtDur(c.dur_ms).padStart(7)}  ${c.tool} ${describeInput(c)}`);
  }
  if (d.slowestLlm.length) {
    p('Slowest model calls:');
    for (const e of d.slowestLlm) p(`  ${fmtDur(e.dur_ms).padStart(7)}  ${e.model || '?'}  out ${e.out_tok || 0} tok  ${fmtTime(e.t)}`);
  }
  if (d.unresolved.length) {
    p('');
    p('⚠ Verification commands that failed in the last turn and were never re-run green:');
    for (const f of d.unresolved) p(`  #${f.n} ${describeInput(f)}`);
  }
}

function printTimeline(events, opts) {
  const a = analyze(events);
  const items = [];
  for (const c of a.calls) items.push({ t: c.start || c.end, kind: 'tool', c });
  for (const e of a.llm) items.push({ t: e.start || e.t, kind: 'llm', e });
  for (const e of a.phases) items.push({ t: e.t, kind: 'phase', e });
  for (const e of a.gates) items.push({ t: e.t, kind: 'gate', e });
  for (const e of a.prompts) items.push({ t: e.t, kind: 'prompt', e });
  for (const e of a.workflow) items.push({ t: e.start || e.t, kind: 'wf', e });
  items.sort((x, y) => (x.t || 0) - (y.t || 0));
  const slowN = opts.slow ? new Set([...a.calls].filter((c) => c.dur_ms !== null).sort((x, y) => y.dur_ms - x.dur_ms).slice(0, opts.slow).map((c) => c.id)) : null;
  const t0 = a.first || 0;
  for (const it of items) {
    if (opts.failures && !(it.kind === 'tool' && it.c.ok === false)) continue;
    if (slowN && !(it.kind === 'tool' && slowN.has(it.c.id))) continue;
    const at = `+${fmtDur((it.t || t0) - t0)}`.padEnd(9);
    if (it.kind === 'tool') {
      const c = it.c;
      const mark = c.ok === false ? '✗' : c.ok === true ? '✓' : '…';
      console.log(`${at} ${mark} #${c.n} ${c.agent ? '[' + String(c.agent).slice(0, 8) + '] ' : ''}${c.tool} ${describeInput(c)}  ${fmtDur(c.dur_ms)}`);
      if (c.reasoning && !opts.brief) console.log(`            why: ${clip(c.reasoning.replace(/\s+/g, ' '), 200)}`);
      if (c.ok === false) console.log(`            error: ${clip((c.error || '').split('\n').filter(Boolean).slice(0, 4).join(' | '), 300)}`);
    } else if (it.kind === 'llm') {
      if (opts.failures || slowN) continue;
      const e = it.e;
      console.log(`${at} · model ${e.model || '?'} ${fmtDur(e.dur_ms)} in ${e.in_tok || 0}+${(e.cache_read || 0) + (e.cache_write || 0)}c out ${e.out_tok || 0}${e.tools && e.tools.length ? ' → ' + e.tools.length + ' tool call(s)' : ''}`);
    } else if (it.kind === 'phase') {
      console.log(`${at} ▶ phase ${it.e.phase}${it.e.magnitude ? ' [' + it.e.magnitude + ']' : ''} completed=${JSON.stringify(it.e.completed)}`);
    } else if (it.kind === 'gate') {
      console.log(`${at} ◆ gate ${it.e.gate} = ${JSON.stringify(it.e.value)}`);
    } else if (it.kind === 'prompt') {
      console.log(`${at} » prompt ${clip((it.e.prompt || '').replace(/\s+/g, ' '), 120)}`);
    } else if (it.kind === 'wf') {
      console.log(`${at} ${it.e.ok ? '✓' : '✗'} workflow ${it.e.phase || ''}/${it.e.label} ${fmtDur(it.e.dur_ms)}`);
    }
  }
}

function printFailures(events) {
  const a = analyze(events);
  const fails = a.calls.filter((c) => c.ok === false);
  if (!fails.length) { console.log('No failed tool calls recorded in this session.'); return; }
  for (const f of fails) {
    console.log(`#${f.n} ${f.tool} at ${new Date(f.start || f.end).toISOString()}  id=${f.id}${f.agent ? '  subagent=' + f.agent : ''}  duration=${fmtDur(f.dur_ms)}`);
    console.log(`  input:  ${describeInput(f) || JSON.stringify(f.input)}`);
    console.log(`  why:    ${f.reasoning ? f.reasoning.replace(/\s+/g, ' ') : '(no reasoning captured — model gave no text/thinking before this call)'}`);
    console.log('  error:');
    for (const l of String(f.error || '(no error text)').split('\n').slice(0, 25)) console.log('    ' + l);
    const later = a.calls.filter((c) => c.n > f.n && c.tool === f.tool && JSON.stringify(c.input) === JSON.stringify(f.input));
    if (later.length) console.log(`  retried: ${later.map((c) => `#${c.n} ${c.ok ? 'ok' : 'failed'}`).join(', ')}`);
    console.log('');
  }
}

/** OTLP/JSON export: POST to <collector>/v1/traces or import into Jaeger/Phoenix/Langfuse. */
function toOtlp(events, sid) {
  const a = analyze(events);
  const hex = (s, n) => crypto.createHash('sha256').update(String(s)).digest('hex').slice(0, n);
  const traceId = hex(sid, 32);
  const ns = (ms) => String(BigInt(Math.round(ms || 0)) * 1000000n);
  const attr = (o) => Object.entries(o).filter(([, v]) => v !== undefined && v !== null).map(([key, v]) => ({
    key, value: typeof v === 'number' ? (Number.isInteger(v) ? { intValue: String(v) } : { doubleValue: v }) : typeof v === 'boolean' ? { boolValue: v } : { stringValue: String(v) },
  }));
  const rootId = hex(sid + ':root', 16);
  const spans = [{
    traceId, spanId: rootId, name: 'dev.session', kind: 1,
    startTimeUnixNano: ns(a.first), endTimeUnixNano: ns(a.last), attributes: attr({ 'session.id': sid, 'code.cwd': a.cwd }),
  }];
  const phaseSpans = a.phases.map((p, i) => {
    const end = (a.phases[i + 1] || {}).t || a.last;
    const s = { traceId, spanId: hex(sid + ':phase:' + i, 16), parentSpanId: rootId, name: `dev.phase ${p.phase}`, kind: 1, startTimeUnixNano: ns(p.t), endTimeUnixNano: ns(end), attributes: attr({ 'dev.phase': String(p.phase), 'dev.magnitude': p.magnitude }) };
    s._start = p.t; s._end = end;
    return s;
  });
  spans.push(...phaseSpans);
  const parentAt = (t) => { const ph = phaseSpans.find((s) => t >= s._start && t < s._end); return ph ? ph.spanId : rootId; };
  const aiById = new Map(a.aiCalls.map((x) => [x.id, x]));
  for (const c of a.calls) {
    const start = c.start || c.end;
    const ai = aiById.get(c.id);
    const end = c.end || c.start;
    spans.push({
      traceId, spanId: hex(sid + ':' + c.id, 16), parentSpanId: parentAt(start), name: `execute_tool ${c.tool}`, kind: 1,
      startTimeUnixNano: ns(start), endTimeUnixNano: ns(end),
      attributes: attr({ 'gen_ai.operation.name': 'execute_tool', 'gen_ai.tool.name': c.tool, 'gen_ai.tool.call.id': c.id, 'dev.input': describeInput(c), 'dev.reasoning': c.reasoning ? clip(c.reasoning, 2000) : undefined, 'dev.subagent': c.agent, 'error.type': c.ok === false ? 'tool_error' : undefined,
        'dev.ai_cli': ai && ai.cli, 'gen_ai.request.model': ai && ai.model, 'gen_ai.usage.input_tokens': ai && ai.in_tok, 'gen_ai.usage.output_tokens': ai && ai.out_tok,
        'dev.ai_cli.turns': ai && ai.turns, 'dev.ai_cli.child_session': ai && ai.child_session, 'dev.ai_cli.tools': ai && ai.tools ? JSON.stringify(ai.tools) : undefined }),
      status: c.ok === false ? { code: 2, message: clip(c.error || 'failed', 500) } : { code: 1 },
    });
  }
  for (const e of a.llm) {
    const start = e.start || e.t;
    spans.push({
      traceId, spanId: hex(sid + ':llm:' + e.id, 16), parentSpanId: parentAt(start), name: `chat ${e.model || ''}`.trim(), kind: 3,
      startTimeUnixNano: ns(start), endTimeUnixNano: ns(e.t),
      attributes: attr({ 'gen_ai.operation.name': 'chat', 'gen_ai.request.model': e.model, 'gen_ai.usage.input_tokens': e.in_tok, 'gen_ai.usage.output_tokens': e.out_tok, 'gen_ai.usage.cache_read_input_tokens': e.cache_read, 'gen_ai.response.finish_reasons': e.stop, 'dev.subagent': e.agent }),
    });
  }
  for (const w of a.workflow) {
    spans.push({
      traceId, spanId: hex(sid + ':wf:' + w.parent + ':' + w.label + ':' + w.start, 16), parentSpanId: w.parent ? hex(sid + ':' + w.parent, 16) : rootId,
      name: `workflow.agent ${w.label}`, kind: 1, startTimeUnixNano: ns(w.start || w.t), endTimeUnixNano: ns(w.t),
      attributes: attr({ 'dev.workflow.phase': w.phase, 'dev.workflow.label': w.label }),
      status: w.ok ? { code: 1 } : { code: 2, message: clip(w.error || 'failed', 500) },
    });
  }
  for (const s of spans) { delete s._start; delete s._end; }
  return { resourceSpans: [{ resource: { attributes: attr({ 'service.name': 'claude-code-dev-pipeline' }) }, scopeSpans: [{ scope: { name: 'dev-trace', version: String(SCHEMA) }, spans }] }] };
}

function doctor(cwd) {
  const dir = traceDir(cwd);
  const all = listSessions(dir);
  const sid = process.env.CLAUDE_CODE_SESSION_ID;
  const own = sid ? all.find((s) => s.sid === safeId(sid)) : null;
  console.log(`trace dir:      ${dir}`);
  console.log(`recording:      ${process.env.DEV_TRACE === '0' ? 'DISABLED (DEV_TRACE=0)' : 'enabled'}  content=${contentMode()}  gate=${process.env.DEV_TRACE_GATE === '0' ? 'off' : 'on'}`);
  console.log(`sessions:       ${all.length}`);
  if (sid) console.log(`this session:   ${sid} → ${own ? 'trace file present, last write ' + fmtDur(Date.now() - own.mtime) + ' ago' : 'NO TRACE FILE'}`);
  const latest = own || all[0];
  if (latest) {
    const evs = readEvents(latest.file);
    const kinds = new Set(evs.map((e) => e.ev));
    console.log(`latest session: ${latest.sid}  events=${evs.length}`);
    const missing = ['tool.start', 'tool.end', 'llm'].filter((k) => !kinds.has(k));
    if (missing.length) console.log(`warning:        no ${missing.join(', ')} events yet (normal right after session start; otherwise the hooks are not registered)`);
  }
  const ok = process.env.DEV_TRACE !== '0' && (sid ? !!own : all.length > 0);
  console.log(ok ? 'status:         OK' : 'status:         NOT TRACING — is the dev plugin installed (claude plugin install), not just the copied skill?');
  return ok ? 0 : 1;
}

function cli(argv) {
  const [cmd, ...rest] = argv;
  const flags = new Set(rest.filter((a) => a.startsWith('--')));
  const pos = rest.filter((a) => !a.startsWith('--'));
  const cwd = process.cwd();
  const dir = traceDir(cwd);
  const pick = () => {
    const s = resolveSession(dir, pos[0]);
    if (!s) { console.error(`No trace sessions found in ${dir}`); process.exit(1); }
    return s;
  };
  switch (cmd) {
    case 'path': console.log(dir); return 0;
    case 'doctor': return doctor(cwd);
    case 'list': {
      const all = listSessions(dir).slice(0, Number(pos[0]) || 20);
      if (!all.length) { console.log(`No trace sessions in ${dir}`); return 0; }
      for (const s of all) {
        const d = summaryData(readEvents(s.file), s.sid);
        console.log(`${s.sid}  ${d.start ? new Date(d.start).toISOString().slice(0, 16).replace('T', ' ') : '?'}  wall ${fmtDur(d.wall_ms).padEnd(7)} turns ${String(d.turns).padEnd(3)} tools ${String(d.tool_calls).padEnd(4)} failures ${d.failures.length}${d.phases.length ? '  phases ' + d.phases.map((p) => p.phase).join('→') : ''}`);
      }
      return 0;
    }
    case 'summary': {
      const s = pick();
      const d = summaryData(readEvents(s.file), s.sid);
      d.childSessions = listSessions(dir).map((x) => x.sid);
      if (flags.has('--json')) console.log(JSON.stringify(d, null, 2)); else printSummary(d);
      return 0;
    }
    case 'show': {
      const s = pick();
      const slowIdx = rest.indexOf('--slow');
      printTimeline(readEvents(s.file), { failures: flags.has('--failures'), brief: flags.has('--brief'), slow: slowIdx >= 0 ? Number(rest[slowIdx + 1]) || 10 : 0 });
      return 0;
    }
    case 'failures': printFailures(readEvents(pick().file)); return 0;
    case 'export': {
      const s = pick();
      console.log(JSON.stringify(toOtlp(readEvents(s.file), s.sid)));
      return 0;
    }
    default:
      console.log('usage: dev-trace.js <list|summary|show|failures|export|doctor|path> [session|latest] [--json] [--failures] [--slow N]');
      return cmd ? 2 : 0;
  }
}

module.exports = {
  handleHook, analyze, readEvents, summaryData, toOtlp, redact, summarizeInput, traceDir, gitCommonDir,
  unresolvedVerificationFailures, ingestTranscript, findDevTrace, sessionFile, VERIFY_RE,
  detectAiCalls, parseAiOutput,
};

if (require.main === module) {
  const arg = process.argv[2];
  if (arg === 'hook') {
    let buf = '';
    const run = () => {
      let out = null;
      try {
        out = handleHook(JSON.parse(buf || '{}'));
      } catch (e) {
        if (process.env.DEV_TRACE_DEBUG) process.stderr.write(`dev-trace: ${e && e.stack}\n`);
      }
      if (out) process.stdout.write(JSON.stringify(out));
    };
    process.stdin.on('data', (c) => { buf += c; });
    process.stdin.on('end', run);
    process.stdin.on('error', run);
  } else if (arg === '--selftest') {
    const listTests = () => {
      const dir = path.join(__dirname, '..', '..', 'tests');
      if (!fs.existsSync(dir)) { console.error(`tests not found at ${dir} (selftest needs the repo checkout)`); process.exit(1); }
      return fs.readdirSync(dir).filter((n) => n.endsWith('.test.js')).map((n) => path.join(dir, n));
    };
    const r = require('child_process').spawnSync(process.execPath, ['--test', ...listTests()], { stdio: 'inherit' });
    process.exit(r.status === null ? 1 : r.status);
  } else {
    process.exitCode = cli(process.argv.slice(2));
  }
}
