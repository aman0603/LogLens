"""LogLens shared library.

Reusable, dependency-isolated helpers consumed by every service so configuration,
logging, auth, metrics, tracing, rate limiting, and Kafka retry/DLQ logic are
never duplicated across services. Services add ``shared/`` to their PYTHONPATH
(the Dockerfile copies it into the image; locally set PYTHONPATH=shared).
"""

from . import config
from . import logging as logging_lib
from . import health
from . import metrics
from . import auth
from . import ratelimit
from . import tracing
from . import kafka_retry

__all__ = [
    "config",
    "logging_lib",
    "health",
    "metrics",
    "auth",
    "ratelimit",
    "tracing",
    "kafka_retry",
]
