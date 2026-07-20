import sys
import os
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import prompts


class FakeLLM:
    """Records the messages it receives; returns a canned grounded answer."""

    def __init__(self):
        self.last_messages = None

    def chat(self, messages):
        self.last_messages = messages
        return (
            "Summary: payment-service had repeated DB timeouts. [log:1][log:2]\n"
            "Root cause: saturated connection pool during peak. [incident:3]\n"
            "Confidence: medium"
        )


class TestPrompts(unittest.TestCase):
    def _incident(self):
        return {
            "id": 1,
            "title": "payment timeout",
            "severity": 0.8,
            "severity_label": "high",
            "status": "open",
            "services": "payment",
            "start_time": datetime.now(timezone.utc),
            "end_time": datetime.now(timezone.utc),
        }

    def _timeline(self):
        return [
            {
                "id": 1,
                "timestamp": datetime.now(timezone.utc),
                "service_name": "payment",
                "level": "ERROR",
                "message": "db timeout",
            },
            {
                "id": 2,
                "timestamp": datetime.now(timezone.utc),
                "service_name": "payment",
                "level": "ERROR",
                "message": "db timeout retry",
            },
        ]

    def _similar(self):
        return [
            {
                "id": 3,
                "title": "past outage",
                "severity": 0.7,
                "services": ["payment"],
                "start_time": datetime.now(timezone.utc),
                "similarity": 0.9,
            }
        ]

    def test_system_prompt_forbids_fabrication(self):
        sys_p = prompts.system_prompt()
        self.assertEqual(sys_p["role"], "system")
        self.assertIn("ONLY use the evidence", sys_p["content"])
        self.assertIn("never invent", sys_p["content"].lower())

    def test_context_block_includes_evidence_ids(self):
        ctx = prompts.build_context_block(self._incident(), self._timeline(), self._similar())
        self.assertIn("[log:1]", ctx)
        self.assertIn("[log:2]", ctx)
        self.assertIn("[incident:3]", ctx)
        self.assertIn("payment", ctx)

    def test_summarize_prompt_mentions_context(self):
        ctx = prompts.build_context_block(self._incident(), self._timeline(), self._similar())
        msg = prompts.summarize_user_prompt(ctx)
        self.assertEqual(msg["role"], "user")
        self.assertIn("context", msg["content"])

    def test_investigate_prompt_requests_root_cause(self):
        ctx = prompts.build_context_block(self._incident(), self._timeline(), self._similar())
        msg = prompts.investigate_user_prompt(ctx)
        self.assertIn("root cause", msg["content"].lower())

    def test_parse_investigation_confidence_and_insufficient(self):
        parsed = prompts.parse_investigation("Confidence: medium blah")
        self.assertEqual(parsed["confidence"], "medium")
        self.assertFalse(parsed["insufficient_evidence"])

        parsed2 = prompts.parse_investigation(
            "The evidence is insufficient to determine a root cause."
        )
        self.assertTrue(parsed2["insufficient_evidence"])


class TestOrchestrationWithMockLLM(unittest.TestCase):
    def test_summarize_uses_assembled_context(self):
        from app import investigate, schemas

        fake = FakeLLM()
        # Patch retrieval to avoid DB/Qdrant.
        import app.retrieval as retrieval

        retrieval.assemble_evidence = (
            lambda inc_id, max_logs=200, similar_limit=5, include_semantic=True: {
                "incident": {
                    "id": inc_id,
                    "title": "t",
                    "severity": 0.5,
                    "severity_label": "low",
                    "status": "open",
                    "services": "x",
                    "start_time": None,
                    "end_time": None,
                },
                "timeline": [
                    {
                        "id": 1,
                        "timestamp": None,
                        "service_name": "x",
                        "level": "ERROR",
                        "message": "boom",
                    }
                ],
                "similar": [
                    {
                        "id": 3,
                        "title": "past",
                        "severity": 0.4,
                        "services": ["x"],
                        "start_time": None,
                        "similarity": 0.8,
                    }
                ],
                "semantic": [],
            }
        )
        resp = investigate.summarize_incident(1, schemas.AIRequest(), fake)
        self.assertIn("[log:1]", resp.summary)
        # Verify the LLM was sent the grounding system prompt + context.
        roles = [m["role"] for m in fake.last_messages]
        self.assertEqual(roles, ["system", "user"])
        self.assertIn("[incident:3]", fake.last_messages[1]["content"])

    def test_investigate_returns_cited_evidence(self):
        from app import investigate, schemas

        fake = FakeLLM()
        import app.retrieval as retrieval

        retrieval.assemble_evidence = (
            lambda inc_id, max_logs=200, similar_limit=5, include_semantic=True: {
                "incident": {
                    "id": inc_id,
                    "title": "t",
                    "severity": 0.5,
                    "severity_label": "low",
                    "status": "open",
                    "services": "x",
                    "start_time": None,
                    "end_time": None,
                },
                "timeline": [
                    {
                        "id": 1,
                        "timestamp": None,
                        "service_name": "x",
                        "level": "ERROR",
                        "message": "boom",
                    }
                ],
                "similar": [
                    {
                        "id": 3,
                        "title": "past",
                        "severity": 0.4,
                        "services": ["x"],
                        "start_time": None,
                        "similarity": 0.8,
                    }
                ],
                "semantic": [],
            }
        )
        resp = investigate.investigate_incident(1, schemas.AIRequest(), fake)
        self.assertEqual(resp.confidence, "medium")
        self.assertFalse(resp.insufficient_evidence)
        ev_ids = [e.ref_id for e in resp.evidence]
        self.assertIn(1, ev_ids)
        self.assertIn(3, ev_ids)


if __name__ == "__main__":
    unittest.main()
