"""Unit and integration tests for Manual Transport and Loop Engineering external worker dispatch."""

import json
from pathlib import Path
import pytest

from zero_core.agents.loop_engineering import LoopEngineeringAgent
from zero_core.engineering.checkpoints import CheckpointManager
from zero_core.engineering.context_builder import DEFAULT_CONTEXT_BUILDER
from zero_core.engineering.manifest import ProjectManifest, TaskItem
from zero_core.engineering.store import EngineeringProjectStore
from zero_core.engineering.workers.base import (
    ProjectContextPackage,
    WorkerCapability,
    WorkerResult,
)
from zero_core.engineering.workers.external import AntigravityWorker, ChatGPTWorker
from zero_core.engineering.workers.registry import DEFAULT_WORKER_REGISTRY, bootstrap_all_workers
from zero_core.engineering.workers.transport import ManualTaskPackage, ManualTransportManager


@pytest.fixture
def clean_loop_agent(tmp_path):
    store_dir = tmp_path / "engineering_projects"
    ckpt_dir = tmp_path / "checkpoints"
    store = EngineeringProjectStore(storage_dir=store_dir)
    checkpoints = CheckpointManager(checkpoint_dir=ckpt_dir)
    agent = LoopEngineeringAgent(store=store, checkpoints=checkpoints)
    bootstrap_all_workers(DEFAULT_WORKER_REGISTRY)
    return agent


def test_manual_task_package_generation():
    context = ProjectContextPackage(
        task_id="t_man_01",
        project_id="p_manual",
        project_name="Manual System",
        current_phase="PHASE_10_BACKEND",
        task_title="Build Authentication Middleware",
        task_description="Implement JWT bearer validation",
        acceptance_criteria=["Valid tokens pass", "Expired tokens return 401"],
        constraints=["Zero external dependencies"],
        relevant_files={"auth.py": "def verify(): pass"},
    )
    pkg = ManualTransportManager.create_package(context, target_worker="ChatGPT")
    assert isinstance(pkg, ManualTaskPackage)
    assert pkg.task_id == "t_man_01"
    assert "ChatGPT" in pkg.target_worker

    formatted = pkg.to_formatted_prompt()
    assert "# ZERO Autonomous AI Engineering Organization" in formatted
    assert "Build Authentication Middleware" in formatted
    assert "Valid tokens pass" in formatted
    assert "FORBIDDEN" in formatted
    assert "auth.py" in formatted


def test_manual_transport_import_json():
    raw_user_paste = json.dumps({
        "status": "SUCCESS",
        "summary": "Implemented JWT validation logic",
        "analysis": "Added HS256 signature verification and expiration check.",
        "files_created": ["src/jwt_auth.py"],
        "files_modified": ["src/app.py"],
        "diff": "+ def verify_jwt(): return True",
        "acceptance_criteria_results": {"Valid tokens pass": True, "Expired tokens return 401": True},
        "decisions": [{"title": "ADR-JWT", "decision": "Use PyJWT", "rationale": "Security"}],
        "recommended_next_action": "Run authentication test suite",
    })
    result = ManualTransportManager.import_result(raw_user_paste, task_id="t_man_json", worker_id="worker_manual")
    assert isinstance(result, WorkerResult)
    assert result.is_success
    assert result.summary == "Implemented JWT validation logic"
    assert "src/jwt_auth.py" in result.files_created
    assert "+ def verify_jwt(): return True" in result.diff
    assert result.acceptance_criteria_results["Valid tokens pass"] is True


def test_manual_transport_import_markdown():
    raw_markdown = (
        "# Implementation Completed\n"
        "Here is the requested implementation:\n\n"
        "```python\ndef candidate_filter():\n    return []\n```\n"
    )
    result = ManualTransportManager.import_result(raw_markdown, task_id="t_man_md", worker_id="worker_manual")
    assert isinstance(result, WorkerResult)
    assert result.is_success
    assert "Implementation Completed" in result.summary
    assert "candidate_filter" in result.analysis


def test_loop_engineering_manual_transport_flow(clean_loop_agent, tmp_path):
    repo = tmp_path / "manual_saas"
    repo.mkdir()

    agent = clean_loop_agent
    manifest = agent.intake_project(idea="Build SaaS platform", repo_path=str(repo))

    task = TaskItem(
        task_id="t_ext_manual",
        milestone_id="m1",
        title="Formulate Security Policy",
        description="Write zero-trust guidelines",
        acceptance_criteria=["Policy documented"],
    )

    # 1. Create manual package
    pkg = agent.create_manual_transport_task(manifest, worker_id="worker_chatgpt", task=task)
    assert isinstance(pkg, ManualTaskPackage)
    assert pkg.task_id == "t_ext_manual"

    # 2. Simulate user pasting response back
    raw_response = json.dumps({
        "status": "SUCCESS",
        "summary": "Formulated zero-trust security policy",
        "analysis": "Enforce strict RBAC and least privilege",
        "acceptance_criteria_results": {"Policy documented": True},
    })
    res = agent.import_manual_task_result(
        manifest=manifest,
        task_id="t_ext_manual",
        worker_id="worker_chatgpt",
        raw_input=raw_response,
    )
    assert res.is_success
    assert res.summary == "Formulated zero-trust security policy"


def test_mandatory_security_regression_across_external_workers(tmp_path):
    """MANDATORY SECURITY REGRESSION TEST:
    Ensures that synthetic secrets (API keys, GitHub tokens, Telegram tokens, DB passwords, JWTs)
    NEVER appear in external worker outbound payloads, stored artifacts, or WorkerResult.
    """
    repo = tmp_path / "secret_leak_check"
    repo.mkdir()

    raw_openai_key = "sk-proj-supercriticalopenaitestkey12345"
    raw_github_token = "ghp_supercriticalgithubtesttoken1234567890"
    raw_telegram_token = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz_1234567"
    raw_db_password = "super_duper_secret_database_password_99"
    raw_database_url = f"postgresql://appuser:{raw_db_password}@dbhost:5432/main"

    (repo / ".env").write_text(f"API_KEY={raw_openai_key}\nGH_TOKEN={raw_github_token}\n", encoding="utf-8")
    (repo / "config.py").write_text(
        f"TG_BOT_TOKEN = '{raw_telegram_token}'\n"
        f"DATABASE_URI = '{raw_database_url}'\n",
        encoding="utf-8",
    )

    manifest = ProjectManifest(
        project_id="p_sec_leak_ext",
        project_name="Leak Protection Project",
        description="Verify zero leaks in external worker adapters",
        repository_path=str(repo),
    )
    task = TaskItem(
        task_id="t_leak_test_ext",
        milestone_id="m1",
        title="Inspect Configuration Layer",
        description="Audit settings and configuration",
    )

    # 1. Build context through Phase 2 builder
    sanitized_context = DEFAULT_CONTEXT_BUILDER.build_context(
        project=manifest,
        task=task,
        worker=ChatGPTWorker(api_key="fake-key"),
        target_files=["config.py"],
    )

    # 2. Test ChatGPT request formatting
    recorded_outbound = {}
    class CapturingLLMClient:
        def generate(self, system_prompt, user_prompt, model=None):
            recorded_outbound["system"] = system_prompt
            recorded_outbound["user"] = user_prompt
            return json.dumps({"status": "SUCCESS", "summary": "Audit complete"})

    chatgpt_worker = ChatGPTWorker(api_key="key", llm_client=CapturingLLMClient())
    chatgpt_worker.artifacts_dir = tmp_path
    cg_res = chatgpt_worker.run_task(sanitized_context)

    # 3. Test Antigravity manual package formatting
    antigravity_worker = AntigravityWorker(cli_path="/nonexistent")
    ag_res = antigravity_worker.run_task(sanitized_context)

    # 4. Check all outbound strings and artifacts
    all_checked_strings = [
        recorded_outbound.get("user", ""),
        recorded_outbound.get("system", ""),
        str(cg_res.to_dict()),
        str(ag_res.to_dict()),
    ]

    for artifact_file in tmp_path.rglob("*.json"):
        all_checked_strings.append(artifact_file.read_text(encoding="utf-8"))

    combined_text = "\n".join(all_checked_strings)

    # ASSERT STRICT ZERO LEAKS
    assert raw_openai_key not in combined_text, "LEAK DETECTED: raw_openai_key appeared in external payload or artifact!"
    assert raw_github_token not in combined_text, "LEAK DETECTED: raw_github_token appeared in external payload or artifact!"
    assert raw_telegram_token not in combined_text, "LEAK DETECTED: raw_telegram_token appeared in external payload or artifact!"
    assert raw_db_password not in combined_text, "LEAK DETECTED: raw_db_password appeared in external payload or artifact!"

    # Assert that safe semantic redactions ARE present
    assert "[REDACTED" in combined_text
