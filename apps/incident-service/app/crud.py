import json
from sqlalchemy.orm import Session
from . import models, schemas


def create_incident(db: Session, incident: schemas.IncidentCreate) -> models.Incident:
    db_incident = models.Incident(
        title=incident.title,
        start_time=incident.start_time,
        end_time=incident.end_time,
        severity=incident.severity,
        severity_label=incident.severity_label,
        status=incident.status,
        services=",".join(incident.services),
        log_count=incident.log_count,
        log_ids=",".join(str(i) for i in incident.log_ids),
        feature_vector=json.dumps(incident.feature_vector) if incident.feature_vector else None,
    )
    db.add(db_incident)
    db.commit()
    db.refresh(db_incident)
    return db_incident


def get_incidents(db: Session, skip: int = 0, limit: int = 100, status: str = None):
    q = db.query(models.Incident)
    if status:
        q = q.filter(models.Incident.status == status)
    return q.order_by(models.Incident.start_time.desc()).offset(skip).limit(limit).all()


def get_incident(db: Session, incident_id: int):
    return db.query(models.Incident).filter(models.Incident.id == incident_id).first()


def get_all_feature_vectors(db: Session):
    """Return (id, feature_vector dict) for all incidents, for similarity."""
    rows = db.query(models.Incident.id, models.Incident.feature_vector).all()
    result = []
    for incident_id, fv in rows:
        if fv:
            try:
                result.append((incident_id, json.loads(fv)))
            except (json.JSONDecodeError, TypeError):
                continue
    return result
