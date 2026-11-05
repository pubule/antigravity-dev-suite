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

test('detects headless AI CLI calls and their output format', () => {
  const d = (c) => T.detectAiCalls(c).map((x) => `${x.cli}:${x.structured ? x.output_format : 'raw'}`);
  assert.deepStrictEqual(d('claude -p "fix it" --output-format stream-json --verbose'), ['claude:stream-json']);
  assert.deepStrictEqual(d('cd app && gemini -p "summarize" -o json | jq .response'), ['gemini:json']);
  assert.deepStrictEqual(d('agy -p "refactor"'), ['agy:raw']);
  assert.deepStrictEqual(d('agy --prompt "refactor" --output-format stream-json --print-timeout 15m'), ['agy:stream-json']);
  assert.strictEqual(T.detectAiCalls('agy -p x --output-format json')[0].timeout, false);
  assert.strictEqual(T.detectAiCalls('agy -p x --output-format json --print-timeout 10m')[0].timeout, true);
  assert.strictEqual(T.detectAiCalls('timeout 600 agy -p x --output-format json')[0].timeout, true);
  assert.deepStrictEqual(d('FOO=1 timeout 60 npx @anthropic-ai/claude-code --print hi'), ['claude:raw']);
  assert.deepStrictEqual(d('codex exec --json "do it"'), ['codex:json']);
  assert.deepStrictEqual(d('claude --version; gemini --help; echo claude -p'), []);
  assert.strictEqual(T.detectAiCalls('claude -p x --model sonnet')[0].model, 'sonnet');
});

test('parses Claude json, Claude stream-json and Gemini json results', () => {
  const c = T.parseAiOutput(JSON.stringify({ type: 'result', subtype: 'success', is_error: false, duration_api_ms: 4000, num_turns: 3, session_id: 'child-1', total_cost_usd: 0.012, usage: { input_tokens: 10, cache_read_input_tokens: 90, output_tokens: 50 } }));
  assert.strictEqual(c.child_session, 'child-1');
  assert.strictEqual(c.turns, 3);
  assert.strictEqual(c.in_tok, 100);
  assert.strictEqual(c.error, undefined);

  const stream = [
    { type: 'system', subtype: 'init', session_id: 'child-2' },
    { type: 'assistant', message: { content: [{ type: 'tool_use', name: 'Bash', id: 't1' }] } },
    { type: 'user', message: { content: [{ type: 'tool_result', tool_use_id: 't1', is_error: true }] } },
    { type: 'assistant', message: { content: [{ type: 'tool_use', name: 'Edit', id: 't2' }] } },
    { type: 'result', subtype: 'error_max_turns', is_error: true, num_turns: 10, session_id: 'child-2' },
  ].map((x) => JSON.stringify(x)).join('\n');
  const s = T.parseAiOutput(stream);
  assert.deepStrictEqual(s.tools, { Bash: 1, Edit: 1 });
  assert.strictEqual(s.tool_errors, 1);
  assert.match(s.error, /error_max_turns/);

  const g = T.parseAiOutput(JSON.stringify({ response: 'ok', stats: { models: { 'gemini-2.5-pro': { api: { totalRequests: 2, totalErrors: 0, totalLatencyMs: 3100 }, tokens: { prompt: 500, candidates: 80 } } }, tools: { totalCalls: 3, totalFail: 1, byName: { read_file: { count: 2 }, run_shell_command: { count: 1 } } } } }));
  assert.strictEqual(g.model, 'gemini-2.5-pro');
  assert.strictEqual(g.in_tok, 500);
  assert.strictEqual(g.tool_errors, 1);
  assert.deepStrictEqual(g.tools, { read_file: 2, run_shell_command: 1 });

  // Antigravity CLI (https://antigravity.google/docs/cli/headless/)
  const aj = T.parseAiOutput(JSON.stringify({ conversation_id: 'conv-1', status: 'SUCCESS', response: 'x', duration_seconds: 7.16, num_turns: 1, usage: { input_tokens: 10415, output_tokens: 657, thinking_tokens: 616, cache_read_tokens: 8113, total_tokens: 11072 } }));
  assert.strictEqual(aj.child_session, 'conv-1');
  assert.strictEqual(aj.api_ms, 7160);
  assert.strictEqual(aj.error, undefined);
  const as = T.parseAiOutput([
    { event: 'init', conversation_id: 'conv-2', init: { cwd: '/p', tools: ['run_command'], model: 'gemini-3-pro' } },
    { event: 'step_update', step_update: { conversation_id: 'conv-2', step_index: 2, state: 'DONE', step_type: 'tool', tool_name: 'run_command', tool_info: { name: 'run_command', parameters: {}, error: { type: 'x', message: 'boom' } } } },
    { event: 'step_update', step_update: { conversation_id: 'conv-2', step_index: 3, state: 'DONE', step_type: 'tool', tool_name: 'write_to_file', tool_info: { name: 'write_to_file' } } },
    { event: 'result', result: { conversation_id: 'conv-2', status: 'ERROR', error: 'invalid model selection', response: '', duration_seconds: 0, num_turns: 0, usage: {} } },
  ].map((x) => JSON.stringify(x)).join('\n'));
  assert.deepStrictEqual(as.tools, { run_command: 1, write_to_file: 1 });
  assert.strictEqual(as.tool_errors, 1);
  assert.strictEqual(as.model, 'gemini-3-pro');
  assert.match(as.error, /status ERROR: invalid model selection/);

  // Codex exec --json
  const cx = T.parseAiOutput([
    { type: 'thread.started', thread_id: 'th-1' },
    { type: 'item.completed', item: { id: 'item_0', type: 'command_execution', command: 'bash -lc ls', status: 'completed' } },
    { type: 'turn.completed', usage: { input_tokens: 24763, cached_input_tokens: 24448, output_tokens: 122 } },
  ].map((x) => JSON.stringify(x)).join('\n'));
  assert.strictEqual(cx.child_session, 'th-1');
  assert.deepStrictEqual(cx.tools, { shell: 1 });
  assert.strictEqual(cx.out_tok, 122);

  assert.strictEqual(T.parseAiOutput('just some text'), null);
});

test('nested AI calls are recorded, linked to the child trace, and unstructured ones denied inside a pipeline', () => {
  const sb = sandbox();
  // outside a pipeline: never denied, but still traced
  const cmd = 'gemini -p "review the diff"';
  assert.strictEqual(hook(sb, 'PreToolUse', { tool_name: 'Bash', tool_use_id: 'g0', tool_input: { command: cmd } }), null);

  fs.writeFileSync(path.join(sb.repo, '.dev-pipeline-state.json'), '{"currentPhase":5}');
  const deny = hook(sb, 'PreToolUse', { tool_name: 'Bash', tool_use_id: 'g1', tool_input: { command: cmd } });
  assert.strictEqual(deny.hookSpecificOutput.permissionDecision, 'deny');
  assert.match(deny.hookSpecificOutput.permissionDecisionReason, /--output-format json/);
  const agyDeny = hook(sb, 'PreToolUse', { tool_name: 'Bash', tool_use_id: 'a0', tool_input: { command: 'agy -p "x"' } });
  assert.match(agyDeny.hookSpecificOutput.permissionDecisionReason, /agy --output-format stream-json/);
  assert.strictEqual(hook(sb, 'PreToolUse', { tool_name: 'Bash', tool_use_id: 'a1', tool_input: { command: 'aider -m "x"' } }), null, 'CLIs without a JSON mode: traced, not denied');
  assert.strictEqual(hook(sb, 'PreToolUse', { tool_name: 'Bash', tool_use_id: 'g1', tool_input: { command: cmd } }, { DEV_TRACE_GATE: '0' }), null);

  const ccmd = 'claude -p "write tests" --output-format json';
  assert.strictEqual(hook(sb, 'PreToolUse', { tool_name: 'Bash', tool_use_id: 'c1', tool_input: { command: ccmd } }), null);
  hook(sb, 'PostToolUse', { tool_name: 'Bash', tool_use_id: 'c1', tool_input: { command: ccmd }, tool_response: { stdout: JSON.stringify({ type: 'result', subtype: 'success', num_turns: 4, session_id: 'child-9', total_cost_usd: 0.02, usage: { input_tokens: 100, output_tokens: 7 } }), stderr: '' } });
  hook(sb, 'PostToolUse', { tool_name: 'Bash', tool_use_id: 'a1', tool_input: { command: 'aider -m "x"' }, tool_response: { stdout: 'done', stderr: '' } });
  // the child session wrote its own trace into the same directory
  hook(sb, 'SessionStart', { session_id: 'child-9', source: 'startup' });

  const a = T.analyze(T.readEvents(path.join(sb.traces, 'sess-1.jsonl')));
  const c = a.aiCalls.find((x) => x.id === 'c1');
  assert.strictEqual(c.child_session, 'child-9');
  assert.strictEqual(c.turns, 4);
  assert.ok(c.dur_ms >= 0);
  assert.strictEqual(a.aiCalls.find((x) => x.id === 'a1').parsed, false);

  const r = cli(sb, ['summary', 'sess-1']);
  assert.match(r.stdout, /Nested AI calls/);
  assert.match(r.stdout, /claude .*4 turns/);
  assert.match(r.stdout, /child trace: node dev-trace.js summary child-9\n/);
  assert.match(r.stdout, /aider[\s\S]*internals not traced/);
});
