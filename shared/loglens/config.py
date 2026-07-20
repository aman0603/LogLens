"""Centralized configuration loading and validation.

Every service imports ``load_config`` with a schema of required/optional
variables. Missing required vars or invalid values raise ``ConfigError`` at
startup (fail-fast) so misconfiguration is caught before the service accepts
traffic. This removes duplicated ``os.getenv`` logic across services.
"""

import os
from typing import Any, Dict, List, Optional, Callable


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


def _coerce(value: str, cast: Callable[[str], Any]) -> Any:
    try:
        return cast(value)
    except (ValueError, TypeError) as e:
        raise ConfigError(f"Invalid configuration value: {e}") from e


class Config:
    """Typed accessor over a validated environment mapping."""

    def __init__(self, values: Dict[str, Any]):
        self._values = values

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def require(self, key: str) -> Any:
        if key not in self._values or self._values[key] is None:
            raise ConfigError(f"Required environment variable not set: {key}")
        return self._values[key]

    def __getitem__(self, key: str) -> Any:
        return self.require(key)

    def as_dict(self) -> Dict[str, Any]:
        return dict(self._values)


def load_config(
    required: Optional[List[str]] = None,
    optional: Optional[Dict[str, Any]] = None,
    casts: Optional[Dict[str, Callable[[str], Any]]] = None,
    source: Optional[Dict[str, str]] = None,
) -> Config:
    """Load and validate configuration from the environment.

    Args:
        required: env var names that must be present and non-empty.
        optional: env var name -> default value when absent.
        casts: env var name -> callable to coerce the raw string.
        source: override mapping (defaults to os.environ); used by tests.
    """
    env = source if source is not None else dict(os.environ)
    required = required or []
    optional = optional or {}
    casts = casts or {}

    values: Dict[str, Any] = {}

    for key in required:
        raw = env.get(key)
        if raw is None or raw == "":
            raise ConfigError(f"Required environment variable not set: {key}")
        values[key] = _coerce(raw, casts[key]) if key in casts else raw

    for key, default in optional.items():
        raw = env.get(key)
        if raw is None or raw == "":
            values[key] = default
        else:
            values[key] = _coerce(raw, casts[key]) if key in casts else raw

    # Apply casts to values that were provided but not covered above.
    for key, cast in casts.items():
        if key in values and not isinstance(values[key], (str,)):
            continue
        if key in values:
            values[key] = _coerce(values[key], cast)

    return Config(values)
