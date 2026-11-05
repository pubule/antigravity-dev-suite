export const meta = {
  name: 'dev-implement-review',
  description: 'Parallel implementation, verification with debug loops, adversarial code review, and conditional audits',
  phases: [
    { title: 'Implement', detail: 'TDD + parallel task execution with worktree isolation' },
    { title: 'Integrate', detail: 'Merge parallel worktrees, resolve conflicts' },
    { title: 'Verify', detail: 'Full test suite + regression check (max 3 debug cycles)' },
    { title: 'Review', detail: 'Parallel code reviews + adversarial verify + graduated remediation' },
    { title: 'Audit', detail: 'Parallel conditional audits + remediation' },
  ],
}

const FINDINGS_SCHEMA = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          severity: { type: 'string', enum: ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'] },
          file: { type: 'string' },
          description: { type: 'string' }
        },
        required: ['severity', 'description']
      }
    }
  },
  required: ['findings']
}

const PASS_FAIL_SCHEMA = {
  type: 'object',
  properties: {
    passed: { type: 'boolean' },
    totalTests: { type: 'number' },
    failures: { type: 'array', items: { type: 'string' } }
  },
  required: ['passed']
}

const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    refuted: { type: 'boolean' },
    reasoning: { type: 'string' }
  },
  required: ['refuted']
}

// ─── Tracing ─────────────────────────────────────────────────────────
// Every agent call is timed and its outcome recorded. The spans travel back in the
// result as `devTrace`; the dev-trace PostToolUse hook ingests them into the session
// trace, so `dev-trace.js summary` shows which workflow agent was slow or failed.
const devTrace = { version: 1, spans: [] }
let currentPhase = null
const now = () => Date.now()

function enterPhase(name) {
  currentPhase = name
  phase(name)
}

async function tracedAgent(prompt, opts = {}) {
  const span = { label: opts.label || 'agent', phase: opts.phase || currentPhase, start: now() }
  devTrace.spans.push(span)
  try {
    const result = await agent(prompt, opts)
    span.end = now()
    span.ok = result !== null && result !== undefined
    if (!span.ok) span.error = 'agent returned no result'
    else if (result && result.passed === false) span.error = `reported failure: ${(result.failures || []).slice(0, 5).join(' | ')}`.slice(0, 500)
    return result
  } catch (e) {
    span.end = now()
    span.ok = false
    span.error = String((e && e.message) || e).slice(0, 500)
    throw e
  }
}

// ─── Phase: IMPLEMENT ───────────────────────────────────────────────
enterPhase('Implement')

const plan = await tracedAgent(
  `Read the implementation plan at ${args.planPath}. Extract all tasks as a JSON array. Each task needs an id, description, and list of files it will touch.`,
  {
    label: 'parse-plan',
    schema: {
      type: 'object',
      properties: {
        tasks: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              id: { type: 'string' },
              description: { type: 'string' },
              files: { type: 'array', items: { type: 'string' } },
              independent: { type: 'boolean' }
            },
            required: ['id', 'description']
          }
        }
      },
      required: ['tasks']
    }
  }
)

const tasks = plan.tasks || []
log(`Found ${tasks.length} tasks in plan`)

const tddInstruction = args.tddRequired
  ? 'Write tests FIRST following TDD (red-green-refactor). Test must fail before implementation.'
  : 'Tests are optional for this task.'

const implemented = await parallel(tasks.map(task => () =>
  tracedAgent(
    `Implement this task:\n\nTask: ${task.description}\nFiles: ${(task.files || []).join(', ') || 'determine from task'}\n\n${tddInstruction}\n\nCommit when done with a clear message.`,
    {
      label: `impl:${task.id}`,
      phase: 'Implement',
      isolation: 'worktree'
    }
  )
))

const successfulImpls = implemented.filter(Boolean)
log(`${successfulImpls.length}/${tasks.length} tasks implemented`)

// ─── Phase: INTEGRATE ───────────────────────────────────────────────
enterPhase('Integrate')

const mergeResult = await tracedAgent(
  `${successfulImpls.length} parallel agents implemented tasks in isolated worktrees.
Merge all changes into the working tree. Resolve any merge conflicts — prefer the more complete implementation.
After merging, run a quick syntax check to verify nothing is broken.
Report: merged (boolean), conflicts (list of resolved conflicts).`,
  {
    label: 'integrator',
    schema: {
      type: 'object',
      properties: {
        merged: { type: 'boolean' },
        conflicts: { type: 'array', items: { type: 'string' } }
      },
      required: ['merged']
    }
  }
)

if (!mergeResult.merged) {
  return { status: 'FAILED', phase: 'integrate', details: 'Failed to merge parallel implementations', devTrace }
}
if ((mergeResult.conflicts || []).length > 0) {
  log(`Resolved ${mergeResult.conflicts.length} merge conflicts`)
}

// ─── Phase: VERIFY (max 3 debug cycles) ─────────────────────────────
enterPhase('Verify')

let verifyPassed = false
let lastFailures = []
for (let attempt = 0; attempt < 3; attempt++) {
  const result = await tracedAgent(
    'Run the full project test suite. If no test script exists, fall back to build verification. Report pass/fail. For each failure include the exact command you ran and the verbatim error lines (test name, assertion, file:line) - never a paraphrase.',
    { label: `verify-${attempt}`, schema: PASS_FAIL_SCHEMA }
  )

  if (result.passed) {
    verifyPassed = true
    log(`Verification passed (attempt ${attempt + 1})`)
    break
  }

  lastFailures = result.failures || []
  log(`Verification failed (attempt ${attempt + 1}): ${lastFailures.length} failures`)

  await tracedAgent(
    `Systematic debugging: find root cause of these failures and fix them. Root cause first, not symptoms.\nDo not guess: re-run the failing command, read the full error output (and the session trace via dev-trace.js failures if available), state the root cause with evidence, then fix. Re-run the SAME command to confirm.\n\nFailures:\n${(result.failures || ['unknown failures']).join('\n')}`,
    { label: `debug-${attempt}` }
  )
}

if (!verifyPassed) {
  return { status: 'FAILED', phase: 'verify', details: 'Tests failing after 3 debug cycles', lastFailures, devTrace }
}

// ─── Phase: REVIEW (adversarial verify + graduated remediation) ──────
enterPhase('Review')

const maestroReview = await tracedAgent(
  'Run a structured code review on all changed files. Classify each finding by severity: LOW, MEDIUM, HIGH, or CRITICAL. Be thorough.',
  { label: 'maestro-review', phase: 'Review', schema: FINDINGS_SCHEMA }
)

let allFindings = maestroReview?.findings || []
const hasHighFindings = allFindings.some(f => ['HIGH', 'CRITICAL'].includes(f.severity))

if (hasHighFindings) {
  const secondReview = await tracedAgent(
    'Independent code review as second opinion. Focus on correctness, security, and architectural issues. Classify by severity.',
    { label: 'second-review', phase: 'Review', schema: FINDINGS_SCHEMA }
  )
  allFindings = [...allFindings, ...(secondReview?.findings || [])]
}

log(`Total review findings: ${allFindings.length} (${allFindings.filter(f => ['HIGH', 'CRITICAL'].includes(f.severity)).length} HIGH/CRITICAL)`)

// Adversarial verify — pressure-test HIGH+ findings
const highFindings = allFindings.filter(f => ['HIGH', 'CRITICAL'].includes(f.severity))
if (highFindings.length > 0) {
  log(`Adversarial verify: ${highFindings.length} HIGH/CRITICAL findings`)

  const verdicts = await parallel(highFindings.map(f => () =>
    tracedAgent(
      `Try to REFUTE this code review finding. Default to refuted=true if uncertain.\n\nFinding: ${f.description}\nFile: ${f.file || 'unknown'}\nSeverity: ${f.severity}\n\nCheck the actual code. Is this genuinely a problem, or is the reviewer wrong?`,
      { label: `adversarial:${f.file || 'unknown'}`, phase: 'Review', schema: VERDICT_SCHEMA }
    )
  ))

  const confirmed = highFindings.filter((f, i) => verdicts[i] && !verdicts[i].refuted)
  const refutedCount = highFindings.length - confirmed.length
  log(`Adversarial result: ${confirmed.length} confirmed, ${refutedCount} refuted`)

  allFindings = [
    ...allFindings.filter(f => !['HIGH', 'CRITICAL'].includes(f.severity)),
    ...confirmed
  ]
}

// Graduated remediation loop — max 3 cycles on confirmed findings
let remainingHighFindings = allFindings.filter(f => ['HIGH', 'CRITICAL'].includes(f.severity))

for (let cycle = 0; cycle < 3 && remainingHighFindings.length > 0; cycle++) {
  log(`Remediation cycle ${cycle + 1}: ${remainingHighFindings.length} HIGH/CRITICAL findings`)

  const lowMed = allFindings.filter(f => ['LOW', 'MEDIUM'].includes(f.severity))
  if (lowMed.length > 0) {
    await tracedAgent(`Fix these LOW/MEDIUM findings inline:\n${JSON.stringify(lowMed, null, 2)}`, { label: `fix-lowmed-${cycle}` })
  }

  const high = remainingHighFindings.filter(f => f.severity === 'HIGH')
  if (high.length > 0) {
    await tracedAgent(`Fix these HIGH findings:\n${JSON.stringify(high, null, 2)}`, { label: `fix-high-${cycle}` })
  }

  const critical = remainingHighFindings.filter(f => f.severity === 'CRITICAL')
  if (critical.length > 0) {
    await tracedAgent(`Fix these CRITICAL findings. Amend the implementation if needed:\n${JSON.stringify(critical, null, 2)}`, { label: `fix-critical-${cycle}` })
  }

  // Re-verify after fixes
  const recheck = await tracedAgent(
    'Re-run full test suite after review fixes.',
    { label: `re-verify-${cycle}`, schema: PASS_FAIL_SCHEMA }
  )
  if (!recheck.passed) {
    await tracedAgent('Debug and fix test failures introduced by review fixes.', { label: `re-debug-${cycle}` })
  }

  // Lightweight re-review
  if (high.length > 0 || critical.length > 0) {
    const reReview = await tracedAgent(
      'Re-review only the files changed by the latest fixes. Report remaining HIGH/CRITICAL issues only.',
      { label: `re-review-${cycle}`, schema: FINDINGS_SCHEMA }
    )
    remainingHighFindings = (reReview?.findings || []).filter(f => ['HIGH', 'CRITICAL'].includes(f.severity))
  } else {
    remainingHighFindings = []
  }
}

// ─── Phase: AUDIT (parallel conditional + remediation) ───────────────
enterPhase('Audit')

const auditThunks = []
if (args.auditTriggers?.security) {
  auditThunks.push(() => tracedAgent(
    'Security audit: check auth flows, injection vectors, OWASP Top 10, secret handling, data exposure on all changed files.',
    { label: 'security-audit', phase: 'Audit', schema: FINDINGS_SCHEMA }
  ))
}
if (args.auditTriggers?.a11y) {
  auditThunks.push(() => tracedAgent(
    'Accessibility audit: check WCAG compliance, ARIA usage, keyboard navigation, screen reader compatibility, color contrast.',
    { label: 'a11y-audit', phase: 'Audit', schema: FINDINGS_SCHEMA }
  ))
}
if (args.auditTriggers?.perf) {
  auditThunks.push(() => tracedAgent(
    'Performance check: identify N+1 queries, unnecessary re-renders, unbounded loops, missing pagination, unoptimized I/O.',
    { label: 'perf-audit', phase: 'Audit', schema: FINDINGS_SCHEMA }
  ))
}

let auditFindings = []
if (auditThunks.length > 0) {
  const auditResults = (await parallel(auditThunks)).filter(Boolean)
  auditFindings = auditResults.flatMap(r => r?.findings || [])

  log(`Audit findings: ${auditFindings.length} total (${auditFindings.filter(f => ['HIGH', 'CRITICAL'].includes(f?.severity)).length} HIGH/CRITICAL)`)

  // Audit remediation loop — max 3 cycles
  let auditHighFindings = auditFindings.filter(f => ['HIGH', 'CRITICAL'].includes(f?.severity))
  for (let auditCycle = 0; auditCycle < 3 && auditHighFindings.length > 0; auditCycle++) {
    log(`Audit remediation cycle ${auditCycle + 1}: ${auditHighFindings.length} findings`)

    await tracedAgent(
      `Fix these audit findings:\n${JSON.stringify(auditHighFindings, null, 2)}`,
      { label: `audit-fix-${auditCycle}` }
    )

    const recheck = await tracedAgent(
      'Re-run full test suite after audit fixes.',
      { label: `audit-re-verify-${auditCycle}`, schema: PASS_FAIL_SCHEMA }
    )
    if (!recheck.passed) {
      await tracedAgent('Debug and fix test failures from audit fixes.', { label: `audit-re-debug-${auditCycle}` })
    }

    const reAudit = await tracedAgent(
      'Re-check previously failing audit areas only. Report remaining HIGH/CRITICAL.',
      { label: `re-audit-${auditCycle}`, schema: FINDINGS_SCHEMA }
    )
    auditHighFindings = (reAudit?.findings || []).filter(f => ['HIGH', 'CRITICAL'].includes(f?.severity))
  }
} else {
  log('No conditional audits triggered')
}

// ─── Return results to SKILL.md orchestrator ─────────────────────────
return {
  status: 'SUCCESS',
  implemented: successfulImpls.length,
  totalTasks: tasks.length,
  verified: verifyPassed,
  reviewFindings: allFindings,
  remainingHighFindings: remainingHighFindings.length,
  auditFindings,
  mergeConflicts: mergeResult.conflicts || [],
  devTrace
}
