from __future__ import annotations

import asyncio
import json
from pathlib import Path

import zero_core.interfaces.web.handlers as handlers
from zero_core.agent_registry import AgencyAgentsAdapter, AgentRegistry
from zero_core.interfaces.web.app import app
from zero_core.native_agents import ALL_NATIVE_AGENTS
from zero_core.orchestrator import Orchestrator


def _patch_backends(monkeypatch, fake_agency_root):
    adapter = AgencyAgentsAdapter(
        root=fake_agency_root,
        divisions=["engineering", "finance"],
        inventory_snapshot=Path("/nonexistent"),
    )
    registry = AgentRegistry(agency_adapter=adapter, native_agents=ALL_NATIVE_AGENTS)
    orch = Orchestrator(registry=registry)

    monkeypatch.setattr(handlers, "build_registry", lambda: registry)
    monkeypatch.setattr(handlers, "build_orchestrator", lambda: orch)
    return registry, orch


async def _dispatch_asgi(scope: dict, body_bytes: bytes = b"") -> tuple[int, dict]:
    messages = []

    async def receive():
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    async def send(msg):
        messages.append(msg)

    await app(scope, receive, send)
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, json.loads(body.decode("utf-8"))


def test_fastapi_get_agents_endpoint(monkeypatch, fake_agency_root):
    _patch_backends(monkeypatch, fake_agency_root)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/agents",
        "query_string": b"",
        "headers": [],
    }
    status, payload = asyncio.run(_dispatch_asgi(scope))
    assert status == 200
    assert len(payload["native"]) == len(ALL_NATIVE_AGENTS)
    assert payload["agency_count"] == 2


def test_fastapi_get_agent_by_slug_endpoint(monkeypatch, fake_agency_root):
    _patch_backends(monkeypatch, fake_agency_root)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/agents/native/finance-agent",
        "query_string": b"",
        "headers": [],
    }
    status, payload = asyncio.run(_dispatch_asgi(scope))
    assert status == 200
    assert payload["name"] == "Finance Agent"


def test_fastapi_get_agent_not_found_returns_404(monkeypatch, fake_agency_root):
    _patch_backends(monkeypatch, fake_agency_root)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/agents/invalid/unknown-slug",
        "query_string": b"",
        "headers": [],
    }
    status, payload = asyncio.run(_dispatch_asgi(scope))
    assert status == 404
    assert "No agent found" in payload["detail"]


def test_fastapi_post_task_endpoint(monkeypatch, fake_agency_root):
    _patch_backends(monkeypatch, fake_agency_root)
    monkeypatch.delenv("FINANCE_DB_URL", raising=False)

    req_body = json.dumps({"task": "What did I spend on subscriptions last month?"}).encode("utf-8")
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/task",
        "query_string": b"",
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(req_body)).encode("utf-8")),
        ],
    }
    status, payload = asyncio.run(_dispatch_asgi(scope, req_body))
    assert status == 200
    assert payload["selected"]["slug"] == "native/finance-agent"
    assert payload["needs_llm"] is False


def test_fastapi_get_root_endpoint():
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        messages.append(msg)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [],
    }

    asyncio.run(app(scope, receive, send))
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    assert status == 200
