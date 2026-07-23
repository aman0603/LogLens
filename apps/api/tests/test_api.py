import sys
import os
import types
import unittest

# Ensure the shared library is importable.
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared"
    ),
)

# The API imports heavy optional deps at module load; stub them if absent so the
# test is runnable in minimal environments (CI installs them via requirements).
for name in ("qdrant_client", "qdrant_client.models", "loglens.embedding"):
    if name not in sys.modules:
        m = types.ModuleType(name)
        if name == "qdrant_client":
            m.QdrantClient = object
        elif name == "qdrant_client.models":
            m.Distance = object
        elif name == "loglens.embedding":
            m.embed = lambda text, model=None: [0.0] * 768
            m.EMBEDDING_DIM = 768
            m.DEFAULT_MODEL = "text-embedding-004"
        sys.modules[name] = m

os.environ.setdefault("JWT_SECRET", "test-secret")
# Use a local sqlite DB for hermetic tests (no Postgres required).
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from fastapi.testclient import TestClient
from app import main as api_main
from loglens import auth as ll_auth


# Override DB dependency with a no-op session to avoid a real database.
class _FakeDB:
    pass


def _fake_get_db():
    yield _FakeDB()


api_main.get_db = _fake_get_db
# Patch CRUD calls used by routes to avoid DB access.
import app.crud as crud

crud.get_logs = lambda db, skip=0, limit=100: []
crud.get_incidents = lambda db, skip=0, limit=100, status=None: []
crud.get_incident = lambda db, incident_id: None
crud.get_logs_for_incident = lambda db, incident: []
crud.get_similar_incidents = lambda db, incident, limit=5: []
crud.create_log_entry = lambda db, log: log

client = TestClient(api_main.app)
SECRET = os.environ["JWT_SECRET"]


def _token(role):
    return ll_auth.create_token(SECRET, "u", role)


class TestApiSecurityAndObservability(unittest.TestCase):
    def setUp(self):
        # Fresh, generous limiter per test so rate limiting doesn't interfere
        # with auth/RBAC assertions (rate limiting is tested separately).
        api_main.rate_limiter = __import__(
            "loglens.ratelimit", fromlist=["RateLimiter"]
        ).RateLimiter(rate=1000, per=1)

    def test_health_public(self):
        r = client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_metrics_public_and_scrapable(self):
        r = client.get("/metrics")
        self.assertEqual(r.status_code, 200)
        self.assertIn("http_requests_total", r.text)

    def test_protected_requires_auth(self):
        self.assertEqual(client.get("/incidents/").status_code, 401)
        self.assertEqual(
            client.get("/incidents/", headers={"Authorization": "Bearer bad.token"}).status_code,
            401,
        )

    def test_viewer_can_read(self):
        tok = _token("viewer")
        r = client.get("/incidents/", headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(r.status_code, 200)

    def test_rate_limit_returns_429(self):
        tok = _token("viewer")
        api_main.rate_limiter = __import__(
            "loglens.ratelimit", fromlist=["RateLimiter"]
        ).RateLimiter(rate=2, per=1)
        codes = [
            client.get("/incidents/", headers={"Authorization": f"Bearer {tok}"}).status_code
            for _ in range(6)
        ]
        self.assertIn(429, codes)
