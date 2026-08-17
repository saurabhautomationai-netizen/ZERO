"""Structured JSON logging and sensitive secret redaction for ZERO (Milestone M20)."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# Regex patterns to detect and mask sensitive tokens, passwords, and API keys
SENSITIVE_PATTERNS = [
    re.compile(r"(postgres(?:ql)?:\/\/[^:]+:)([^@]+)(@)", re.IGNORECASE),  # DB passwords in URLs
    re.compile(r"(['\"]?(?:api[_-]?key|token|password|secret|auth)['\"]?\s*[:=]\s*['\"])([^'\"]+)(['\"])", re.IGNORECASE),
    re.compile(r"(Bearer\s+)([a-zA-Z0-9_\-\.]{10,})", re.IGNORECASE),
]


def redact_secrets(text: str) -> str:
    """Redacts passwords, tokens, and secrets from log strings."""
    if not isinstance(text, str):
        return text

    redacted = text
    for pattern in SENSITIVE_PATTERNS:
        if "postgres" in pattern.pattern:
            redacted = pattern.sub(r"\1***\3", redacted)
        elif "Bearer" in pattern.pattern:
            redacted = pattern.sub(r"\1***", redacted)
        else:
            redacted = pattern.sub(r"\1***\3", redacted)
    return redacted


def sanitize_data(data: Any) -> Any:
    """Recursively sanitizes dictionary, list, and string data structures."""
    if isinstance(data, str):
        return redact_secrets(data)
    elif isinstance(data, dict):
        return {k: sanitize_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_data(x) for x in data]
    return data


class StructuredLogger:
    """JSON structured event logger with audit trail support."""

    def __init__(self, name: str = "zero", log_level: int = logging.INFO):
        self.name = name
        self.level = log_level
        self._events: List[Dict[str, Any]] = []

    def log(
        self,
        event_type: str,
        message: str,
        level: str = "INFO",
        metadata: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Logs a structured JSON event record."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "logger": self.name,
            "level": level.upper(),
            "event_type": event_type,
            "message": redact_secrets(message),
            "metadata": sanitize_data(metadata or {}),
        }
        if duration_ms is not None:
            event["duration_ms"] = round(duration_ms, 2)

        self._events.append(event)
        return event

    def info(self, event_type: str, message: str, **kwargs) -> Dict[str, Any]:
        return self.log(event_type=event_type, message=message, level="INFO", metadata=kwargs)

    def warning(self, event_type: str, message: str, **kwargs) -> Dict[str, Any]:
        return self.log(event_type=event_type, message=message, level="WARNING", metadata=kwargs)

    def error(self, event_type: str, message: str, **kwargs) -> Dict[str, Any]:
        return self.log(event_type=event_type, message=message, level="ERROR", metadata=kwargs)

    def get_events(self, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns recorded events, optionally filtered by event_type."""
        if event_type is None:
            return list(self._events)
        return [e for e in self._events if e["event_type"] == event_type]

    def clear(self) -> None:
        self._events.clear()


# Global default logger singleton
DEFAULT_LOGGER = StructuredLogger()
