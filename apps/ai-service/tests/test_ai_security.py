import sys
import os
import types
import unittest

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared"
    ),
)

for name in ("sentence_transformers", "qdrant_client", "qdrant_client.models"):
    if name not in sys.modules:
        m = types.ModuleType(name)
        if name == "sentence_transformers":
            m.SentenceTransformer = object
        elif name == "qdrant_client":
            m.QdrantClient = object
        elif name == "qdrant_client.models":
            m.Distance = object
        sys.modules[name] = m

os.environ.setdefault("JWT_SECRET", "test-secret")
# Use a file-based sqlite DB so all connections share the same schema.
import tempfile

_db_file = os.path.join(tempfile.gettempdir(), "loglens_ai_test.db")
if os.path.exists(_db_file):
    os.remove(_db_file)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_file}"

from fastapi.testclient import TestClient
from app import main as ai_main
from loglens import auth as ll_auth

import app.database as db_mod

db_mod.Base.metadata.create_all(bind=db_mod.engine)


def _fake_get_db():
    from sqlalchemy.orm import Session

    yield Session(bind=db_mod.engine)


ai_main.get_db = _fake_get_db

# Make the LLM client a no-op so investigate/summarize don't call out.
import app.llm as llm_mod


class _FakeLLM:
    def chat(self, messages):
        return "Summary: ok [log:1]\nConfidence: medium"


llm_mod.LLMClient = lambda *a, **k: _FakeLLM()

client = TestClient(ai_main.app)
SECRET = os.environ["JWT_SECRET"]


def _token(role):
    return ll_auth.create_token(SECRET, "u", role)


class TestAiServiceSecurity(unittest.TestCase):
    def setUp(self):
        ai_main.rate_limiter = __import__(
            "loglens.ratelimit", fromlist=["RateLimiter"]
        ).RateLimiter(rate=1000, per=1)

    def test_health_ready_metrics_public(self):
        self.assertEqual(client.get("/health").status_code, 200)
        self.assertEqual(client.get("/ready").status_code, 200)
        self.assertIn("http_requests_total", client.get("/metrics").text)

    def test_ai_requires_auth(self):
        self.assertEqual(client.post("/ai/incident/1/summarize").status_code, 401)

    def test_rbac_viewer_forbidden_analyst_required(self):
        tok = _token("viewer")
        r = client.post("/ai/incident/1/summarize", headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(r.status_code, 403)
        tok_a = _token("analyst")
        r2 = client.post("/ai/incident/1/summarize", headers={"Authorization": f"Bearer {tok_a}"})
        # 404 (no incident) or 200 — but not 401/403 (auth passed).
        self.assertIn(r2.status_code, (200, 404, 502))

    def test_rate_limit_returns_429(self):
        tok = _token("analyst")
        ai_main.rate_limiter = __import__(
            "loglens.ratelimit", fromlist=["RateLimiter"]
        ).RateLimiter(rate=2, per=1)
        codes = [
            client.post(
                "/ai/incident/1/summarize", headers={"Authorization": f"Bearer {tok}"}
            ).status_code
            for _ in range(6)
        ]
        self.assertIn(429, codes)


if __name__ == "__main__":
    unittest.main()
