'use strict';
// Runs skills/dev/implement-and-review.js against a mocked Workflow runtime
// (agent / parallel / phase / log) to check control flow and the devTrace spans.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');

const SRC = fs.readFileSync(path.join(__dirname, '..', 'skills', 'dev', 'implement-and-review.js'), 'utf8')
  .replace(/^export const meta\s*=/m, 'const meta =');
const AsyncFunction = Object.getPrototypeOf(async () => {}).constructor;

async function run(responder, args = {}) {
  const calls = [];
  const phases = [];
  const agent = async (prompt, opts = {}) => { calls.push(opts.label); return responder(opts.label || '', prompt); };
  const parallel = async (thunks) => Promise.all(thunks.map((t) => t().catch(() => null)));
  const fn = new AsyncFunction('agent', 'parallel', 'phase', 'log', 'args', SRC);
  const result = await fn(agent, parallel, (p) => phases.push(p), () => {}, { planPath: 'plan.md', tddRequired: true, auditTriggers: {}, ...args });
  return { result, calls, phases };
}

test('happy path returns devTrace with one span per agent call', async () => {
  const { result, calls, phases } = await run((label) => {
    if (label === 'parse-plan') return { tasks: [{ id: 'T1', description: 'a' }, { id: 'T2', description: 'b' }] };
    if (label === 'integrator') return { merged: true, conflicts: [] };
    if (label.startsWith('verify')) return { passed: true };
    if (label === 'maestro-review') return { findings: [] };
    return {};
  });
  assert.strictEqual(result.status, 'SUCCESS');
  assert.deepStrictEqual(phases, ['Implement', 'Integrate', 'Verify', 'Review', 'Audit']);
  assert.strictEqual(result.devTrace.spans.length, calls.length);
  for (const s of result.devTrace.spans) {
    assert.ok(typeof s.start === 'number' && s.end >= s.start, `span ${s.label} timed`);
    assert.ok(s.phase, `span ${s.label} has a phase`);
  }
  assert.strictEqual(result.devTrace.spans.find((s) => s.label === 'impl:T1').phase, 'Implement');
});

test('verify failure after 3 cycles returns FAILED with failures and failing spans', async () => {
  const { result } = await run((label) => {
    if (label === 'parse-plan') return { tasks: [{ id: 'T1', description: 'a' }] };
    if (label === 'integrator') return { merged: true };
    if (label.startsWith('verify')) return { passed: false, failures: ['a.test.js: expected 2 got 3'] };
    return {};
  });
  assert.strictEqual(result.status, 'FAILED');
  assert.deepStrictEqual(result.lastFailures, ['a.test.js: expected 2 got 3']);
  const verifies = result.devTrace.spans.filter((s) => s.label.startsWith('verify'));
  assert.strictEqual(verifies.length, 3);
  assert.ok(verifies.every((s) => /expected 2 got 3/.test(s.error)));
});

test('an agent that throws is recorded as a failed span', async () => {
  const { result } = await run((label) => {
    if (label === 'parse-plan') return { tasks: [{ id: 'T1', description: 'a' }, { id: 'T2', description: 'b' }] };
    if (label === 'impl:T2') throw new Error('worktree creation failed');
    if (label === 'integrator') return { merged: true };
    if (label.startsWith('verify')) return { passed: true };
    if (label === 'maestro-review') return { findings: [] };
    return {};
  });
  assert.strictEqual(result.implemented, 1);
  const s = result.devTrace.spans.find((x) => x.label === 'impl:T2');
  assert.strictEqual(s.ok, false);
  assert.match(s.error, /worktree creation failed/);
});
