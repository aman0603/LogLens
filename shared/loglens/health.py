"""Standardized health and readiness endpoints.

Liveness (/health): the process is up. Readiness (/ready): the process can serve
traffic (e.g. dependencies reachable). Each service composes these into its app.
"""

from typing import Callable, Dict, Any


def health_response() -> Dict[str, Any]:
    return {"status": "ok"}


def readiness_response(checks: Dict[str, Callable[[], bool]] = None) -> Dict[str, Any]:
    checks = checks or {}
    results = {}
    ready = True
    for name, fn in checks.items():
        try:
            ok = bool(fn())
        except Exception:
            ok = False
        results[name] = "ok" if ok else "unavailable"
        ready = ready and ok
    return {"status": "ok" if ready else "degraded", "dependencies": results}
