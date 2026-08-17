from __future__ import annotations

from unittest.mock import MagicMock
from zero_core.approval import ApprovalPolicyEngine
from zero_core.interfaces.telegram.bot import TelegramBotHandler
from zero_core.interfaces.telegram.runner import TelegramBotRunner


def test_telegram_runner_not_configured():
    runner = TelegramBotRunner(token="")
    assert runner.is_configured() is False
    assert runner.poll_once() == 0


def test_telegram_runner_poll_with_mock_api(monkeypatch):
    engine = ApprovalPolicyEngine()
    handler = TelegramBotHandler(approval_engine=engine)
    runner = TelegramBotRunner(token="mock_token_123", handler=handler)

    mock_updates = {
        "ok": True,
        "result": [
            {
                "update_id": 101,
                "message": {
                    "chat": {"id": 12345},
                    "from": {"id": 999},
                    "text": "/status",
                },
            },
            {
                "update_id": 102,
                "callback_query": {
                    "id": "cb_1",
                    "from": {"id": 999},
                    "message": {"chat": {"id": 12345}},
                    "data": "approve:REQ-TEST-1",
                },
            },
        ],
    }

    sent_messages = []

    def mock_api_call(method, data=None):
        if method == "getUpdates":
            return mock_updates
        if method == "sendMessage":
            sent_messages.append(data)
            return {"ok": True}
        if method == "answerCallbackQuery":
            return {"ok": True}
        return {"ok": True}

    monkeypatch.setattr(runner, "_api_call", mock_api_call)

    processed = runner.poll_once()
    assert processed == 2
    assert runner.last_update_id == 102
    assert len(sent_messages) >= 1


def test_telegram_runner_unauthorized_user_rejection(monkeypatch):
    runner = TelegramBotRunner(token="mock_token_123", allowed_user_ids=["allowed_user_1"])

    mock_updates = {
        "ok": True,
        "result": [
            {
                "update_id": 201,
                "message": {
                    "chat": {"id": 12345},
                    "from": {"id": "unauthorized_hacker"},
                    "text": "give me briefing",
                },
            }
        ],
    }

    sent_messages = []

    def mock_api_call(method, data=None):
        if method == "getUpdates":
            return mock_updates
        if method == "sendMessage":
            sent_messages.append(data)
            return {"ok": True}
        return {"ok": True}

    monkeypatch.setattr(runner, "_api_call", mock_api_call)

    processed = runner.poll_once()
    assert processed == 1
    assert any("Unauthorized" in m.get("text", "") for m in sent_messages)
