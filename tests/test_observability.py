from __future__ import annotations

import time
import pytest

from zero_core.observability import (
    DEFAULT_LOGGER,
    DEFAULT_TRACER,
    StructuredLogger,
    Tracer,
    redact_secrets,
    sanitize_data,
)


def test_secret_redaction():
    db_url = "postgresql://zero_user:SuperSecretPassword123@localhost:5432/finance_db"
    redacted_url = redact_secrets(db_url)
    assert "SuperSecretPassword123" not in redacted_url
    assert "postgresql://zero_user:***@localhost:5432/finance_db" == redacted_url

    bearer_str = "Authorization: Bearer my_secret_jwt_token_9999"
    assert "my_secret_jwt_token_9999" not in redact_secrets(bearer_str)

    data = {
        "url": db_url,
        "nested": [{"auth": "token=secret_abc_123"}],
    }
    sanitized = sanitize_data(data)
    assert "SuperSecretPassword123" not in sanitized["url"]


def test_structured_logger_event_recording():
    logger = StructuredLogger(name="test_logger")
    assert len(logger.get_events()) == 0

    event = logger.info(
        event_type="TASK_ROUTED",
        message="Task routed to Finance Agent",
        task="What did I spend?",
        selected="native/finance-agent",
    )
    assert event["event_type"] == "TASK_ROUTED"
    assert event["level"] == "INFO"
    assert event["metadata"]["selected"] == "native/finance-agent"

    # Log error
    logger.error(
        event_type="DB_ERROR",
        message="Connection failed to postgresql://user:pass123@host/db",
    )
    events = logger.get_events()
    assert len(events) == 2
    assert "pass123" not in events[1]["message"]


def test_tracer_span_measurement():
    tracer = Tracer()

    with tracer.span("orchestrator_routing", task="test_task") as s:
        time.sleep(0.01)  # 10ms work
        assert s.status == "IN_PROGRESS"

    spans = tracer.get_spans("orchestrator_routing")
    assert len(spans) == 1
    assert spans[0].status == "SUCCESS"
    assert spans[0].duration_ms is not None
    assert spans[0].duration_ms >= 5.0

    avg_dur = tracer.get_average_duration("orchestrator_routing")
    assert avg_dur is not None and avg_dur >= 5.0


def test_tracer_handles_exception_and_records_error():
    tracer = Tracer()

    with pytest.raises(ValueError, match="Simulated execution failure"):
        with tracer.span("faulty_adapter_call"):
            raise ValueError("Simulated execution failure")

    spans = tracer.get_spans("faulty_adapter_call")
    assert len(spans) == 1
    assert spans[0].status == "ERROR"
    assert "Simulated execution failure" in spans[0].error
