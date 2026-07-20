"""Evidence retrieval for the AI service.

Assembles a bounded, explicitly retrieved context from three sources before any
LLM call (per AGENT.md retrieval pipeline):
  1. Incident timeline (PostgreSQL log_entries via incident.log_ids).
  2. Semantic neighbours (Qdrant vector search over the log collection).
  3. Similar historical incidents (incident feature-vector similarity).

The AI service reads from the DB directly and from Qdrant; it never calls the
LLM over the full log history.
"""

import os
import json
from typing import List, Dict, Any, Optional

from .database import SessionLocal, Incident, LogEntry


def _parse_ids(raw: str) -> List[int]:
    return [int(i) for i in (raw or "").split(",") if i.strip()]


def get_incident_dict(db, incident_id: int) -> Optional[Dict[str, Any]]:
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        return None
    return {
        "id": inc.id,
        "title": inc.title,
        "severity": inc.severity,
        "severity_label": inc.severity_label,
        "status": inc.status,
        "services": inc.services,
        "log_count": inc.log_count,
        "log_ids": _parse_ids(inc.log_ids),
        "feature_vector": inc.feature_vector,
        "start_time": inc.start_time,
        "end_time": inc.end_time,
    }


def get_timeline(db, incident: Dict[str, Any], max_logs: int = 200) -> List[Dict[str, Any]]:
    ids = incident.get("log_ids") or []
    if not ids:
        return []
    rows = (
        db.query(LogEntry)
        .filter(LogEntry.id.in_(ids))
        .order_by(LogEntry.timestamp.asc())
        .limit(max_logs)
        .all()
    )
    return [
        {
            "id": r.id,
            "timestamp": r.timestamp,
            "service_name": r.service_name,
            "level": r.level,
            "message": r.message,
            "trace_id": r.trace_id,
        }
        for r in rows
    ]


def get_similar_incidents(db, incident_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        return []
    target = {}
    if inc.feature_vector:
        try:
            target = json.loads(inc.feature_vector)
        except (json.JSONDecodeError, TypeError):
            target = {}

    rows = db.query(
        Incident.id,
        Incident.title,
        Incident.severity,
        Incident.services,
        Incident.start_time,
        Incident.feature_vector,
    ).all()
    scored = []
    for r_id, title, severity, services, start_time, fv in rows:
        if r_id == incident_id:
            continue
        vec = {}
        if fv:
            try:
                vec = json.loads(fv)
            except (json.JSONDecodeError, TypeError):
                continue
        sim = _cosine(target, vec)
        if sim <= 0:
            continue
        scored.append(
            {
                "id": r_id,
                "title": title,
                "severity": severity,
                "services": [s for s in (services or "").split(",") if s],
                "start_time": start_time,
                "similarity": sim,
            }
        )
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:limit]


def semantic_neighbours(query_text: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Optional semantic context via Qdrant. Returns [] if unavailable."""
    try:
        from sentence_transformers import SentenceTransformer
        from qdrant_client import QdrantClient
    except ImportError:
        return []

    host = os.getenv("QDRANT_HOST", "qdrant")
    port = int(os.getenv("QDRANT_PORT", 6333))
    collection = os.getenv("QDRANT_COLLECTION", "log_collection")
    try:
        model = SentenceTransformer(os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2"))
        client = QdrantClient(host=host, port=port)
        vector = model.encode(query_text).tolist()
        hits = client.search(collection_name=collection, query_vector=vector, limit=limit)
    except Exception:
        return []
    results = []
    for h in hits:
        payload = dict(h.payload or {})
        results.append(
            {
                "id": getattr(h, "id", None),
                "score": getattr(h, "score", None),
                "payload": payload,
            }
        )
    return results


def _cosine(a: dict, b: dict) -> float:
    import math

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


def assemble_evidence(
    incident_id: int,
    max_logs: int = 200,
    similar_limit: int = 5,
    include_semantic: bool = True,
) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        incident = get_incident_dict(db, incident_id)
        if not incident:
            return {"incident": None, "timeline": [], "similar": [], "semantic": []}
        timeline = get_timeline(db, incident, max_logs=max_logs)
        similar = get_similar_incidents(db, incident_id, limit=similar_limit)
        semantic = []
        if include_semantic and timeline:
            # Build a query from the incident's error messages.
            q = (
                " ".join(
                    t["message"] for t in timeline if t["level"] in ("ERROR", "CRITICAL", "FATAL")
                )
                or incident["title"]
            )
            semantic = semantic_neighbours(q, limit=5)
        return {
            "incident": incident,
            "timeline": timeline,
            "similar": similar,
            "semantic": semantic,
        }
    finally:
        db.close()
