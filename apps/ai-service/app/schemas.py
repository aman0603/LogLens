from pydantic import BaseModel
from typing import List, Optional


class EvidenceItem(BaseModel):
    kind: str  # "log" | "incident"
    ref_id: int
    snippet: str


class SummaryResponse(BaseModel):
    incident_id: int
    summary: str
    evidence: List[EvidenceItem]


class InvestigationResponse(BaseModel):
    incident_id: int
    summary: str
    root_cause_hypothesis: str
    evidence: List[EvidenceItem]
    similar_incidents: List[dict]
    confidence: Optional[str] = None
    insufficient_evidence: bool = False


class AIRequest(BaseModel):
    max_logs: Optional[int] = 200
    similar_limit: Optional[int] = 5
