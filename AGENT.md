# AGENTS.md

# LogLens

LogLens is an AI-powered log search and incident investigation platform.

The goal is to build a production-quality system that demonstrates distributed systems, event-driven architecture, observability, and practical AI engineering. This is not a chatbot project or a CRUD application.

---

# Engineering Philosophy

Build features as if they will operate in a real production environment.

When multiple implementations are possible, prefer the one that demonstrates:

- distributed systems
- asynchronous processing
- observability
- scalability
- maintainability

over the shortest implementation.

Avoid unnecessary abstractions, but also avoid shortcuts that make future scaling difficult.

---

# System Architecture

LogLens is composed of independent services.

Each service owns exactly one responsibility.

Examples include:

- log ingestion
- log persistence
- embedding generation
- semantic retrieval
- incident detection
- AI analysis
- dashboard

Do not mix responsibilities across services.

Prefer event-driven communication through Kafka whenever asynchronous processing is appropriate.

---

# Incident-Centric Design

Incidents are the primary entity in the system.

Users investigate incidents, not individual log entries.

New functionality should extend the incident workflow rather than creating parallel investigation models.

Logs, summaries, timelines, AI analysis, and historical context should all connect back to an incident.

---

# AI Principles

AI exists to assist engineers, not replace them.

Every AI response must be grounded in retrieved evidence.

Never fabricate:

- logs
- timelines
- incident causes
- recommendations

If available evidence is insufficient, the AI should explicitly state that rather than speculate.

---

# Retrieval Pipeline

Every investigation follows this flow:

```
Query
    ↓
Embedding
    ↓
Vector Search
    ↓
Metadata Filtering
    ↓
Prompt Construction
    ↓
LLM
    ↓
Structured Response
```

Never call the LLM directly over the complete log history.

Always retrieve relevant context first.

Semantic search and keyword search are different capabilities and should remain separate implementations.

---

# Service Responsibilities

The AI service owns:

- embeddings
- retrieval
- prompt construction
- summarization
- root cause suggestions

The incident engine owns:

- clustering
- correlation
- timeline reconstruction
- severity calculation

Storage services only persist and retrieve data.

Avoid duplicating responsibilities between services.

---

# Event-Driven Rules

Kafka is the system backbone.

Assume:

- duplicate delivery
- consumer retries
- out-of-order processing across partitions

Consumers should therefore be idempotent.

Avoid synchronous service-to-service calls when an event-driven workflow is appropriate.

---

# Structured Logging

Every service must produce structured logs.

Include at minimum:

- timestamp
- service
- level
- trace_id
- request_id
- message

Structured logs are part of the product and may later be ingested back into LogLens itself.

---

# Dashboard Philosophy

The dashboard is an investigation console, not an administration panel.

Prioritize features that help engineers answer questions such as:

- What happened?
- When did it start?
- Which services are affected?
- What similar incidents have occurred before?
- What evidence supports the AI's conclusion?

Avoid building generic CRUD screens unless required.

---

# Future Compatibility

Design new components so they can later integrate with:

- OpenTelemetry
- Kubernetes Events
- Prometheus
- Grafana
- Loki
- Slack
- PagerDuty
- GitHub Deployments

Avoid implementation decisions that tightly couple the system to simulated log sources.

---

# Repository Conventions

Keep business logic independent from transport layers.

Keep AI code isolated from infrastructure code.

Store prompts separately from application logic.

Do not hardcode provider-specific implementations where an abstraction already exists.

When extending functionality, prefer existing modules before introducing new packages.

---

# Autonomous Development Loop

Development may be run as a bounded autonomous phase loop. The input is one
high-level phase goal. The workflow definition is in
`AUTONOMOUS_WORKFLOW.md`; follow it whenever autonomous execution is requested.

## Durable State

Keep the loop's memory outside the conversation:

- `.workflow/plan.md` contains the current phase goal, scope, tasks, and
  observable acceptance criteria.
- `.workflow/status.md` contains the current state, evidence, blockers,
  decisions, approvals, and event history.

Keep plan and status as separate files. Resume an active phase from these files
and preserve unrelated user changes.

## Phase and Approval Rules

- Create a finite plan before implementation and wait for explicit plan approval.
- Once approved, execute bounded tasks autonomously and verify each task with
  the smallest relevant check.
- Ask the human only for highly permissive, destructive, irreversible,
  production-facing, privacy-sensitive, out-of-scope, or externally visible
  commands and decisions.
- Stop for explicit approval when a decision changes the approved goal, scope,
  architecture, risk, or acceptance criteria.
- When the phase passes its acceptance criteria, set the status to
  `Awaiting next-phase approval`; never begin the next phase without explicit
  transition approval.
- Use `Blocked` when required access, information, or reproducible verification
  is unavailable. Never treat an error or skipped check as success.

## Loop Engineering Practices

Apply these practices in this order as the project grows:

1. **Skills:** keep LogLens architecture, service boundaries, retrieval rules,
   and incident principles in this file and in focused skills rather than
   repeating them in every task.
2. **Verification:** separate implementation from review where risk justifies
   it. A checker must compare the result with the approved plan and evidence,
   not merely restate the implementer's conclusion.
3. **Isolation:** use a separate Git worktree before running parallel agents or
   parallel feature work. Never let parallel agents edit the same checkout.
4. **Connectors:** add issue tracker, CI, observability, or notification
   integrations only when a real recurring workflow needs them and each action
   has an explicit approval boundary.
5. **Automation:** add scheduled discovery or triage only after the manual loop
   has a stable acceptance check and a useful no-op outcome.

The agent remains responsible for understanding the code it changes. Human
review is still required for phase plans, gated actions, and phase transitions;
autonomy must not become unreviewed production change.

Reference: [Loop Engineering](https://addyosmani.com/blog/loop-engineering/).

---

# Success Criteria

A feature is complete when it:

- integrates naturally into the existing architecture
- preserves clear service boundaries
- remains observable and testable
- follows the incident-centric workflow
- improves the investigation experience without increasing unnecessary complexity
