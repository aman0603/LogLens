"""Standardized structured JSON logging.

Every service emits JSON log lines that include at minimum: timestamp, service,
level, message, and the correlation context (request_id, correlation_id,
trace_id) when available. A contextvar carries the IDs across async/sync calls
so they appear consistently without threading them through every function.
"""

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Optional

_correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)
_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_trace_id: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)


def set_correlation_ids(
    request_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    trace_id: Optional[str] = None,
):
    """Set the active correlation context. Returns the token(s) for reset."""
    if request_id is not None:
        _request_id.set(request_id)
    if correlation_id is not None:
        _correlation_id.set(correlation_id)
    if trace_id is not None:
        _trace_id.set(trace_id)


def get_correlation_ids() -> dict:
    return {
        "request_id": _request_id.get(),
        "correlation_id": _correlation_id.get(),
        "trace_id": _trace_id.get(),
    }


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "service": getattr(record, "service", "unknown"),
            "level": record.levelname,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "correlation_id": getattr(record, "correlation_id", None),
            "trace_id": getattr(record, "trace_id", None),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def get_logger(service: str, level: str = "INFO") -> logging.Logger:
    """Return a logger that emits structured JSON with service + correlation IDs."""
    logger = logging.getLogger(service)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Inject correlation fields into every record.
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.service = service
        ids = get_correlation_ids()
        record.request_id = ids["request_id"]
        record.correlation_id = ids["correlation_id"]
        record.trace_id = ids["trace_id"]
        return record

    logging.setLogRecordFactory(record_factory)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger


def new_request_id() -> str:
    return uuid.uuid4().hex
