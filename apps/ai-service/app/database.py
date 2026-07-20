"""Read-only database access for the AI service.

The AI service only reads evidence; it never writes incidents or logs. The
schema mirrors the api/storage models so queries are stable.
"""

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Float, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://loglens:loglens@postgres:5432/loglens",
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class LogEntry(Base):
    __tablename__ = "log_entries"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    service_name = Column(String, index=True)
    level = Column(String)
    message = Column(Text)
    trace_id = Column(String, index=True, nullable=True)
    span_id = Column(String, index=True, nullable=True)


class Incident(Base):
    __tablename__ = "incidents"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    severity = Column(Float, nullable=False, default=0.0)
    severity_label = Column(String, nullable=False, default="low")
    status = Column(String, nullable=False, default="open")
    services = Column(Text, nullable=False, default="")
    log_count = Column(Integer, nullable=False, default=0)
    log_ids = Column(Text, nullable=False, default="")
    feature_vector = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
