"""Modular, reusable prompt construction for the AI investigation pipeline.

Each function returns a discrete message (system or user) so prompts can be
composed, tested, and reused independently. The central rule is groundedness:
the model may only use the provided context and must cite evidence.
"""

from datetime import datetime
from typing import List, Dict, Any


GROUNDING_SYSTEM = (
    "You are an incident investigation assistant for engineers. "
    "You are NOT the source of truth. You must ONLY use the evidence provided "
    "in the context below. Never invent log lines, timestamps, services, error "
    "messages, incident IDs, or root causes that are not present in the context. "
    "If the provided evidence is insufficient to answer, you must explicitly say "
    "so rather than speculate. When you make a claim, reference the evidence item "
    "IDs (e.g. [log:12], [incident:3]) that support it."
)


def system_prompt() -> Dict[str, str]:
    return {"role": "system", "content": GROUNDING_SYSTEM}


def build_context_block(
    incident: Dict[str, Any],
    timeline: List[Dict[str, Any]],
    similar: List[Dict[str, Any]],
) -> str:
    lines: List[str] = []
    lines.append("=== INCIDENT ===")
    lines.append(f"id: {incident.get('id')}")
    lines.append(f"title: {incident.get('title')}")
    lines.append(f"severity: {incident.get('severity')} ({incident.get('severity_label')})")
    lines.append(f"services: {incident.get('services')}")
    lines.append(f"status: {incident.get('status')}")
    lines.append(f"start: {incident.get('start_time')}")
    lines.append(f"end: {incident.get('end_time')}")

    lines.append("\n=== TIMELINE LOGS ===")
    for i, log in enumerate(timeline):
        ts = log.get("timestamp")
        if isinstance(ts, datetime):
            ts = ts.isoformat()
        lines.append(
            f"[log:{log.get('id')}] {ts} service={log.get('service_name')} "
            f"level={log.get('level')} message={log.get('message')}"
        )

    lines.append("\n=== SIMILAR HISTORICAL INCIDENTS ===")
    if similar:
        for s in similar:
            lines.append(
                f"[incident:{s.get('id')}] title={s.get('title')} "
                f"severity={s.get('severity')} similarity={s.get('similarity')} "
                f"services={s.get('services')}"
            )
    else:
        lines.append("(none)")

    return "\n".join(lines)


def summarize_user_prompt(context: str) -> Dict[str, str]:
    return {
        "role": "user",
        "content": (
            "Using only the context above, write a concise plain-language summary "
            "of what happened in this incident. Cite the evidence item IDs that "
            "support your summary.\n\n" + context
        ),
    }


def investigate_user_prompt(context: str) -> Dict[str, str]:
    return {
        "role": "user",
        "content": (
            "Using only the context above, do the following:\n"
            "1. Summarize the incident in 2-3 sentences, citing evidence IDs.\n"
            "2. Propose the most likely root cause(s), citing the specific logs or "
            "similar incidents that support each hypothesis.\n"
            "3. State a confidence level (low/medium/high) and explain why.\n"
            "4. If the evidence is insufficient to determine a root cause, say so "
            "explicitly instead of guessing.\n\n" + context
        ),
    }


def parse_investigation(text: str) -> Dict[str, Any]:
    """Best-effort structured parse of the model's investigation text.

    We do not hardcode provider output format; we extract lightweight signals so
    the dashboard and tests can verify a response is present and grounded.
    """
    lowered = text.lower()
    confidence = None
    for level in ("high", "medium", "low"):
        if f"confidence: {level}" in lowered or f"confidence level: {level}" in lowered:
            confidence = level
            break
    insufficient = (
        ("insufficient" in lowered and ("evidence" in lowered or "context" in lowered))
        or "cannot determine" in lowered
        or "unable to determine" in lowered
    )
    return {
        "raw": text,
        "confidence": confidence,
        "insufficient_evidence": insufficient,
    }
