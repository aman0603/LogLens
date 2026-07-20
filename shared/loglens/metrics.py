"""Prometheus metrics helpers shared across services.

Exposes a single registry and convenience instruments so every service reports
request count, latency histogram, and error counter consistently. The registry
is exposed via a /metrics endpoint (see ``make_metrics_app``).
"""

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
)

# A shared registry so all instruments land in one /metrics scrape.
REGISTRY = CollectorRegistry()

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["service", "method", "endpoint", "status"],
    registry=REGISTRY,
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["service", "method", "endpoint"],
    registry=REGISTRY,
)
ERROR_COUNT = Counter(
    "app_errors_total",
    "Total application errors",
    ["service", "type"],
    registry=REGISTRY,
)
KAFKA_MESSAGES = Counter(
    "kafka_messages_total",
    "Total Kafka messages processed",
    ["service", "topic", "outcome"],
    registry=REGISTRY,
)
DB_OPS = Gauge(
    "db_connections",
    "Current DB connection pool size (approximated)",
    ["service"],
    registry=REGISTRY,
)


def observe_request(service: str, method: str, endpoint: str, status: int, duration: float):
    REQUEST_COUNT.labels(service=service, method=method, endpoint=endpoint, status=status).inc()
    REQUEST_LATENCY.labels(service=service, method=method, endpoint=endpoint).observe(duration)
    if status >= 500:
        ERROR_COUNT.labels(service=service, type="http_5xx").inc()


def metrics_response():
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


def start_sidecar(host: str = "0.0.0.0", port: int = 8000, service: str = "service"):
    """Start a minimal HTTP server exposing /health, /ready, /metrics.

    Used by non-API services (consumers/producers) that otherwise have no HTTP
    surface, so Prometheus can scrape them and orchestrators can health-check.
    Runs in a daemon thread; does not block the main loop.
    """
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import json as _json

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json"):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/health":
                self._send(200, _json.dumps({"status": "ok"}))
            elif self.path == "/ready":
                self._send(200, _json.dumps({"status": "ok", "dependencies": {}}))
            elif self.path == "/metrics":
                body, ctype = metrics_response()
                self._send(200, body, ctype)
            else:
                self._send(404, _json.dumps({"detail": "not found"}))

        def log_message(self, *args):
            return  # quiet

    server = ThreadingHTTPServer((host, port), Handler)
    import threading

    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server
