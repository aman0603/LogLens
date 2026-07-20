from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class LogEntryBase(BaseModel):
    service_name: str
    level: str
    message: str
    trace_id: Optional[str] = None
    span_id: Optional[str] = None


class LogEntryCreate(LogEntryBase):
    pass


class LogEntryRead(LogEntryBase):
    id: Optional[int]
    timestamp: datetime

    class Config:
        orm_mode = True


class IncidentRead(BaseModel):
    id: int
    title: str
    start_time: datetime
    end_time: datetime
    severity: float
    severity_label: str
    status: str
    services: List[str] = []
    log_count: int
    log_ids: List[int] = []
    feature_vector: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class SimilarIncident(BaseModel):
    id: int
    title: str
    severity: float
    services: List[str]
    start_time: datetime
    similarity: float
