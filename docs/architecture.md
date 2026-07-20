# LogLens Architecture

LogLens is an AI-assisted log search and incident investigation platform. Logs
flow through an event-driven pipeline; incidents are the central entity; the AI
service assists engineers by reasoning only over retrieved evidence.

## Services

| Service            | Responsibility                                  | Transport        |
|--------------------|-------------------------------------------------|------------------|
| log-producer       | Generate/simulate logs into the `logs` topic    | Kafka            |
| storage-consumer   | Persist raw logs to PostgreSQL (`log_entries`)  | Kafka → Postgres |
| embedding-service  | Embed log messages → Qdrant vector store        | Kafka → Qdrant   |
| incident-service   | Rule-based clustering → `incidents` table       | Kafka → Postgres |
| ai-service         | Retrieval + prompt construction + LLM reasoning | HTTP (FastAPI)   |
| api                | REST API + dashboard console                    | HTTP (FastAPI)   |

## Data model

- `log_entries`: id, timestamp, service_name, level, message, trace_id, span_id
- `incidents`: id, title, start_time, end_time, severity, severity_label,
  status, services, log_count, log_ids, feature_vector (TF-IDF JSON), created_at

## Retrieval pipeline (AGENT.md)

Every investigation follows:

```
Query / Incident
    ↓
Embedding (incident error messages)
    ↓
Vector Search (Qdrant)
    ↓
Metadata Filtering (incident timeline, similar incidents)
    ↓
Prompt Construction (modular templates)
    ↓
LLM (Gemini, OpenAI-compatible)
    ↓
Structured Response (summary, root cause, evidence)
```

The LLM is never called over the full log history. Context is assembled first
from three bounded sources:

1. **Incident timeline** — the incident's linked `log_entries`, ordered by time.
2. **Semantic neighbours** — Qdrant vector search over the log collection.
3. **Similar incidents** — TF-IDF cosine similarity against other incidents.

## AI service design

- **Isolation**: AI code is separate from infrastructure. Prompts live in
  `app/prompts.py`; retrieval in `app/retrieval.py`; orchestration in
  `app/investigate.py`.
- **Provider abstraction**: `app/llm.py` defines an `LLMClient` over an
  OpenAI-compatible chat completions API. Default backend is Google Gemini
  (`gemini-3.1-flash-lite`) via its OpenAI-compatible endpoint. The base URL,
  model, and API key come from the environment (`LLM_BASE_URL`, `LLM_MODEL`,
  `GEMINI_API_KEY`) — nothing is hardcoded.
- **Modular prompts**: `system_prompt()`, `build_context_block()`,
  `summarize_user_prompt()`, `investigate_user_prompt()` are discrete, reusable
  functions.
- **No fabrication guarantee**: the system prompt forbids inventing logs,
  timestamps, services, or root causes absent from the context. If evidence is
  insufficient, the model must state so. Every claim references evidence IDs
  (e.g. `[log:12]`, `[incident:3]`).
- **Read-only evidence**: the AI service only reads PostgreSQL and Qdrant; it
  never writes incidents or logs.

## Endpoints

- `GET /incidents/` — list incidents
- `GET /incidents/{id}` — incident details
- `GET /incidents/{id}/timeline` — chronological logs
- `GET /incidents/{id}/similar` — similar historical incidents
- `POST /ai/incident/{id}/summarize` — plain-language summary (AI service)
- `POST /ai/incident/{id}/investigate` — root-cause hypothesis + cited evidence
- `GET /dashboard/` — investigation console

## Dashboard

The console lists incidents, shows a timeline and similar incidents, and exposes
an AI panel with **Summarize** and **Investigate** actions. Responses render the
model's output alongside the evidence items it cited.

## Out of scope

Autonomous agents, automatic remediation, real-time alerting, and model
training are explicitly excluded.
