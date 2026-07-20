"""Rule-based incident detection, severity scoring, and feature vectors.

Pure, framework-independent logic so it can be unit-tested without Kafka or a DB.
"""

import math
from collections import Counter
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

LEVEL_WEIGHT = {
    "DEBUG": 0.0,
    "INFO": 0.1,
    "WARN": 0.5,
    "WARNING": 0.5,
    "ERROR": 1.0,
    "CRITICAL": 1.5,
    "FATAL": 1.5,
}


def normalize_service(raw: Dict[str, Any]) -> str:
    return raw.get("service_name") or raw.get("service") or "unknown"


def normalize_log(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce a Kafka log message into a canonical shape."""
    ts = raw.get("timestamp")
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            ts = datetime.now(timezone.utc)
    elif ts is None:
        ts = datetime.now(timezone.utc)
    return {
        "id": raw.get("id"),
        "service": normalize_service(raw),
        "level": (raw.get("level") or "INFO").upper(),
        "message": raw.get("message", ""),
        "timestamp": ts,
    }


def tokenize(text: str) -> List[str]:
    return [t for t in text.lower().split() if t]


def build_feature_vector(logs: List[Dict[str, Any]]) -> Dict[str, float]:
    """TF-IDF-ish feature vector over message tokens.

    Uses term frequency within the incident (relative to the max term
    frequency) weighted by inverse document frequency across the incident's
    message set. Stored as {token: weight} for similarity comparison.
    """
    docs = [tokenize(l["message"]) for l in logs]
    df: Counter[str] = Counter()
    for d in docs:
        for term in set(d):
            df[term] += 1

    n_docs = max(len(docs), 1)
    tf: Counter[str] = Counter()
    for d in docs:
        tf.update(d)
    max_tf = max(tf.values()) if tf else 1

    vector: Dict[str, float] = {}
    for term, count in tf.items():
        tf_norm = 0.5 + 0.5 * (count / max_tf)
        idf = math.log((n_docs + 1) / (df[term] + 1)) + 1.0
        vector[term] = round(tf_norm * idf, 4)
    return vector


def cosine_similarity(a: Dict[str, float], b: Dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    if not common:
        return 0.0
    dot = sum(a[t] * b[t] for t in common)
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return round(dot / (mag_a * mag_b), 4)


def compute_severity(logs: List[Dict[str, Any]]) -> tuple:
    """Return (score 0..1, label)."""
    if not logs:
        return 0.0, "low"

    level_scores = [LEVEL_WEIGHT.get(l["level"], 0.1) for l in logs]
    avg_level = sum(level_scores) / len(level_scores)

    error_ratio = sum(1 for s in level_scores if s >= 1.0) / len(level_scores)

    # More distinct impacted services raises severity.
    services = {l["service"] for l in logs}
    service_factor = min(len(services) / 3.0, 1.0)

    # Burst density: many logs in a short window raises severity.
    times = sorted(l["timestamp"] for l in logs if l["timestamp"])
    density_factor = 0.0
    if len(times) >= 2:
        span = (times[-1] - times[0]).total_seconds()
        if span <= 0:
            density_factor = 1.0
        else:
            rate = len(times) / max(span / 60.0, 1.0)  # logs per minute
            density_factor = min(rate / 10.0, 1.0)

    score = 0.45 * avg_level + 0.25 * error_ratio + 0.15 * service_factor + 0.15 * density_factor
    score = min(max(score, 0.0), 1.0)

    if score >= 0.7:
        label = "critical"
    elif score >= 0.45:
        label = "high"
    elif score >= 0.2:
        label = "medium"
    else:
        label = "low"
    return round(score, 4), label


def build_incident_from_logs(
    logs: List[Dict[str, Any]], title: Optional[str] = None
) -> Dict[str, Any]:
    """Aggregate a set of canonical logs into an incident payload dict."""
    times = sorted(l["timestamp"] for l in logs if l["timestamp"])
    start = times[0] if times else datetime.now(timezone.utc)
    end = times[-1] if times else datetime.now(timezone.utc)
    services = sorted({l["service"] for l in logs})
    severity, label = compute_severity(logs)
    feature = build_feature_vector(logs)
    log_ids = [l["id"] for l in logs if l["id"] is not None]

    if not title:
        top_service = services[0] if services else "unknown"
        err_count = sum(1 for l in logs if l["level"] in ("ERROR", "CRITICAL", "FATAL"))
        title = f"{top_service}: {err_count} error(s) across {len(services)} service(s)"

    return {
        "title": title,
        "start_time": start,
        "end_time": end,
        "severity": severity,
        "severity_label": label,
        "status": "open",
        "services": services,
        "log_count": len(logs),
        "log_ids": log_ids,
        "feature_vector": feature,
    }
