"""Orchestration: assemble evidence, build prompts, call the LLM, parse results.

Keeps the no-fabrication guarantee by only passing retrieved context to the
model and by attaching evidence references to every response.
"""

from typing import Dict, Any, List
from . import retrieval, prompts, schemas
from .llm import LLMClient


def _to_evidence(
    timeline: List[Dict[str, Any]], similar: List[Dict[str, Any]]
) -> List[schemas.EvidenceItem]:
    items: List[schemas.EvidenceItem] = []
    for log in timeline:
        items.append(
            schemas.EvidenceItem(
                kind="log",
                ref_id=log["id"],
                snippet=f"{log.get('service_name')} {log.get('level')}: {log.get('message')}",
            )
        )
    for s in similar:
        items.append(
            schemas.EvidenceItem(
                kind="incident",
                ref_id=s["id"],
                snippet=f"{s.get('title')} (similarity {s.get('similarity')})",
            )
        )
    return items


def summarize_incident(
    incident_id: int, req: schemas.AIRequest, llm: LLMClient
) -> schemas.SummaryResponse:
    evidence = retrieval.assemble_evidence(
        incident_id,
        max_logs=req.max_logs or 200,
        similar_limit=req.similar_limit or 5,
    )
    incident = evidence["incident"]
    if incident is None:
        raise ValueError(f"Incident {incident_id} not found")

    context = prompts.build_context_block(incident, evidence["timeline"], evidence["similar"])
    messages = [prompts.system_prompt(), prompts.summarize_user_prompt(context)]
    text = llm.chat(messages)

    return schemas.SummaryResponse(
        incident_id=incident_id,
        summary=text,
        evidence=_to_evidence(evidence["timeline"], evidence["similar"]),
    )


def investigate_incident(
    incident_id: int, req: schemas.AIRequest, llm: LLMClient
) -> schemas.InvestigationResponse:
    evidence = retrieval.assemble_evidence(
        incident_id,
        max_logs=req.max_logs or 200,
        similar_limit=req.similar_limit or 5,
    )
    incident = evidence["incident"]
    if incident is None:
        raise ValueError(f"Incident {incident_id} not found")

    context = prompts.build_context_block(incident, evidence["timeline"], evidence["similar"])
    messages = [prompts.system_prompt(), prompts.investigate_user_prompt(context)]
    text = llm.chat(messages)
    parsed = prompts.parse_investigation(text)

    return schemas.InvestigationResponse(
        incident_id=incident_id,
        summary=text,
        root_cause_hypothesis=text,
        evidence=_to_evidence(evidence["timeline"], evidence["similar"]),
        similar_incidents=evidence["similar"],
        confidence=parsed["confidence"],
        insufficient_evidence=parsed["insufficient_evidence"],
    )
