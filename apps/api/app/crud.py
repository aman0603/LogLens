import json
from sqlalchemy.orm import Session
from . import models, schemas


def create_log_entry(db: Session, log: schemas.LogEntryCreate):
    db_log = models.LogEntry(**log.dict())
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return db_log


def get_logs(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.LogEntry).offset(skip).limit(limit).all()


def get_incidents(db: Session, skip: int = 0, limit: int = 100, status: str = None):
    q = db.query(models.Incident)
    if status:
        q = q.filter(models.Incident.status == status)
    return q.order_by(models.Incident.start_time.desc()).offset(skip).limit(limit).all()


def get_incident(db: Session, incident_id: int):
    return db.query(models.Incident).filter(models.Incident.id == incident_id).first()


def get_logs_for_incident(db: Session, incident: models.Incident):
    ids = [int(i) for i in incident.log_ids.split(",") if i]
    if not ids:
        return []
    return (
        db.query(models.LogEntry)
        .filter(models.LogEntry.id.in_(ids))
        .order_by(models.LogEntry.timestamp.asc())
        .all()
    )


def _parse_vector(raw):
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def get_similar_incidents(db: Session, incident: models.Incident, limit: int = 5):
    target = _parse_vector(incident.feature_vector)
    rows = db.query(
        models.Incident.id,
        models.Incident.title,
        models.Incident.severity,
        models.Incident.services,
        models.Incident.start_time,
        models.Incident.feature_vector,
    ).all()
    scored = []
    for inc_id, title, severity, services, start_time, fv in rows:
        if inc_id == incident.id:
            continue
        vec = _parse_vector(fv)
        sim = _cosine(target, vec)
        if sim <= 0:
            continue
        scored.append(
            {
                "id": inc_id,
                "title": title,
                "severity": severity,
                "services": [s for s in services.split(",") if s],
                "start_time": start_time,
                "similarity": sim,
            }
        )
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:limit]


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
