from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class IncidentBase(BaseModel):
    title: str
    start_time: datetime
    end_time: datetime
    severity: float = 0.0
    severity_label: str = "low"
    status: str = "open"
    services: List[str] = []
    log_count: int = 0
    log_ids: List[int] = []


class IncidentCreate(IncidentBase):
    pass


class IncidentRead(IncidentBase):
    id: int
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
