from sqlalchemy import Column, Integer, String, DateTime, Text, func
from .database import Base


class LogEntry(Base):
    __tablename__ = "log_entries"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    service_name = Column(String, index=True)
    level = Column(String)
    message = Column(Text)
    trace_id = Column(String, index=True, nullable=True)
    span_id = Column(String, index=True, nullable=True)
    # additional fields can be added as JSON
