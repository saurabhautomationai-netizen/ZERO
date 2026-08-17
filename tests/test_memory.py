from __future__ import annotations

from pathlib import Path
from zero_core.memory import EntityStore, Message, SessionMemory


def test_session_memory_add_and_get():
    session = SessionMemory(session_id="test_session_1", max_messages=5)
    assert session.count() == 0

    session.add_message(role="user", content="Hello, ZERO!")
    session.add_message(role="assistant", content="Hello! How can I help you today?")

    assert session.count() == 2
    msgs = session.get_messages()
    assert msgs[0].role == "user"
    assert msgs[0].content == "Hello, ZERO!"
    assert msgs[1].role == "assistant"
    assert msgs[1].content == "Hello! How can I help you today?"


def test_session_memory_truncation_window():
    session = SessionMemory(session_id="test_session_2", max_messages=3)

    for i in range(5):
        session.add_message(role="user", content=f"Message {i}")

    assert session.count() == 3
    msgs = session.get_messages()
    assert msgs[0].content == "Message 2"
    assert msgs[1].content == "Message 3"
    assert msgs[2].content == "Message 4"


def test_session_memory_formatted_history_and_json():
    session = SessionMemory(session_id="test_session_3")
    session.add_message(role="user", content="What is my budget?")
    session.add_message(role="assistant", content="Your monthly budget is $2000.")

    history = session.get_formatted_history()
    assert "User: What is my budget?" in history
    assert "Assistant: Your monthly budget is $2000." in history

    json_str = session.to_json()
    new_session = SessionMemory(session_id="test_session_3_clone")
    new_session.load_json(json_str)
    assert new_session.count() == 2
    assert new_session.get_messages()[0].content == "What is my budget?"


def test_entity_store_crud_and_persistence(tmp_path: Path):
    db_file = tmp_path / "entities.json"
    store = EntityStore(persistence_file=db_file)

    store.set("user_profile", "name", "Alex")
    store.set("user_profile", "currency", "USD")
    store.set("trading_rules", "max_risk_pct", 1.5)

    assert store.get("user_profile", "name") == "Alex"
    assert store.get("user_profile", "currency") == "USD"
    assert store.get("trading_rules", "max_risk_pct") == 1.5
    assert store.get("user_profile", "missing_key", default="default_val") == "default_val"

    assert set(store.list_keys("user_profile")) == {"name", "currency"}

    # Reload from file to ensure persistence worked
    reloaded_store = EntityStore(persistence_file=db_file)
    assert reloaded_store.get("user_profile", "name") == "Alex"
    assert reloaded_store.get("trading_rules", "max_risk_pct") == 1.5

    # Delete & Clear
    assert store.delete("user_profile", "currency") is True
    assert store.get("user_profile", "currency") is None

    store.clear(namespace="trading_rules")
    assert store.get_namespace("trading_rules") == {}
