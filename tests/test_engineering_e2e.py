import pytest
from fastapi.testclient import TestClient
from zero_core.interfaces.web.app import app
from zero_core.bootstrap import build_orchestrator

client = TestClient(app)


def test_orchestrator_routes_to_loop_engineering():
    orch = build_orchestrator()
    res = orch.run("ZERO, build me a complete HR Recruitment AI Assistant")
    assert res.selected is not None
    assert res.selected.slug == "native/loop-engineering-agent"


def test_orchestrator_executes_loop_engineering_intake():
    orch = build_orchestrator()
    exec_res = orch.execute("ZERO, build me a complete HR Recruitment AI Assistant")
    assert exec_res.answer is not None
    assert "Autonomous Engineering Complete" in exec_res.answer or "Project Intake & Discovery" in exec_res.answer
    assert "COMPLETED" in exec_res.answer or "Gate 1" in exec_res.answer


def test_web_api_engineering_projects():
    # 1. List Projects
    res = client.get("/api/v1/engineering/projects")
    assert res.status_code == 200
    data = res.json()
    assert "projects" in data
    assert "count" in data


def test_orchestrator_status_and_continue_queries():
    orch = build_orchestrator()
    
    # Trigger intake
    orch.execute("build me a complete Trading Dashboard")
    
    # Status query
    status_res = orch.execute("where are we with the Trading Dashboard?")
    assert status_res.answer is not None
    assert "Trading Dashboard" in status_res.answer

    # Continue query
    continue_res = orch.execute("continue the Trading Dashboard")
    assert continue_res.answer is not None
    assert "Project Resumed" in continue_res.answer
