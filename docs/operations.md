# LogLens Operations

Production-hardening guide for LogLens: configuration, auth, observability,
reliability, and deployment.

## Configuration management

All services load configuration through `shared/loglens/config.py` via
`load_config(required=[...], optional={...}, casts={...})`. The service fails
fast at startup if a required variable is missing or fails validation, so
misconfiguration is caught before the service accepts traffic. No service reads
`os.getenv` directly for its own settings — the shared helper is the single
source of truth.

| Variable | Used by | Required | Default |
|----------|---------|----------|---------|
| `DATABASE_URL` | api, ai, storage, incident | yes | — |
| `JWT_SECRET` | api, ai | yes | — |
| `QDRANT_HOST` / `QDRANT_PORT` | api, ai, embedding | no | qdrant / 6333 |
| `RATE_LIMIT` | api, ai | no | 20 req/s per client |
| `KAFKA_BOOTSTRAP_SERVERS` | producers/consumers | no | kafka:9092 |
| `KAFKA_MAX_RETRIES` | consumers | no | 3 |
| `GEMINI_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | ai | no | Gemini OpenAI-compatible |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | api, ai | no | otel-collector:4317 |

## Authentication & RBAC

Shared-secret JWT (HS256) implemented in `shared/loglens/auth.py`. Tokens carry
a `role` claim. The API is the system ingress and enforces auth:

- `viewer` — read incidents/logs/search/dashboard.
- `analyst` — also AI endpoints (`/ai/...`).
- `admin` — all current capabilities.

Public (no token) endpoints: `/health`, `/ready`, `/metrics`. A dev token
endpoint `POST /auth/token?role=...` issues a JWT for local/demo use. Unauthorized
requests return **401**; authorized-but-forbidden roles return **403**.

## Rate limiting

In-memory token-bucket limiter (`shared/loglens/ratelimit.py`), one bucket per
client IP, applied in the API middleware. Exceeding the limit returns **429**
with a `Retry-After` header. Suitable for single-instance deployment; no Redis.

## Structured logging

Every service uses JSON logging via `shared/loglens/logging.py`, emitting
`timestamp`, `service`, `level`, `message`, `request_id`, `correlation_id`, and
`trace_id` when available. A contextvar propagates the correlation IDs across
calls without threading them through every function.

## Observability

- **Metrics**: every service exposes `/metrics` (Prometheus format) using a
  shared registry (`shared/loglens/metrics.py`): `http_requests_total`,
  `http_request_duration_seconds`, `app_errors_total`, `kafka_messages_total`.
  Consumers/producers expose these via a lightweight sidecar HTTP server.
- **Scraping**: `infra/monitoring/prometheus.yml` scrapes every service on
  `:8000`/`:8000`.
- **Dashboards**: Grafana is provisioned with a Prometheus datasource and the
  `infra/monitoring/grafana/dashboards/loglens.json` dashboard (request rate,
  error rate, p95 latency, Kafka outcomes).
- **Tracing**: OpenTelemetry (`shared/loglens/tracing.py`) instruments FastAPI
  and HTTP. Spans export to the OTLP collector → Jaeger when
  `OTEL_EXPORTER_OTLP_ENDPOINT` is set; otherwise tracing degrades gracefully.

## Reliability: retry & dead-letter queues

Kafka consumers (storage, embedding, incident) process each message with
`shared/loglens/kafka_retry.with_retry`: up to `KAFKA_MAX_RETRIES` attempts with
exponential backoff. After exhaustion (or on undecodable payloads), the original
message is published to a `<topic>.dlq` topic — no poison record is lost. All
outcomes are counted in `kafka_messages_total` (success/retry/dlq/decode_error).

## Health & readiness

- `/health` — liveness (process up).
- `/ready` — readiness (dependency checks, e.g. Postgres).
- `/metrics` — Prometheus scrape target.

The docker-compose healthchecks hit `/health` on every service.

## Deployment

- **Images**: `Dockerfile.python` is a multi-stage build (builder + slim
  runtime), runs as a non-root `appuser`, sets `PYTHONPATH=/app/shared`, and
  includes a `HEALTHCHECK`. Each service is built with
  `--build-arg SERVICE_DIR=./apps/<svc>`.
- **Orchestration**: `infra/compose/docker-compose.yml` brings up Kafka,
  Postgres, Qdrant, all services, Prometheus, Grafana, the OTel collector, and
  Jaeger, with health-based dependencies and a sidecar metrics port per service.
- **CI/CD**: `.github/workflows/ci.yml` runs `ruff format --check`, `ruff check`,
  unit tests (with `PYTHONPATH=shared`), and builds every service image.

## Local quickstart

```bash
export JWT_SECRET=$(openssl rand -hex 32)
docker compose -f infra/compose/docker-compose.yml up -d --build
# API:        http://localhost:8000  (dashboard at /dashboard)
# AI service: http://localhost:8001
# Prometheus: http://localhost:9090
# Grafana:    http://localhost:3000 (admin/admin)
# Jaeger:     http://localhost:16686
```
