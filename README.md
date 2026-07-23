# LogLens

AI-assisted log search and incident investigation platform. LogLens ingests
logs through an event-driven pipeline, automatically clusters them into
incidents, and uses retrieval-augmented AI (grounded in evidence) to explain
incidents and propose likely root causes. It is built to demonstrate production
distributed-systems practices: observability, security, reliability, and clean
service boundaries.

## Architecture

Independent services, each owning one responsibility, communicating
asynchronously via Kafka.

| Service            | Responsibility                                  | Transport        |
|--------------------|-------------------------------------------------|------------------|
| `log-producer`     | Simulate/generate logs into the `logs` topic    | Kafka            |
| `storage-consumer` | Persist raw logs to PostgreSQL (`log_entries`)  | Kafka → Postgres |
| `embedding-service`| Embed log messages → Qdrant vector store        | Kafka → Qdrant   |
| `incident-service`| Rule-based clustering → `incidents` table       | Kafka → Postgres |
| `ai-service`       | Retrieval + prompt construction + LLM reasoning | HTTP (FastAPI)   |
| `api`              | REST API + investigation dashboard              | HTTP (FastAPI)   |

Shared, reusable concerns (configuration, structured logging, auth, metrics,
tracing, rate limiting, Kafka retry/DLQ) live in `shared/loglens/` and are
imported by every service — never duplicated.

## Features

- **Incident detection**: rule-based clustering of logs into incidents with
  severity scoring and timelines.
- **Semantic search**: Qdrant vector search over log embeddings.
- **AI investigation**: Gemini (OpenAI-compatible) summarizes incidents and
  proposes root causes using only retrieved evidence, with citations.
- **Auth & RBAC**: shared-secret JWT; roles `viewer` / `analyst` / `admin`.
- **Observability**: Prometheus metrics + Grafana dashboards, OpenTelemetry
  tracing, and structured JSON logging with correlation/trace IDs.
- **Reliability**: in-memory rate limiting (429), Kafka consumer retry with
  exponential backoff, and dead-letter topics (`<topic>.dlq`).
- **Health**: `/health`, `/ready`, and `/metrics` on every service.
- **CI/CD**: GitHub Actions runs format/lint/tests and builds all images.

## Project layout

```
apps/            # services (api, ai-service, incident-service, storage-consumer,
                 #           embedding-service, log-producer)
shared/loglens/  # shared library (config, logging, auth, metrics, tracing, ...)
infra/compose/   # docker-compose.yml
infra/monitoring/# prometheus.yml, grafana dashboards, otel config
docs/            # architecture.md, operations.md
.github/workflows/# CI pipeline
```

## Quickstart

```bash
# 1. Configure secrets
export JWT_SECRET=$(openssl rand -hex 32)
cp .env.example .env   # edit GEMINI_API_KEY etc. as needed

# 2. Build and run everything
docker compose up -d --build
```

Services:

| Component  | URL                                   |
|------------|---------------------------------------|
| API + dashboard | http://localhost:8000  (`/dashboard`) |
| AI service      | http://localhost:8001                 |
| Prometheus      | http://localhost:9090                 |
| Grafana         | http://localhost:3000 (admin/admin)   |
| Jaeger          | http://localhost:16686                |

### Get a token (local/dev)

```bash
curl -X POST http://localhost:8000/auth/token?role=analyst
# -> { "access_token": "...", "role": "analyst" }
```

Use the token as `Authorization: Bearer <token>` on protected endpoints.

## API reference

All data/AI endpoints require a JWT (`viewer` for reads, `analyst`+ for AI).
`/health`, `/ready`, `/metrics` are public.

- `POST /logs/` — ingest a log
- `GET  /logs/` — list logs
- `GET  /search/?q=...` — semantic search
- `GET  /incidents/` — list incidents
- `GET  /incidents/{id}` — incident details
- `GET  /incidents/{id}/timeline` — chronological logs
- `GET  /incidents/{id}/similar` — similar historical incidents
- `POST /ai/incident/{id}/summarize` — AI summary (analyst+)
- `POST /ai/incident/{id}/investigate` — AI root-cause analysis (analyst+)
- `GET  /dashboard/` — investigation console

## Configuration

Services load config via `shared/loglens/config.py` and fail fast on missing
required variables. Key variables: `DATABASE_URL`, `JWT_SECRET`, `QDRANT_HOST`,
`RATE_LIMIT`, `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_MAX_RETRIES`, `GEMINI_API_KEY`,
`LLM_BASE_URL`, `LLM_MODEL`, `OTEL_EXPORTER_OTLP_ENDPOINT`. See
`docs/operations.md` for the full reference.

## Development

```bash
pip install -r requirements.txt
export PYTHONPATH=shared JWT_SECRET=dev DATABASE_URL=sqlite:///dev.db
ruff format --check . && ruff check .
python -m unittest discover -s shared/tests   -p 'test_*.py'
python -m unittest discover -s apps/ai-service/tests -p 'test_*.py'
```

## Documentation

- `docs/architecture.md` — system & AI retrieval/reasoning pipeline.
- `docs/operations.md` — auth, observability, reliability, deployment.

## License

See repository for license terms.
