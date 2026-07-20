import sys
import os
import unittest
from unittest import mock

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared")
)

from loglens import config, auth, ratelimit, health, kafka_retry


class TestConfig(unittest.TestCase):
    def test_required_missing_fails_fast(self):
        with self.assertRaises(config.ConfigError):
            config.load_config(required=["NOPE"], source={})

    def test_required_present_and_cast(self):
        cfg = config.load_config(required=["PORT"], casts={"PORT": int}, source={"PORT": "8080"})
        self.assertEqual(cfg.require("PORT"), 8080)
        self.assertEqual(cfg["PORT"], 8080)

    def test_optional_default(self):
        cfg = config.load_config(optional={"TIMEOUT": 30}, source={})
        self.assertEqual(cfg.get("TIMEOUT"), 30)

    def test_optional_override_and_invalid_cast(self):
        cfg = config.load_config(optional={"N": 1}, casts={"N": int}, source={"N": "5"})
        self.assertEqual(cfg.get("N"), 5)
        with self.assertRaises(config.ConfigError):
            config.load_config(optional={"N": 1}, casts={"N": int}, source={"N": "abc"})


class TestAuth(unittest.TestCase):
    def setUp(self):
        self.secret = "test-secret"

    def test_create_and_decode(self):
        token = auth.create_token(self.secret, "u1", "analyst")
        payload = auth.decode_token(self.secret, token)
        self.assertEqual(payload["role"], "analyst")
        self.assertEqual(payload["sub"], "u1")

    def test_role_hierarchy(self):
        from fastapi import HTTPException

        # viewer cannot access admin-only endpoint (expect 403 Forbidden).
        viewer_token = auth.create_token(self.secret, "u", "viewer")
        creds = mock.Mock()
        creds.credentials = viewer_token
        with self.assertRaises(HTTPException) as ctx:
            auth.check_authorization(creds, [auth._ROLE_RANK["admin"]], self.secret)
        self.assertEqual(ctx.exception.status_code, 403)

        # analyst can access analyst-or-above endpoint (expect payload).
        analyst_token = auth.create_token(self.secret, "u", "analyst")
        creds2 = mock.Mock()
        creds2.credentials = analyst_token
        payload = auth.check_authorization(creds2, [auth._ROLE_RANK["analyst"]], self.secret)
        self.assertEqual(payload["role"], "analyst")

        # missing token -> 401.
        no_creds = mock.Mock()
        no_creds.credentials = None
        with self.assertRaises(HTTPException) as ctx:
            auth.check_authorization(no_creds, [auth._ROLE_RANK["analyst"]], self.secret)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_invalid_token_raises(self):
        with self.assertRaises(auth.AuthError):
            auth.decode_token(self.secret, "not.a.jwt")

    def test_missing_secret(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                auth.get_secret()


class TestRateLimiter(unittest.TestCase):
    def test_allows_up_to_rate(self):
        rl = ratelimit.RateLimiter(rate=3, per=1)
        for _ in range(3):
            allowed, _ = rl.allow("k")
            self.assertTrue(allowed)
        allowed, retry = rl.allow("k")
        self.assertFalse(allowed)
        self.assertGreaterEqual(retry, 1)

    def test_separate_keys(self):
        rl = ratelimit.RateLimiter(rate=1, per=1)
        self.assertTrue(rl.allow("a")[0])
        self.assertTrue(rl.allow("b")[0])
        self.assertFalse(rl.allow("a")[0])


class TestHealth(unittest.TestCase):
    def test_health_ok(self):
        self.assertEqual(health.health_response(), {"status": "ok"})

    def test_readiness(self):
        checks = {"db": lambda: True, "kafka": lambda: False}
        resp = health.readiness_response(checks)
        self.assertEqual(resp["status"], "degraded")
        self.assertEqual(resp["dependencies"]["db"], "ok")
        self.assertEqual(resp["dependencies"]["kafka"], "unavailable")


class TestKafkaRetry(unittest.TestCase):
    def test_success_no_retry(self):
        calls = []

        def proc(d):
            calls.append(d)

        ok = kafka_retry.with_retry("svc", "logs", b'{"a":1}', proc, producer=None, max_attempts=3)
        self.assertTrue(ok)
        self.assertEqual(len(calls), 1)

    def test_retry_then_success(self):
        state = {"n": 0}

        def proc(d):
            state["n"] += 1
            if state["n"] < 2:
                raise ValueError("transient")
            return None

        ok = kafka_retry.with_retry(
            "svc", "logs", b'{"a":1}', proc, producer=None, max_attempts=3, base_backoff=0
        )
        self.assertTrue(ok)
        self.assertEqual(state["n"], 2)

    def test_exhaustion_routes_to_dlq(self):
        def proc(d):
            raise RuntimeError("poison")

        producer = mock.Mock()
        ok = kafka_retry.with_retry(
            "svc", "logs", b'{"a":1}', proc, producer=producer, max_attempts=2, base_backoff=0
        )
        self.assertTrue(ok)
        producer.produce.assert_called_once()
        self.assertTrue(producer.produce.call_args[0][0].endswith(".dlq"))

    def test_decode_error_to_dlq(self):
        producer = mock.Mock()
        ok = kafka_retry.with_retry("svc", "logs", b"not-json", lambda d: None, producer=producer)
        self.assertFalse(ok)
        producer.produce.assert_called_once()


if __name__ == "__main__":
    unittest.main()
