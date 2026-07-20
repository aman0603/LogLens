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
