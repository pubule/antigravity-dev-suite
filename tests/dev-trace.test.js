'use strict';
// node --test tests/
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const SCRIPT = path.join(__dirname, '..', 'skills', 'dev', 'dev-trace.js');
const T = require(SCRIPT);

function sandbox() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'dev-trace-'));
  const repo = path.join(root, 'repo');
  fs.mkdirSync(path.join(repo, '.git'), { recursive: true });
  const traces = path.join(root, 'traces');
  const transcript = path.join(root, 'transcript.jsonl');
  fs.writeFileSync(transcript, '');
  return { root, repo, traces, transcript };
}

function hook(sb, event, extra = {}, env = {}) {
  const input = { session_id: 'sess-1', cwd: sb.repo, transcript_path: sb.transcript, hook_event_name: event, ...extra };
  const r = spawnSync(process.execPath, [SCRIPT, 'hook'], {
    input: JSON.stringify(input),
    env: { ...process.env, DEV_TRACE_DIR: sb.traces, DEV_TRACE_DEBUG: '1', ...env },
    encoding: 'utf8',
  });
  assert.strictEqual(r.status, 0, r.stderr);
  assert.strictEqual(r.stderr, '', 'hook must not print errors');
  return r.stdout ? JSON.parse(r.stdout) : null;
}

function cli(sb, args) {
  const r = spawnSync(process.execPath, [SCRIPT, ...args], {
    cwd: sb.repo, env: { ...process.env, DEV_TRACE_DIR: sb.traces, CLAUDE_CODE_SESSION_ID: '' }, encoding: 'utf8',
  });
  return r;
}

const line = (o) => JSON.stringify(o) + '\n';

function writeTurn(sb, { toolId, command, isError, errorText, thinking }) {
  fs.appendFileSync(sb.transcript,
    line({ type: 'user', timestamp: '2026-11-05T10:00:00.000Z', message: { role: 'user', content: 'run the tests' } }) +
    line({ type: 'assistant', timestamp: '2026-11-05T10:00:01.000Z', message: { id: 'msg_1', model: 'claude-test', role: 'assistant', content: [{ type: 'thinking', thinking }], usage: { input_tokens: 100, output_tokens: 20 } } }) +
    line({ type: 'assistant', timestamp: '2026-11-05T10:00:03.000Z', message: { id: 'msg_1', model: 'claude-test', role: 'assistant', content: [{ type: 'tool_use', id: toolId, name: 'Bash', input: { command } }], usage: { input_tokens: 100, output_tokens: 60 }, stop_reason: 'tool_use' } }) +
    line({ type: 'user', timestamp: '2026-11-05T10:00:09.000Z', message: { role: 'user', content: [{ type: 'tool_result', tool_use_id: toolId, is_error: isError, content: errorText || 'ok' }] } }),
  );
}

test('redaction removes common secret shapes', () => {
  const s = T.redact('curl -H "Authorization: Bearer abcdefghijklmnop" https://u:hunter2@host/x?api_key=XYZ123 sk-ant-api03-aaaaaaaaaaaaaaaa ghp_abcdefghijklmnopqrstuvwxyz password=s3cr3t');
  for (const leak of ['abcdefghijklmnop', 'hunter2', 'XYZ123', 'sk-ant-api03', 'ghp_abc', 's3cr3t']) assert.ok(!s.includes(leak), `${leak} leaked: ${s}`);
});

test('input summaries never store file contents', () => {
  const w = T.summarizeInput('Write', { file_path: '/a/b.js', content: 'const secret = 1\n'.repeat(100) });
  assert.deepStrictEqual(Object.keys(w).sort(), ['bytes', 'file_path']);
  const e = T.summarizeInput('Edit', { file_path: '/a/b.js', old_string: 'abc', new_string: 'abcd' });
  assert.strictEqual(e.old_len, 3);
  assert.ok(!JSON.stringify(e).includes('abcd'));
});

test('trace dir lives in the git common dir, shared by linked worktrees', () => {
  const sb = sandbox();
  const common = path.join(sb.repo, '.git');
  const wtGit = path.join(common, 'worktrees', 'feat');
  fs.mkdirSync(wtGit, { recursive: true });
  fs.writeFileSync(path.join(wtGit, 'commondir'), '../..\n');
  const wt = path.join(sb.root, 'wt-feat', 'src');
  fs.mkdirSync(wt, { recursive: true });
  fs.writeFileSync(path.join(sb.root, 'wt-feat', '.git'), `gitdir: ${wtGit}\n`);
  assert.strictEqual(T.gitCommonDir(path.join(sb.repo)), common);
  assert.strictEqual(T.gitCommonDir(wt), common);
  const saved = process.env.DEV_TRACE_DIR;
  delete process.env.DEV_TRACE_DIR;
  try { assert.strictEqual(T.traceDir(wt), path.join(common, 'dev-trace')); } finally { if (saved !== undefined) process.env.DEV_TRACE_DIR = saved; }
});

test('records tool calls, latency, reasoning and failures; Stop blocks once on an unresolved failing test run', () => {
  const sb = sandbox();
  fs.writeFileSync(path.join(sb.repo, '.dev-pipeline-state.json'), JSON.stringify({ task: 'x', magnitude: 'standard', currentPhase: 6, completedPhases: [0, 1, 3, 4, 5] }));

  hook(sb, 'SessionStart', { source: 'startup' });
  hook(sb, 'UserPromptSubmit', { prompt: 'run the tests, token=abc123secret' });
  hook(sb, 'PreToolUse', { tool_name: 'Bash', tool_use_id: 'toolu_1', tool_input: { command: 'npm test' } });
  hook(sb, 'PostToolUseFailure', { tool_name: 'Bash', tool_use_id: 'toolu_1', tool_input: { command: 'npm test' }, error: 'Exit code 1\nFAIL src/a.test.js\n  expected 2 received 3' });
  writeTurn(sb, { toolId: 'toolu_1', command: 'npm test', isError: true, errorText: 'Exit code 1\nFAIL src/a.test.js', thinking: 'I will run the unit tests to check the retry logic.' });

  const block = hook(sb, 'Stop', { stop_hook_active: false });
  assert.ok(block, 'expected a block');
  assert.strictEqual(block.decision, 'block');
  assert.match(block.reason, /npm test/);
  assert.match(block.reason, /FAIL|Exit code 1/);

  assert.strictEqual(hook(sb, 'Stop', { stop_hook_active: true }), null, 'second stop in the same turn must pass (no loops)');

  const events = T.readEvents(path.join(sb.traces, 'sess-1.jsonl'));
  const a = T.analyze(events);
  const c = a.calls.find((x) => x.id === 'toolu_1');
  assert.strictEqual(c.ok, false);
  assert.ok(c.dur_ms !== null && c.dur_ms >= 0, 'tool latency computed');
  assert.match(c.reasoning, /retry logic/, 'reasoning attached to the tool call');
  const llm = a.llm.find((e) => e.id === 'msg_1');
  assert.strictEqual(llm.dur_ms, 3000, 'model latency = previous user entry → last chunk');
  assert.strictEqual(llm.out_tok, 60);
  assert.ok(!fs.readFileSync(path.join(sb.traces, 'sess-1.jsonl'), 'utf8').includes('abc123secret'), 'prompt redacted');

  // transcript is read incrementally: a second Stop does not duplicate llm events
  hook(sb, 'Stop', { stop_hook_active: true });
  assert.strictEqual(T.analyze(T.readEvents(path.join(sb.traces, 'sess-1.jsonl'))).llm.length, 1);
});

test('a later green re-run of the same command resolves the failure', () => {
  const sb = sandbox();
  fs.writeFileSync(path.join(sb.repo, '.dev-pipeline-state.json'), '{"currentPhase":6}');
  hook(sb, 'UserPromptSubmit', { prompt: 'go' });
  hook(sb, 'PreToolUse', { tool_name: 'Bash', tool_use_id: 'a', tool_input: { command: 'pytest -q' } });
  hook(sb, 'PostToolUseFailure', { tool_name: 'Bash', tool_use_id: 'a', tool_input: { command: 'pytest -q' }, error: 'Exit code 1' });
  hook(sb, 'PreToolUse', { tool_name: 'Bash', tool_use_id: 'b', tool_input: { command: 'pytest  -q' } });
  hook(sb, 'PostToolUse', { tool_name: 'Bash', tool_use_id: 'b', tool_input: { command: 'pytest  -q' }, tool_response: { stdout: '3 passed', stderr: '' } });
  assert.strictEqual(hook(sb, 'Stop', { stop_hook_active: false }), null);
});

test('no block outside an active /dev pipeline, nor for non-verification commands', () => {
  const sb = sandbox();
  hook(sb, 'UserPromptSubmit', { prompt: 'go' });
  hook(sb, 'PreToolUse', { tool_name: 'Bash', tool_use_id: 'a', tool_input: { command: 'npm test' } });
  hook(sb, 'PostToolUseFailure', { tool_name: 'Bash', tool_use_id: 'a', tool_input: { command: 'npm test' }, error: 'Exit code 1' });
  assert.strictEqual(hook(sb, 'Stop', {}), null, 'no pipeline state → no gate');

  fs.writeFileSync(path.join(sb.repo, '.dev-pipeline-state.json'), '{"currentPhase":6}');
  hook(sb, 'UserPromptSubmit', { prompt: 'next' });
  hook(sb, 'PreToolUse', { tool_name: 'Bash', tool_use_id: 'c', tool_input: { command: 'ls missing-dir' } });
  hook(sb, 'PostToolUseFailure', { tool_name: 'Bash', tool_use_id: 'c', tool_input: { command: 'ls missing-dir' }, error: 'Exit code 2' });
  assert.strictEqual(hook(sb, 'Stop', {}), null, 'only verification commands gate; the earlier turn is out of scope');
  assert.strictEqual(hook(sb, 'Stop', {}, { DEV_TRACE_GATE: '0' }), null);
});

test('pipeline phases and gate verdicts are recorded from state file writes', () => {
  const sb = sandbox();
  const sf = path.join(sb.repo, '.dev-pipeline-state.json');
  fs.writeFileSync(sf, JSON.stringify({ currentPhase: 0, completedPhases: [0], magnitude: 'complex', gates: {} }));
  hook(sb, 'PostToolUse', { tool_name: 'Write', tool_use_id: 'w1', tool_input: { file_path: sf, content: '{}' }, tool_response: {} });
  fs.writeFileSync(sf, JSON.stringify({ currentPhase: 2, completedPhases: [0, 1, 2], magnitude: 'complex', gates: { designCouncilGO: true } }));
  hook(sb, 'PostToolUse', { tool_name: 'Edit', tool_use_id: 'w2', tool_input: { file_path: sf, old_string: 'a', new_string: 'b' }, tool_response: {} });
  hook(sb, 'PostToolUse', { tool_name: 'Edit', tool_use_id: 'w3', tool_input: { file_path: sf, old_string: 'a', new_string: 'b' }, tool_response: {} });
  const a = T.analyze(T.readEvents(path.join(sb.traces, 'sess-1.jsonl')));
  assert.deepStrictEqual(a.phases.map((p) => p.phase), [0, 2], 'unchanged state does not emit duplicates');
  assert.deepStrictEqual(a.gates.map((g) => [g.gate, g.value]), [['designCouncilGO', true]]);
});

test('Workflow devTrace spans are ingested from the tool response', () => {
  const sb = sandbox();
  const result = { status: 'SUCCESS', devTrace: { version: 1, spans: [
    { label: 'impl:T1', phase: 'Implement', start: 1000, end: 61000, ok: true },
    { label: 'verify-0', phase: 'Verify', start: 61000, end: 90000, ok: false, error: 'reported failure: a.test.js' },
  ] } };
  hook(sb, 'PreToolUse', { tool_name: 'Workflow', tool_use_id: 'wf', tool_input: { scriptPath: '/x/implement-and-review.js', args: {} } });
  hook(sb, 'PostToolUse', { tool_name: 'Workflow', tool_use_id: 'wf', tool_input: {}, tool_response: { content: [{ type: 'text', text: JSON.stringify(result) }] } });
  const a = T.analyze(T.readEvents(path.join(sb.traces, 'sess-1.jsonl')));
  assert.strictEqual(a.workflow.length, 2);
  assert.strictEqual(a.workflow[0].dur_ms, 60000);
  assert.strictEqual(a.workflow[1].ok, false);
});

test('CLI: summary, show, failures, export, doctor', () => {
  const sb = sandbox();
  fs.writeFileSync(path.join(sb.repo, '.dev-pipeline-state.json'), '{"currentPhase":6}');
  hook(sb, 'SessionStart', { source: 'startup' });
  hook(sb, 'UserPromptSubmit', { prompt: 'go' });
  hook(sb, 'PreToolUse', { tool_name: 'Read', tool_use_id: 'r1', tool_input: { file_path: '/repo/a.js' } });
  hook(sb, 'PostToolUse', { tool_name: 'Read', tool_use_id: 'r1', tool_input: { file_path: '/repo/a.js' }, tool_response: { file: {} } });
  hook(sb, 'PreToolUse', { tool_name: 'Bash', tool_use_id: 'toolu_1', tool_input: { command: 'npm test' } });
  hook(sb, 'PostToolUseFailure', { tool_name: 'Bash', tool_use_id: 'toolu_1', tool_input: { command: 'npm test' }, error: 'Exit code 1\nAssertionError: boom' });
  writeTurn(sb, { toolId: 'toolu_1', command: 'npm test', isError: true, errorText: 'Exit code 1', thinking: 'Checking whether the fix works.' });
  hook(sb, 'Stop', { stop_hook_active: true });

  let r = cli(sb, ['summary']);
  assert.strictEqual(r.status, 0, r.stderr);
  assert.match(r.stdout, /Failures:/);
  assert.match(r.stdout, /AssertionError: boom/);
  assert.match(r.stdout, /why:\s+Checking whether the fix works/);
  assert.match(r.stdout, /Bash\s+1\s+1/);

  r = cli(sb, ['summary', 'sess-1', '--json']);
  const d = JSON.parse(r.stdout);
  assert.strictEqual(d.tool_calls, 2);
  assert.strictEqual(d.failures.length, 1);
  assert.strictEqual(d.unresolved.length, 1);

  r = cli(sb, ['show', '--failures']);
  assert.match(r.stdout, /✗ #2 Bash `npm test`/);
  assert.doesNotMatch(r.stdout, /Read/);

  r = cli(sb, ['failures']);
  assert.match(r.stdout, /why:\s+Checking whether the fix works/);

  r = cli(sb, ['export']);
  const otlp = JSON.parse(r.stdout);
  const spans = otlp.resourceSpans[0].scopeSpans[0].spans;
  assert.ok(spans.some((s) => s.name === 'execute_tool Bash' && s.status.code === 2));
  assert.ok(spans.some((s) => s.name === 'chat claude-test'));
  assert.ok(spans.every((s) => /^[0-9a-f]{32}$/.test(s.traceId) && /^[0-9a-f]{16}$/.test(s.spanId)));

  r = cli(sb, ['doctor']);
  assert.strictEqual(r.status, 0, r.stdout);
  assert.match(r.stdout, /status:\s+OK/);

  r = cli(sb, ['list']);
  assert.match(r.stdout, /sess-1/);
});

test('DEV_TRACE=0 records nothing', () => {
  const sb = sandbox();
  hook(sb, 'PreToolUse', { tool_name: 'Bash', tool_use_id: 'x', tool_input: { command: 'ls' } }, { DEV_TRACE: '0' });
  assert.ok(!fs.existsSync(path.join(sb.traces, 'sess-1.jsonl')));
});

test('malformed hook input never breaks the session', () => {
  const r = spawnSync(process.execPath, [SCRIPT, 'hook'], { input: '{not json', encoding: 'utf8', env: { ...process.env, DEV_TRACE_DIR: os.tmpdir() } });
  assert.strictEqual(r.status, 0);
  assert.strictEqual(r.stdout, '');
});
