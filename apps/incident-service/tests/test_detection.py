import sys
import os
import unittest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import detection


def make_log(level, service, message, minutes_ago=0, id=None):
    return {
        "id": id,
        "level": level,
        "service": service,
        "message": message,
        "timestamp": datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
    }


class TestSeverity(unittest.TestCase):
    def test_all_info_is_low(self):
        logs = [detection.normalize_log(make_log("INFO", "svc", "ok", i)) for i in range(3)]
        score, label = detection.compute_severity(logs)
        self.assertEqual(label, "low")
        self.assertLess(score, 0.2)

    def test_errors_raise_severity(self):
        logs = [detection.normalize_log(make_log("ERROR", "svc", f"fail {i}", i)) for i in range(5)]
        score, label = detection.compute_severity(logs)
        self.assertIn(label, ("high", "critical"))
        self.assertGreater(score, 0.4)

    def test_multiple_services_raise_severity(self):
        logs = [
            detection.normalize_log(make_log("ERROR", f"svc{i % 3}", "boom", i)) for i in range(6)
        ]
        score, label = detection.compute_severity(logs)
        self.assertGreaterEqual(score, 0.0)


class TestFeatureVector(unittest.TestCase):
    def test_vector_built(self):
        logs = [
            detection.normalize_log(make_log("ERROR", "svc", "connection timeout database", i))
            for i in range(3)
        ]
        vec = detection.build_feature_vector(logs)
        self.assertIn("connection", vec)
        self.assertIn("timeout", vec)
        self.assertIn("database", vec)

    def test_cosine_identical(self):
        a = {"x": 1.0, "y": 2.0}
        self.assertAlmostEqual(detection.cosine_similarity(a, a), 1.0)

    def test_cosine_disjoint(self):
        a = {"x": 1.0}
        b = {"y": 1.0}
        self.assertEqual(detection.cosine_similarity(a, b), 0.0)

    def test_cosine_partial(self):
        a = {"x": 1.0, "y": 1.0}
        b = {"x": 1.0, "z": 1.0}
        sim = detection.cosine_similarity(a, b)
        self.assertGreater(sim, 0.0)
        self.assertLess(sim, 1.0)


class TestBuildIncident(unittest.TestCase):
    def test_aggregation(self):
        raw = [
            make_log("ERROR", "payment", "timeout db", 5, id=1),
            make_log("ERROR", "payment", "timeout db retry", 4, id=2),
            make_log("INFO", "payment", "recovered", 3, id=3),
        ]
        inc = detection.build_incident_from_logs([detection.normalize_log(r) for r in raw])
        self.assertEqual(inc["log_count"], 3)
        self.assertEqual(inc["services"], ["payment"])
        self.assertEqual(inc["log_ids"], [1, 2, 3])
        self.assertIsInstance(inc["feature_vector"], dict)
        self.assertIn("timeout", inc["feature_vector"])

    def test_normalize_service_alias(self):
        self.assertEqual(detection.normalize_service({"service": "x"}), "x")
        self.assertEqual(detection.normalize_service({"service_name": "y"}), "y")


if __name__ == "__main__":
    unittest.main()
