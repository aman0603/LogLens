from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class LogEntryBase(BaseModel):
    service_name: str
    level: str
    message: str
    trace_id: Optional[str] = None
    span_id: Optional[str] = None


class LogEntryCreate(LogEntryBase):
    pass


class LogEntryRead(LogEntryBase):
    id: int
    timestamp: datetime

    class Config:
        orm_mode = True
