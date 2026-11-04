#!/usr/bin/env node
/**
 * SessionStart hook — surfaces a /dev HANDOFF.md left by a previous session.
 *
 * Per-session by construction: this process is spawned by one Claude session,
 * reads that session's cwd from stdin, and its stdout lands only in that
 * session's context. Multiple terminals on different projects never interact.
 *
 * Silent (exit 0, no stdout) whenever there is nothing to report — this hook is
 * registered user-level, so it fires in every session including ~ and scratch dirs.
 */

const fs = require('fs');
const path = require('path');

const MAX_WALK_UP = 8;
const HEAD_BYTES = 4096;

/** Walk up from `start` looking for HANDOFF.md. Stops at a .git dir (repo root) or fs root. */
function findHandoff(start) {
  let dir = start;
  for (let i = 0; i < MAX_WALK_UP; i++) {
    const candidate = path.join(dir, 'HANDOFF.md');
    if (fs.existsSync(candidate)) return candidate;
    // .git present but no HANDOFF.md => we are at the repo root, stop climbing out of it
    if (fs.existsSync(path.join(dir, '.git'))) return null;
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
  return null;
}

function readHead(file) {
  const fd = fs.openSync(file, 'r');
  try {
    const buf = Buffer.alloc(HEAD_BYTES);
    const n = fs.readSync(fd, buf, 0, HEAD_BYTES, 0);
    return buf.toString('utf8', 0, n);
  } finally {
    fs.closeSync(fd);
  }
}

function field(text, name) {
  const m = text.match(new RegExp('^' + name + ':\\s*(.+)$', 'm'));
  return m ? m[1].trim() : null;
}

function parse(text) {
  const title = (text.match(/^#\s*HANDOFF\s*[—-]\s*(.+)$/m) || [])[1];
  const where = (text.match(/^##\s*Where we are\s*\n+(.+)$/m) || [])[1];
  const next = (text.match(/^##\s*Next step\s*\n+(?:\d+\.|[-*])\s*(.+)$/m) || [])[1];
  const sessionRaw = field(text, 'Session') || '';
  const pid = (sessionRaw.match(/pid\s+(\d+)/i) || [])[1];
  return {
    title: title ? title.trim() : null,
    status: (field(text, 'Status') || '').toUpperCase(),
    updated: field(text, 'Updated'),
    session: sessionRaw.replace(/\s*\(pid\s+\d+\)\s*/i, '').trim() || null,
    pid: pid ? Number(pid) : null,
    where: where ? where.trim() : null,
    next: next ? next.trim() : null,
  };
}

/**
 * True only when another Claude process is *currently alive* holding this handoff.
 * A dead pid means the handoff is a leftover from one of your own past sessions —
 * the common case after /clear — and must NOT produce a scary warning.
 */
function isForeignAndAlive(h, currentSession, currentPid) {
  if (!h.pid || h.pid === currentPid) return false;
  if (h.session && currentSession && h.session === currentSession) return false;
  // kill(pid, 0) probes existence. ESRCH = gone. EPERM = exists but owned by
  // another user, which still counts as alive.
  try { process.kill(h.pid, 0); return true; } catch (e) { return e.code === 'EPERM'; }
}

function buildMessage(file, h, currentSession, currentPid) {
  const lines = [
    `INTERRUPTED /dev PIPELINE DETECTED — do not start fresh work before reading it.`,
    `File: ${file}`,
    h.title ? `Task: ${h.title}` : null,
    `Status: ${h.status}${h.updated ? ` (updated ${h.updated})` : ''}`,
    h.where ? `Where: ${h.where}` : null,
    h.next ? `Next step: ${h.next}` : null,
  ];

  if (isForeignAndAlive(h, currentSession, currentPid)) {
    lines.push(
      `WARNING: another Claude process (pid ${h.pid}, session ${h.session || 'unknown'}) is ALIVE and owns this ` +
      `handoff — a second terminal is working in this same directory right now. Do NOT write HANDOFF.md or ` +
      `.dev-pipeline-state.json; two /dev pipelines would clobber each other. Tell the user and let them choose.`
    );
  }

  lines.push(
    `If the user's request relates to this task, invoke Skill(dev) — Phase 0 Step 0a will read the file and resume. ` +
    `If it is unrelated work, ignore this and do not modify the file.`
  );

  return lines.filter(Boolean).join('\n');
}

function emit(context) {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: { hookEventName: 'SessionStart', additionalContext: context },
  }));
}

function main(stdin) {
  let input = {};
  try { input = JSON.parse(stdin || '{}'); } catch { /* malformed stdin: fall back to cwd */ }

  const cwd = input.cwd || process.cwd();
  const file = findHandoff(cwd);
  if (!file) return; // silent

  const h = parse(readHead(file));
  if (h.status !== 'IN PROGRESS' && h.status !== 'PAUSED') return; // DONE or unparseable: not worth the tokens

  const session = input.session_id || process.env.CLAUDE_CODE_SESSION_ID || null;
  const pid = Number(process.env.CLAUDE_PID) || process.ppid;
  emit(buildMessage(file, h, session, pid));
}

function selftest() {
  const assert = require('assert');
  const os = require('os');

  const doc = [
    '# HANDOFF — add retry to payment webhook',
    '',
    'Status: PAUSED',
    'Updated: 2026-08-03T10:00:00Z',
    'Session: abc-123 (pid 999999)',
    '',
    '## Where we are',
    'Phase 6: Verify — 2 tests failing',
    '',
    '## Next step',
    '1. Fix the timeout assertion in webhook.test.ts',
    '2. Re-run suite',
  ].join('\n');

  const h = parse(doc);
  assert.strictEqual(h.title, 'add retry to payment webhook');
  assert.strictEqual(h.status, 'PAUSED');
  assert.strictEqual(h.session, 'abc-123');
  assert.strictEqual(h.pid, 999999);
  assert.strictEqual(h.where, 'Phase 6: Verify — 2 tests failing');
  assert.strictEqual(h.next, 'Fix the timeout assertion in webhook.test.ts');
  assert.strictEqual(parse('Session: abc-123').pid, null, 'pid is optional');

  // DONE and missing-status docs must stay silent
  assert.strictEqual(parse('# HANDOFF — x\nStatus: DONE\n').status, 'DONE');
  assert.strictEqual(parse('no header at all').status, '');

  // Collision warning fires ONLY for a foreign pid that is actually alive.
  const alive = { ...h, pid: process.pid, session: 'other-999' };
  const dead = { ...h, pid: 999999, session: 'other-999' }; // unlikely to exist
  assert.ok(isForeignAndAlive(alive, 'me', process.ppid), 'live foreign process must warn');
  assert.ok(!isForeignAndAlive(dead, 'me', process.ppid), 'dead pid = own past session, must stay quiet');
  assert.ok(!isForeignAndAlive({ ...alive, session: 'me' }, 'me', process.ppid), 'same session never warns');
  assert.ok(!isForeignAndAlive({ ...alive, pid: process.ppid }, 'me', process.ppid), 'same pid never warns');
  assert.ok(isForeignAndAlive({ ...alive, pid: 1 }, 'me', process.ppid), 'EPERM (pid 1) means alive, not dead');
  assert.ok(buildMessage('/x/H.md', alive, 'me', process.ppid).includes('is ALIVE'));
  assert.ok(!buildMessage('/x/H.md', dead, 'me', process.ppid).includes('is ALIVE'));

  // walk-up finds the file, and stops at a .git boundary
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'handoff-'));
  const deep = path.join(root, 'repo', 'src', 'a', 'b');
  fs.mkdirSync(deep, { recursive: true });
  fs.mkdirSync(path.join(root, 'repo', '.git'));
  assert.strictEqual(findHandoff(deep), null, 'stops at repo root when no handoff');
  fs.writeFileSync(path.join(root, 'HANDOFF.md'), doc);
  assert.strictEqual(findHandoff(deep), null, 'must not escape the repo to an outer handoff');
  fs.writeFileSync(path.join(root, 'repo', 'HANDOFF.md'), doc);
  assert.strictEqual(findHandoff(deep), path.join(root, 'repo', 'HANDOFF.md'));
  fs.rmSync(root, { recursive: true, force: true });

  console.log('ok — all self-checks passed');
}

if (process.argv[2] === '--selftest') {
  selftest();
} else {
  let buf = '';
  process.stdin.on('data', (c) => { buf += c; });
  process.stdin.on('end', () => { try { main(buf); } catch { /* never break session start */ } });
  // no stdin attached (manual run): proceed with cwd
  process.stdin.on('error', () => { try { main(''); } catch {} });
}
