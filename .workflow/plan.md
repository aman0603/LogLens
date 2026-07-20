# Phase Plan

## Goal
Prepare LogLens for production-quality operation by strengthening reliability,
observability, security, and deployment — while preserving the existing event-
driven, service-isolated architecture. The platform should demonstrate the
engineering practices expected of modern distributed systems.

## Success Outcome
Once this phase is complete, the system will be able to:
- Authenticate requests and enforce role-based access control.
- Expose Prometheus metrics from every service and visualize them in Grafana.
- Propagate distributed traces (OpenTelemetry) across services and Kafka.
- Limit request rates to protect services from abuse.
- Retry transient failures and route poisoned messages to a dead-letter queue.
- Report health/readiness consistently from every service.
- Build, test, and deploy via a CI/CD pipeline and production-grade Docker.
- Demonstrate all of the above through comprehensive automated tests.

## Scope
- Shared auth + RBAC middleware (token/JWT) applied at the API boundary.
- Prometheus metrics (request counts, latencies, error rates, Kafka/DB gauges)
  exposed at `/metrics` on every service.
- Grafana dashboards + Prometheus scrape config (static or compose service).
- OpenTelemetry instrumentation: traces across HTTP and Kafka produce/consume.
- Rate limiting middleware on the API.
- Retry-with-backoff and dead-letter handling for Kafka consumers
  (storage-consumer, embedding-service, incident-service).
- Standardized `/health` (liveness) and `/ready` (readiness) endpoints.
- CI/CD pipeline (GitHub Actions): lint, unit tests, docker build.
- Production Docker: multi-stage builds, non-root user, healthchecks in compose.
- Expanded tests: auth, rate limit, retry/DLQ, metrics endpoint, health.

## Engineering Constraints
- Preserve backward compatibility: existing APIs (`/logs/`, `/search/`,
  `/incidents/...`, `/ai/...`) keep working; auth is opt-in per route and
  non-breaking for internal service-to-service calls where appropriate.
- Maintain service boundaries: each service keeps one responsibility; shared
  concerns (auth, metrics, tracing) live in a shared library consumed by all
  services, not duplicated per service.
- Event-driven rules hold: Kafka remains the backbone; retry/DLQ use Kafka
  mechanics, not synchronous calls. Consumers stay idempotent.
- Asynchronous processing must not be blocked by new middleware.
- Avoid new external dependencies unless necessary; prefer libraries already
  aligned with the stack (FastAPI/Python, Kafka, Postgres, Qdrant).

## Architecture Decisions
- Introduce a `shared/` Python package (or `internal/`) with reusable helpers:
  auth (JWT verify), metrics (Prometheus counters/histograms), tracing (OTel
  setup), rate limiting, health, and Kafka retry/DLQ utilities. Each service
  imports from it — no cross-service runtime calls for these concerns.
- Auth model: bearer JWT validated at the `api` service (the system's ingress).
  Roles: `viewer` (read incidents/logs/search/dashboard), `analyst` (also AI
  endpoints), `admin` (all + future management). RBAC enforced via dependency.
- Metrics: `prometheus-client` exposing `/metrics`; Prometheus scrapes each
  service; Grafana reads Prometheus. No metrics stored in app DB.
- Tracing: OpenTelemetry with OTLP exporter; auto-instrument HTTP; manual span
  around Kafka produce/consume and DB calls. Backend (Jaeger/OTel collector)
  added to compose as an option.
- Rate limiting: token-bucket per client/IP at the API using an in-memory or
  Redis-backed limiter; Redis added to compose only if chosen (default
  in-memory for single-instance demo).
- Retry/DLQ: consumers retry N times with backoff; on exhaustion, publish to a
  `<topic>.dlq` topic and log. No message loss for poison records.
- Deployment: multi-stage Dockerfile (builder + slim runtime, non-root),
  compose healthchecks, CI builds images and runs tests.
- CI/CD: GitHub Actions workflow running on PR/push — install deps, lint, unit
  tests (mocked externals), docker build per service.

## Deliverables
- `shared/` library: `auth.py`, `metrics.py`, `tracing.py`, `ratelimit.py`,
  `health.py`, `kafka_retry.py`.
- Updated services wiring in `shared` helpers (api, ai-service, incident-service,
  storage-consumer, embedding-service, log-producer).
- `infra/monitoring/` with `prometheus.yml`, Grafana datasource + dashboard JSON.
- `infra/compose/docker-compose.yml` extended with prometheus, grafana,
  (optional) otel-collector/jaeger, redis (if rate limiting needs it).
- `infra/docker/` multi-stage production Dockerfiles + `.dockerignore`.
- `.github/workflows/ci.yml` CI/CD pipeline.
- Auth + RBAC applied to API routes; dashboard reads token.
- Expanded test suite covering auth, rate limit, retry/DLQ, metrics, health.
- `docs/operations.md` describing auth, metrics, tracing, deployment.

## Out of Scope
- Real user identity provider / SSO integration (use shared-secret/JWT demo).
- Kubernetes manifests (compose-based production-style deployment only).
- Automatic remediation or autonomous agents.
- Re-architecting storage or replacing Kafka/Postgres/Qdrant.

## Acceptance Criteria
- [ ] API requires a valid token for protected routes; RBAC roles enforced (viewer/analyst/admin); public health/metrics excluded.
- [ ] Every service exposes `/metrics` with request count, latency histogram, and error counter; Prometheus scrapes them.
- [ ] Grafana dashboard visualizes request rate, error rate, and latency per service.
- [ ] Distributed traces span API -> ai-service -> DB/Qdrant and Kafka produce/consume.
- [ ] Rate limiting returns 429 when the threshold is exceeded.
- [ ] Kafka consumers retry with backoff and route failing messages to a `.dlq` topic.
- [ ] Every service has `/health` (liveness) and `/ready` (readiness) returning structured status.
- [ ] CI/CD pipeline runs lint + unit tests + docker build on push/PR.
- [ ] Production Dockerfiles are multi-stage, non-root, with compose healthchecks.
- [ ] Comprehensive automated tests pass for auth, RBAC, rate limit, retry/DLQ, metrics, health.
- [ ] `docs/operations.md` documents the production setup.

## Approval
- State: approved
- Approved by: user
- Approved at: 2026-07-20 00:20 UTC
- Expanded scope approved: centralized config + fail-fast validation; structured JSON logging (request/correlation/trace IDs); /health+/ready+/metrics consistently; GitHub Actions (format+lint+test+docker build); shared-secret JWT; in-memory rate limiter; no new infrastructure.
- Acceptance: JWT enforced, RBAC (401/403), Prometheus scrapes all, Grafana live, retry/DLQ verified, health/ready/metrics on all, CI passes on clean checkout, regression tests pass.
