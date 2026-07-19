# Autonomous Phase Workflow

Use this workflow when the input is a high-level phase goal and the work should
progress autonomously while preserving human control over consequential actions.

## Input

```text
Phase goal: <one high-level outcome>
```

If the phase goal is missing or ambiguous enough to change the scope, ask for it
before creating a plan.

## Files

Create and maintain these files separately:

- `.workflow/plan.md` — the approved phase plan and acceptance criteria.
- `.workflow/status.md` — current state, actions, evidence, blockers, and
  approval decisions.

Create the `.workflow/` directory when needed. Never use `status.md` as a
substitute for the plan.

## Approval policy

Ask the human only when one of these applies:

1. The plan is ready to start. Do not execute phase work until the human
   approves the plan.
2. A command is highly permissive, destructive, irreversible, production-facing,
   privacy-sensitive, external, or outside the repository's stated scope.
3. A material decision changes the goal, scope, architecture, acceptance
   criteria, or risk beyond the approved plan.
4. The phase is complete and the next phase is ready. Do not move to the next
   phase until the human explicitly approves the current plan/status and the
   transition.

Do not ask for approval for ordinary read-only inspection, scoped edits,
reversible local commands, tests, or routine implementation choices covered by
the approved plan.

## Procedure

### 1. Initialize

Read the repository instructions and current workflow files. Preserve unrelated
user changes. If an active phase exists, resume it from `status.md` rather than
creating a competing plan.

### 2. Plan

Create `.workflow/plan.md` with:

```markdown
# Phase Plan

## Goal
<high-level phase goal>

## Scope
- <included work>

## Out of scope
- <explicit exclusions>

## Tasks
1. <smallest ordered task>

## Acceptance criteria
- <observable check>

## Approval
- State: pending
- Approved by: —
- Approved at: —
```

Keep the plan finite and outcome-focused. Do not invent requirements that are
not needed to achieve the goal. Set `status.md` to `Awaiting plan approval`.

### 3. Start the approved phase

After explicit plan approval, record the approval in both files and set the
status to `In progress`. Execute one bounded task at a time. After each task:

- inspect fresh state;
- make the smallest scoped change;
- run the available relevant check;
- record the command, result, and evidence in `status.md`;
- update the task state in `plan.md` only when the evidence supports it.

### 4. Handle decisions and commands

For ordinary implementation choices, choose the smallest option consistent with
the approved plan and continue. For a gated command or material decision, stop
at `Approval required` and record:

- the exact command or decision;
- why it is gated;
- expected impact and rollback, when applicable;
- the smallest safe alternative, if one exists.

Resume only after explicit permission. Never treat silence, a vague response,
or an earlier approval as permission for a new gated action.

### 5. Finish the phase

When all acceptance criteria pass, record the evidence and set `status.md` to
`Awaiting next-phase approval`. Add a proposed next phase only if the current
goal naturally produces one; otherwise set the terminal state to `Complete`.

Do not start, plan in detail, or execute the next phase until the human approves
the transition. A transition approval must be recorded in `status.md` with the
approved phase goal.

## Status format

Keep `.workflow/status.md` concise and append events rather than rewriting
history:

```markdown
# Workflow Status

- State: Awaiting plan approval | In progress | Approval required | Blocked | Awaiting next-phase approval | Complete
- Current phase: <name>
- Current task: <task or —>
- Last updated: <timestamp>

## Evidence
- <check and result>

## Decisions
- <decision, rationale, and approval if required>

## Blockers
- <blocker or None>

## Event log
- <timestamp> — <state/action/result>
```

## Stop conditions

Stop and report `Blocked` when required information, access, or a reproducible
check is unavailable. Stop and report `Approval required` for any gated action.
Never report an error, skipped check, or exhausted attempt as success.

