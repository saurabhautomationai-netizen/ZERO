"""Execution tracing and telemetry metrics for ZERO (Milestone M20)."""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional


@dataclass
class TraceSpan:
    """Represents a measured execution span."""
    span_id: str
    name: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    status: str = "IN_PROGRESS"  # 'SUCCESS', 'ERROR', 'IN_PROGRESS'
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def finish(self, status: str = "SUCCESS", error: Optional[str] = None) -> None:
        self.end_time = time.perf_counter()
        self.duration_ms = round((self.end_time - self.start_time) * 1000, 2)
        self.status = status
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Tracer:
    """Telemetry tracer collecting execution duration spans across ZERO modules."""

    def __init__(self):
        self._spans: List[TraceSpan] = []
        self._span_counter = 0

    @contextmanager
    def span(self, name: str, **metadata) -> Generator[TraceSpan, None, None]:
        """Context manager to measure and record execution duration of an operation."""
        self._span_counter += 1
        span_id = f"span_{self._span_counter:04d}"
        s = TraceSpan(
            span_id=span_id,
            name=name,
            start_time=time.perf_counter(),
            metadata=metadata,
        )
        self._spans.append(s)
        try:
            yield s
            s.finish(status="SUCCESS")
        except Exception as exc:
            s.finish(status="ERROR", error=str(exc))
            raise

    def get_spans(self, name: Optional[str] = None) -> List[TraceSpan]:
        """Returns recorded trace spans."""
        if name is None:
            return list(self._spans)
        return [s for s in self._spans if s.name == name]

    def get_average_duration(self, name: str) -> Optional[float]:
        """Calculates average duration in milliseconds for a span name."""
        matching = [s.duration_ms for s in self.get_spans(name) if s.duration_ms is not None]
        if not matching:
            return None
        return round(sum(matching) / len(matching), 2)

    def clear(self) -> None:
        self._spans.clear()
        self._span_counter = 0


# Global default tracer singleton
DEFAULT_TRACER = Tracer()
