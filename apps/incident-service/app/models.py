from sqlalchemy import Column, Integer, String, DateTime, Text, Float, func
from .database import Base


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    severity = Column(Float, nullable=False, default=0.0)
    severity_label = Column(String, nullable=False, default="low")
    status = Column(String, nullable=False, default="open")
    services = Column(Text, nullable=False, default="")  # comma-separated
    log_count = Column(Integer, nullable=False, default=0)
    log_ids = Column(Text, nullable=False, default="")  # comma-separated int IDs
    feature_vector = Column(Text, nullable=True)  # JSON-encoded TF-IDF features
    created_at = Column(DateTime(timezone=True), server_default=func.now())
