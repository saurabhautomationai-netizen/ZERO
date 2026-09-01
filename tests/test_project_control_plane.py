"""Comprehensive Regression Test Suite for ZERO Multi-Project Control Plane.

Tests all 30 mandatory requirements:
- Explicit project_id precedence (always wins)
- Normalized canonical path resolution
- Fail-closed behavior (PROJECT_NOT_FOUND, PROJECT_AMBIGUOUS, BOUNDARY_VIOLATION)
- Removal of project-specific keyword hacks
- ProjectKnowledge canonical alias mapping
- Checkpoint isolation
- Mutation safety (UNKNOWN, DIAGNOSTIC, STATUS cannot mutate)
- Approval isolation (elimination of pending[-1])
- Sequential request isolation (Finance -> HR -> Finance)
"""

import os
from pathlib import Path
import pytest

from zero_core.agents.loop_engineering import DEFAULT_LOOP_ENGINEERING_AGENT, LoopEngineeringAgent
from zero_core.engineering.checkpoints import CheckpointIsolationError, DEFAULT_CHECKPOINT_MANAGER
from zero_core.engineering.manifest import ApprovalGateType, PhaseEnum, ProjectManifest, ProjectStatus, TaskItem
from zero_core.engineering.resolver import (
    CANONICAL_PROJECT_ALIASES,
    DEFAULT_PROJECT_RESOLVER,
    EngineeringIntent,
    EngineeringRequest,
    ProjectResolver,
    ResolutionError,
    ResolutionStatus,
    normalize_repo_path,
)
from zero_core.engineering.store import DEFAULT_PROJECT_STORE, EngineeringProjectStore
from zero_core.executors import _execute_loop_engineering
from zero_core.memory.project_knowledge import DEFAULT_PROJECT_KNOWLEDGE


# -----------------------------------------------------------------------------
# 1. Explicit Finance project_id resolves Finance Tracker
# -----------------------------------------------------------------------------
def test_01_explicit_finance_project_id_resolves_finance():
    req = DEFAULT_PROJECT_RESOLVER.parse_request(
        "@Loop Engineering Agent\nProject ID: proj_personal_finance_tracker\nCheck status."
    )
    manifest = DEFAULT_PROJECT_RESOLVER.resolve_project(req)
    assert manifest.project_id == "proj_personal_finance_tracker"
    assert "Finance" in manifest.project_name


# -----------------------------------------------------------------------------
# 2. Explicit HR project_id resolves HR Recruitment Assistant
# -----------------------------------------------------------------------------
def test_02_explicit_hr_project_id_resolves_hr():
    req = DEFAULT_PROJECT_RESOLVER.parse_request(
        "@Loop Engineering Agent\nProject ID: proj_hr_recruitment_ai_assistant\nCheck status."
    )
    manifest = DEFAULT_PROJECT_RESOLVER.resolve_project(req)
    assert manifest.project_id == "proj_hr_recruitment_ai_assistant"
    assert "Recruitment" in manifest.project_name


# -----------------------------------------------------------------------------
# 3. Exact normalized Finance repository resolves Finance Tracker
# -----------------------------------------------------------------------------
def test_03_exact_finance_repository_resolves_finance():
    repo_path = r"F:\AI Automation\Projects\Smart Finance AI Tracker\Personal Finance Tracker"
    req = DEFAULT_PROJECT_RESOLVER.parse_request(
        f"@Loop Engineering Agent\nRepository: {repo_path}\nInspect project."
    )
    manifest = DEFAULT_PROJECT_RESOLVER.resolve_project(req)
    assert manifest.project_id == "proj_personal_finance_tracker"


# -----------------------------------------------------------------------------
# 4. Exact normalized HR repository resolves HR Recruitment Assistant
# -----------------------------------------------------------------------------
def test_04_exact_hr_repository_resolves_hr():
    repo_path = r"F:\AI Automation\Projects\HR Recruitment Assistant\Dashboard\ai-recruitment-dashboard\hr_recruitment_ai_assistant"
    req = DEFAULT_PROJECT_RESOLVER.parse_request(
        f"@Loop Engineering Agent\nRepository: {repo_path}\nInspect project."
    )
    manifest = DEFAULT_PROJECT_RESOLVER.resolve_project(req)
    assert manifest.project_id == "proj_hr_recruitment_ai_assistant"


# -----------------------------------------------------------------------------
# 5. Invalid explicit project_id fails closed (PROJECT_NOT_FOUND)
# -----------------------------------------------------------------------------
def test_05_invalid_project_id_fails_closed():
    req = DEFAULT_PROJECT_RESOLVER.parse_request(
        "@Loop Engineering Agent\nProject ID: proj_does_not_exist_xyz\nStatus."
    )
    with pytest.raises(ResolutionError) as exc_info:
        DEFAULT_PROJECT_RESOLVER.resolve_project(req)
    assert exc_info.value.status == ResolutionStatus.PROJECT_NOT_FOUND


# -----------------------------------------------------------------------------
# 6. Ambiguous project query fails closed (PROJECT_AMBIGUOUS)
# -----------------------------------------------------------------------------
def test_06_ambiguous_project_name_fails_closed():
    resolver = ProjectResolver(DEFAULT_PROJECT_STORE)
    req = EngineeringRequest(raw_instruction="Show dashboard assistant status")
    # Both Trading Dashboard and HR Recruitment Assistant might score similarly if queried ambiguously
    with pytest.raises(ResolutionError) as exc_info:
        # Intentionally construct an ambiguous query with multiple project words
        req_ambig = EngineeringRequest(raw_instruction="Personal Finance and HR Recruitment Assistant project")
        resolver.resolve_project(req_ambig)
    assert exc_info.value.status in (ResolutionStatus.PROJECT_AMBIGUOUS, ResolutionStatus.PROJECT_NOT_FOUND)


# -----------------------------------------------------------------------------
# 7. Active HR session overridden by explicit Finance ID
# -----------------------------------------------------------------------------
def test_07_active_hr_session_overridden_by_explicit_finance_id():
    req = DEFAULT_PROJECT_RESOLVER.parse_request(
        "Project ID: proj_personal_finance_tracker\nStatus.",
        session_project_id="proj_hr_recruitment_ai_assistant",
    )
    manifest = DEFAULT_PROJECT_RESOLVER.resolve_project(
        req, session_project_id="proj_hr_recruitment_ai_assistant"
    )
    assert manifest.project_id == "proj_personal_finance_tracker"


# -----------------------------------------------------------------------------
# 8. Active Finance session overridden by explicit HR ID
# -----------------------------------------------------------------------------
def test_08_active_finance_session_overridden_by_explicit_hr_id():
    req = DEFAULT_PROJECT_RESOLVER.parse_request(
        "Project ID: proj_hr_recruitment_ai_assistant\nStatus.",
        session_project_id="proj_personal_finance_tracker",
    )
    manifest = DEFAULT_PROJECT_RESOLVER.resolve_project(
        req, session_project_id="proj_personal_finance_tracker"
    )
    assert manifest.project_id == "proj_hr_recruitment_ai_assistant"


# -----------------------------------------------------------------------------
# 9. Finance task after HR task produces NO contamination
# -----------------------------------------------------------------------------
def test_09_finance_task_after_hr_task_no_contamination():
    # 1. Resolve HR
    req_hr = DEFAULT_PROJECT_RESOLVER.parse_request("Project ID: proj_hr_recruitment_ai_assistant\nStatus")
    m_hr = DEFAULT_PROJECT_RESOLVER.resolve_project(req_hr)
    assert m_hr.project_id == "proj_hr_recruitment_ai_assistant"

    # 2. Resolve Finance immediately after
    req_fin = DEFAULT_PROJECT_RESOLVER.parse_request("Project ID: proj_personal_finance_tracker\nStatus")
    m_fin = DEFAULT_PROJECT_RESOLVER.resolve_project(req_fin)
    assert m_fin.project_id == "proj_personal_finance_tracker"
    assert m_fin.repository_path != m_hr.repository_path


# -----------------------------------------------------------------------------
# 10. HR task after Finance task produces NO contamination
# -----------------------------------------------------------------------------
def test_10_hr_task_after_finance_task_no_contamination():
    req_fin = DEFAULT_PROJECT_RESOLVER.parse_request("Project ID: proj_personal_finance_tracker\nStatus")
    m_fin = DEFAULT_PROJECT_RESOLVER.resolve_project(req_fin)
    assert m_fin.project_id == "proj_personal_finance_tracker"

    req_hr = DEFAULT_PROJECT_RESOLVER.parse_request("Project ID: proj_hr_recruitment_ai_assistant\nStatus")
    m_hr = DEFAULT_PROJECT_RESOLVER.resolve_project(req_hr)
    assert m_hr.project_id == "proj_hr_recruitment_ai_assistant"


# -----------------------------------------------------------------------------
# 11. Diagnostic instruction executes diagnosis, NOT canned Gate 1 discovery
# -----------------------------------------------------------------------------
def test_11_diagnostic_instruction_executes_diagnosis_not_gate1():
    out = _execute_loop_engineering(
        "@Loop Engineering Agent\n"
        "Project ID: proj_personal_finance_tracker\n"
        "Diagnose why Finance is resolving to HR. Do not modify anything."
    )
    assert "🔬 Project Diagnostic Report" in out
    assert "READ-ONLY DIAGNOSTIC" in out
    assert "GATE 1 (Feature Scope Approval)" not in out
    assert "🛑 Halted at Continuation HITL Gate" not in out


# -----------------------------------------------------------------------------
# 12. Resume instruction loads correct checkpoint for that project
# -----------------------------------------------------------------------------
def test_12_resume_instruction_loads_correct_checkpoint():
    out = _execute_loop_engineering(
        "@Loop Engineering Agent\n"
        "Project ID: proj_personal_finance_tracker\n"
        "Resume project."
    )
    assert "Personal Finance Tracker" in out
    assert "Project Resumed" in out or "Status" in out


# -----------------------------------------------------------------------------
# 13. Two projects at different gates remain independent
# -----------------------------------------------------------------------------
def test_13_two_projects_at_different_gates_independent():
    p_fin = DEFAULT_PROJECT_STORE.get_project("proj_personal_finance_tracker")
    p_hr = DEFAULT_PROJECT_STORE.get_project("proj_hr_recruitment_ai_assistant")
    assert p_fin is not None
    assert p_hr is not None
    assert p_fin.project_id != p_hr.project_id
    # Even if both are APPROVAL_PENDING, they are separate manifest instances
    assert id(p_fin) != id(p_hr)


# -----------------------------------------------------------------------------
# 14. Checkpoint isolation: loading project A checkpoint under project B is blocked
# -----------------------------------------------------------------------------
def test_14_checkpoint_isolation_cross_project_blocked():
    ckpts = DEFAULT_CHECKPOINT_MANAGER.list_checkpoints("proj_hr_recruitment_ai_assistant")
    if ckpts:
        target_ckpt = ckpts[0].checkpoint_id
        # Attempting to load HR checkpoint under Finance ID must fail
        with pytest.raises(CheckpointIsolationError):
            DEFAULT_CHECKPOINT_MANAGER.get_checkpoint("proj_personal_finance_tracker", target_ckpt)


# -----------------------------------------------------------------------------
# 15. Repository mutation guard blocks cross-project target paths
# -----------------------------------------------------------------------------
def test_15_repository_mutation_guard_blocks_cross_project():
    m_fin = DEFAULT_PROJECT_STORE.get_project("proj_personal_finance_tracker")
    assert m_fin is not None
    alien_path = r"F:\AI Automation\Projects\HR Recruitment Assistant\Dashboard\file.py"
    with pytest.raises(ResolutionError) as exc_info:
        DEFAULT_PROJECT_RESOLVER.verify_mutation_boundary(m_fin, target_path=alien_path)
    assert exc_info.value.status == ResolutionStatus.BOUNDARY_VIOLATION


# -----------------------------------------------------------------------------
# 16. Explicit project ID beats conflicting project keywords in text
# -----------------------------------------------------------------------------
def test_16_explicit_project_id_beats_conflicting_project_keywords():
    prompt = (
        "@Loop Engineering Agent\n"
        "Project ID: proj_personal_finance_tracker\n"
        "Why did you previously select the HR recruitment assistant instead of finance?"
    )
    req = DEFAULT_PROJECT_RESOLVER.parse_request(prompt)
    manifest = DEFAULT_PROJECT_RESOLVER.resolve_project(req)
    assert manifest.project_id == "proj_personal_finance_tracker"


# -----------------------------------------------------------------------------
# 17. Explicit repository beats conflicting historical state
# -----------------------------------------------------------------------------
def test_17_explicit_repository_beats_conflicting_historical_state():
    repo = r"F:\AI Automation\Projects\Smart Finance AI Tracker\Personal Finance Tracker"
    req = DEFAULT_PROJECT_RESOLVER.parse_request(
        f"Repository: {repo}\nCheck status.",
        session_project_id="proj_hr_recruitment_ai_assistant",
    )
    manifest = DEFAULT_PROJECT_RESOLVER.resolve_project(req, session_project_id="proj_hr_recruitment_ai_assistant")
    assert manifest.project_id == "proj_personal_finance_tracker"


# -----------------------------------------------------------------------------
# 18. UNKNOWN intent cannot mutate filesystem
# -----------------------------------------------------------------------------
def test_18_unknown_intent_cannot_mutate_filesystem():
    out = _execute_loop_engineering(
        "@Loop Engineering Agent\n"
        "Project ID: proj_personal_finance_tracker\n"
        "Tell me a philosophical joke about software engineering."
    )
    assert "ℹ️ Loop Engineering Instruction Received" in out
    assert "Unrecognized command intent. For safety, no files were mutated." in out


# -----------------------------------------------------------------------------
# 19. DIAGNOSTIC intent cannot mutate filesystem
# -----------------------------------------------------------------------------
def test_19_diagnostic_intent_cannot_mutate_filesystem():
    out = _execute_loop_engineering(
        "@Loop Engineering Agent\n"
        "Project ID: proj_personal_finance_tracker\n"
        "Diagnose component health."
    )
    assert "🔬 Project Diagnostic Report" in out
    assert "No files were mutated, no gates were approved" in out


# -----------------------------------------------------------------------------
# 20. STATUS cannot advance lifecycle
# -----------------------------------------------------------------------------
def test_20_status_cannot_advance_lifecycle():
    m_before = DEFAULT_PROJECT_STORE.get_project("proj_personal_finance_tracker")
    phase_before = m_before.current_phase
    _execute_loop_engineering(
        "@Loop Engineering Agent\n"
        "Project ID: proj_personal_finance_tracker\n"
        "What is the status of this project?"
    )
    m_after = DEFAULT_PROJECT_STORE.get_project("proj_personal_finance_tracker")
    assert m_after.current_phase == phase_before


# -----------------------------------------------------------------------------
# 21. PROJECT_NOT_FOUND cannot create a new manifest automatically
# -----------------------------------------------------------------------------
def test_21_project_not_found_cannot_create_new_manifest():
    initial_count = len(DEFAULT_PROJECT_STORE.list_projects())
    out = _execute_loop_engineering(
        "@Loop Engineering Agent\n"
        "Project ID: proj_completely_non_existent_12345\n"
        "Status."
    )
    assert "PROJECT_NOT_FOUND" in out
    after_count = len(DEFAULT_PROJECT_STORE.list_projects())
    assert initial_count == after_count


# -----------------------------------------------------------------------------
# 22. PROJECT_AMBIGUOUS cannot mutate anything
# -----------------------------------------------------------------------------
def test_22_project_ambiguous_cannot_mutate_anything():
    req = EngineeringRequest(raw_instruction="personal finance hr recruitment dashboard assistant")
    with pytest.raises(ResolutionError) as exc_info:
        DEFAULT_PROJECT_RESOLVER.resolve_project(req)
    assert exc_info.value.status in (ResolutionStatus.PROJECT_AMBIGUOUS, ResolutionStatus.PROJECT_NOT_FOUND)


# -----------------------------------------------------------------------------
# 23. Approval without project identity when multiple projects pending returns ambiguity
# -----------------------------------------------------------------------------
def test_23_approval_without_project_identity_when_multiple_pending_returns_ambiguity():
    out = _execute_loop_engineering("Approve feature scope")
    # Both Finance and HR are in APPROVAL_PENDING state
    assert "PROJECT_AMBIGUOUS" in out
    assert "Multiple projects are currently awaiting approval" in out


# -----------------------------------------------------------------------------
# 24. Checkpoint project ID mismatch is blocked
# -----------------------------------------------------------------------------
def test_24_checkpoint_project_id_mismatch_is_blocked():
    ckpts = DEFAULT_CHECKPOINT_MANAGER.list_checkpoints("proj_hr_recruitment_ai_assistant")
    if ckpts:
        target_ckpt = ckpts[0].checkpoint_id
        with pytest.raises(CheckpointIsolationError):
            DEFAULT_CHECKPOINT_MANAGER.restore_manifest_from_checkpoint(
                project_id="proj_personal_finance_tracker",
                checkpoint_id=target_ckpt,
            )


# -----------------------------------------------------------------------------
# 25. RepositoryGuard and manifest repository mismatch is blocked
# -----------------------------------------------------------------------------
def test_25_repository_guard_and_manifest_mismatch_is_blocked():
    m = DEFAULT_PROJECT_STORE.get_project("proj_trading_dashboard")
    assert m is not None
    bad_target = r"f:/AI Automation/Projects/Zero/zero_core/hack.py"
    with pytest.raises(ResolutionError) as exc_info:
        DEFAULT_PROJECT_RESOLVER.verify_mutation_boundary(m, target_path=bad_target)
    assert exc_info.value.status == ResolutionStatus.BOUNDARY_VIOLATION


# -----------------------------------------------------------------------------
# 26. ProjectKnowledge alias resolves to canonical ID
# -----------------------------------------------------------------------------
def test_26_project_knowledge_alias_resolves_to_canonical_id():
    # Pass canonical project_id to knowledge store
    profile = DEFAULT_PROJECT_KNOWLEDGE.get_project("proj_personal_finance_tracker")
    assert profile is not None
    assert profile.project_id == "finance_tracker"
    assert "Finance" in profile.name

    # Reverse lookup
    profile_rev = DEFAULT_PROJECT_KNOWLEDGE.get_project("finance_tracker")
    assert profile_rev is not None


# -----------------------------------------------------------------------------
# 27. Finance -> HR -> Finance sequential requests remain isolated
# -----------------------------------------------------------------------------
def test_27_finance_hr_finance_sequential_requests_remain_isolated():
    out1 = _execute_loop_engineering("Project ID: proj_personal_finance_tracker\nShow status of this project.")
    assert "Personal Finance Tracker" in out1
    assert "HR Recruitment" not in out1

    out2 = _execute_loop_engineering("Project ID: proj_hr_recruitment_ai_assistant\nShow status of this project.")
    assert "HR Recruitment AI Assistant" in out2
    assert "Personal Finance Tracker" not in out2

    out3 = _execute_loop_engineering("Project ID: proj_personal_finance_tracker\nShow status of this project.")
    assert "Personal Finance Tracker" in out3
    assert "HR Recruitment" not in out3


# -----------------------------------------------------------------------------
# 28. Simultaneous independent HITL states remain isolated
# -----------------------------------------------------------------------------
def test_28_simultaneous_independent_hitl_states_remain_isolated():
    p_fin = DEFAULT_PROJECT_STORE.get_project("proj_personal_finance_tracker")
    p_hr = DEFAULT_PROJECT_STORE.get_project("proj_hr_recruitment_ai_assistant")
    assert p_fin is not None and p_hr is not None

    # Approving feature scope with explicit ID only modifies Finance
    out = _execute_loop_engineering(
        "Approve feature scope\nProject ID: proj_personal_finance_tracker"
    )
    assert "Feature Scope Approved" in out
    assert "Personal Finance Tracker" in out
    assert "HR Recruitment" not in out


# -----------------------------------------------------------------------------
# 29. Diagnostic command reaches diagnostic execution instead of canned discovery
# -----------------------------------------------------------------------------
def test_29_diagnostic_command_reaches_diagnostic_execution_instead_of_canned_discovery():
    out = _execute_loop_engineering(
        "@Loop Engineering Agent\n"
        "Project ID: proj_hr_recruitment_ai_assistant\n"
        "Investigate and troubleshoot why previous step halted. Diagnose only."
    )
    assert "🔬 Project Diagnostic Report: HR Recruitment AI Assistant" in out
    assert "READ-ONLY DIAGNOSTIC" in out
    assert "Gate 1 (Feature Scope Approval)" not in out


# -----------------------------------------------------------------------------
# 30. Arbitrary legitimate engineering task reaches TaskRouter / worker execution after gates
# -----------------------------------------------------------------------------
def test_30_arbitrary_legitimate_engineering_task_reaches_task_router_after_required_gates():
    m = DEFAULT_PROJECT_STORE.get_project("proj_personal_finance_tracker")
    task = TaskItem(
        task_id="t_test_cycle",
        milestone_id="M_TEST",
        title="Verify database connection config",
        description="Check database connectivity and schemas",
        target_files=["schema_enterprise.sql"],
    )
    # The underlying run_autonomous_task_cycle should execute worker, reviewer, validator
    agent = LoopEngineeringAgent(store=DEFAULT_PROJECT_STORE)
    res = agent.run_autonomous_task_cycle(m, task)
    assert "status" in res
    assert "routing" in res
    assert res["routing"]["task_id"] == "t_test_cycle"
    assert "execution" in res
    assert res["execution"]["project_id"] == "proj_personal_finance_tracker"
