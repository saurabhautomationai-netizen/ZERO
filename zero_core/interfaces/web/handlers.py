"""Pure request-handling logic for the web interface.

Deliberately has NO import of fastapi (or any web framework) — this module
is fully unit-testable without that dependency installed at all, and
app.py (the actual FastAPI route wiring) stays a thin, mostly-untested-by-
necessity shim that just calls into here. This is the same "interfaces
carry no business logic" rule documented in this folder's README, applied.

Known Phase 1 inefficiency, left as-is on purpose rather than
prematurely optimized: every call rebuilds the registry from scratch,
which re-scans and re-parses all 269 Agency-agents files from disk. Fine
for occasional personal use; if this ever sits behind real request volume,
cache the registry (e.g. FastAPI lifespan + app.state, or
functools.lru_cache with an explicit invalidation hook for
`git pull`-ed updates to the Agency-agents clone) — don't add that
complexity before it's actually needed.
"""

from __future__ import annotations

from typing import Any, Optional

from zero_core.agent_registry import AgentSpec
from zero_core.bootstrap import build_orchestrator, build_registry


def _spec_to_dict(spec: Optional[AgentSpec]) -> Optional[dict[str, Any]]:
    if spec is None:
        return None
    return {
        "name": spec.name,
        "slug": spec.slug,
        "source": spec.source,
        "division": spec.division,
        "description": spec.description,
    }


from zero_core.llm import DEFAULT_LLM_MANAGER


def handle_task(task: str, auto_invoke_llm: bool = True) -> dict[str, Any]:
    if not task or not task.strip():
        return {"error": "task must be a non-empty string"}

    orch = build_orchestrator()

    # Check for multi-line multi-agent batch dispatch (@Agent1: ... \n @Agent2: ...)
    lines = [l.strip() for l in task.strip().splitlines() if l.strip()]
    at_lines = [l for l in lines if l.startswith("@")]

    if len(at_lines) > 1:
        sub_results = []
        for line in at_lines:
            decision = orch.run(line)
            outcome = orch.execute(line)
            ans = outcome.answer
            if outcome.needs_llm and outcome.persona and auto_invoke_llm and ans is None:
                ans = DEFAULT_LLM_MANAGER.call_specialist(persona=outcome.persona, task=line)
            agent_name = decision.selected.name if decision.selected else "Specialist"
            sub_results.append(f"### 🤖 {agent_name}\n**Assigned Directive**: `{line}`\n\n{ans or 'Acknowledged and processed.'}")

        return {
            "task": task,
            "selected": {"name": f"Multi-Agent Squad ({len(at_lines)} Agents)", "slug": "squad", "source": "squad", "division": "orchestrated-squad"},
            "alternatives": [],
            "needs_llm": False,
            "answer": "\n\n---\n\n".join(sub_results),
            "persona": None,
        }

    decision = orch.run(task)
    outcome = orch.execute(task)

    answer = outcome.answer
    if outcome.needs_llm and outcome.persona and auto_invoke_llm and answer is None:
        answer = DEFAULT_LLM_MANAGER.call_specialist(persona=outcome.persona, task=task)

    return {
        "task": task,
        "selected": _spec_to_dict(decision.selected),
        "alternatives": [_spec_to_dict(a) for a in decision.alternatives],
        "needs_llm": outcome.needs_llm,
        "answer": answer,
        "persona": outcome.persona if outcome.needs_llm else None,
    }


def handle_list_agents(division: Optional[str] = None) -> dict[str, Any]:
    registry = build_registry()
    agency = registry.list_agency(division=division)
    return {
        "native": [_spec_to_dict(a) for a in registry.list_native()],
        "agency": [_spec_to_dict(a) for a in agency],
        "agency_count": len(agency),
    }


def handle_get_agent(slug: str) -> Optional[dict[str, Any]]:
    registry = build_registry()
    return _spec_to_dict(registry.get(slug))


from zero_core.agents.loop_engineering import DEFAULT_LOOP_ENGINEERING_AGENT


def handle_list_engineering_projects() -> dict[str, Any]:
    """Returns list of all active and completed engineering projects."""
    projects = DEFAULT_LOOP_ENGINEERING_AGENT.store.list_projects()
    return {
        "count": len(projects),
        "projects": [p.model_dump() for p in projects],
    }


def handle_get_engineering_project(project_id: str) -> Optional[dict[str, Any]]:
    """Returns detailed manifest and history for a specific project."""
    manifest = DEFAULT_LOOP_ENGINEERING_AGENT.store.get_project(project_id)
    if not manifest:
        manifest = DEFAULT_LOOP_ENGINEERING_AGENT.store.find_by_name(project_id)
    return manifest.model_dump() if manifest else None


def handle_engineering_project_action(project_id: str, action: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Dispatches human-in-the-loop approvals or lifecycle continuation."""
    act = action.lower()
    if act == "approve_scope":
        return DEFAULT_LOOP_ENGINEERING_AGENT.approve_feature_scope(project_id)
    elif act == "approve_uiux":
        return DEFAULT_LOOP_ENGINEERING_AGENT.approve_uiux_and_build(project_id)
    elif act in ("approve_security", "approve_deploy"):
        return DEFAULT_LOOP_ENGINEERING_AGENT.approve_security_and_deploy(project_id)
    elif act == "continue":
        return DEFAULT_LOOP_ENGINEERING_AGENT.continue_project(project_id)
    return {"error": f"Unknown action: {action}"}


# -------------------------------------------------------------------------
# SALES & COMMERCIAL GROWTH HANDLERS
# -------------------------------------------------------------------------
def handle_sales_lead(payload: dict[str, Any]) -> dict[str, Any]:
    from zero_core.sales.crm import DEFAULT_SALES_CRM
    lead = DEFAULT_SALES_CRM.create_lead(
        name=payload.get("name", ""),
        email=payload.get("email", ""),
        company=payload.get("company", ""),
        phone=payload.get("phone", ""),
        recruiters_count=int(payload.get("recruiters_count", 1)),
        source=payload.get("source", "WEBSITE"),
        selected_plan=payload.get("selected_plan", "GROWTH_199"),
    )
    return {"status": "SUCCESS", "lead_id": lead.lead_id, "message": "Lead captured successfully"}


def handle_sales_demo(payload: dict[str, Any]) -> dict[str, Any]:
    from zero_core.sales.crm import DEFAULT_SALES_CRM
    demo = DEFAULT_SALES_CRM.book_demo(
        name=payload.get("name", ""),
        email=payload.get("email", ""),
        company=payload.get("company", ""),
        date=payload.get("requested_date", ""),
        time=payload.get("requested_time", "11:00 AM"),
        recruiters_count=int(payload.get("recruiters_count", 1)),
    )
    return {"status": "SUCCESS", "booking_id": demo.booking_id, "message": "Demo booked successfully"}


def handle_sales_trial_signup(payload: dict[str, Any]) -> dict[str, Any]:
    from zero_core.sales.crm import DEFAULT_SALES_CRM
    trial = DEFAULT_SALES_CRM.start_30_day_trial(
        name=payload.get("name", ""),
        email=payload.get("email", ""),
        company=payload.get("company", ""),
        plan=payload.get("plan", "GROWTH_199"),
        recruiters_count=int(payload.get("recruiters_count", 1)),
    )
    return {
        "status": "SUCCESS",
        "trial_id": trial.trial_id,
        "trial_end": trial.trial_end,
        "message": "30-Day Free Trial workspace generated successfully",
    }


def handle_sales_pipeline() -> dict[str, Any]:
    from zero_core.agents.sales_agent import DEFAULT_SALES_AGENT
    return DEFAULT_SALES_AGENT.get_pipeline_summary()


def handle_sales_campaign(channel: str) -> dict[str, Any]:
    from zero_core.agents.sales_agent import DEFAULT_SALES_AGENT
    return DEFAULT_SALES_AGENT.generate_marketing_campaign(channel=channel)


# -------------------------------------------------------------------------
# AUTONOMOUS PATROL & HITL APPROVAL HANDLERS
# -------------------------------------------------------------------------
from zero_core.patrol import DEFAULT_PATROL_WORKER, DEFAULT_APPROVAL_ENGINE


def handle_patrol_status() -> dict[str, Any]:
    return DEFAULT_PATROL_WORKER.get_status()


def handle_trigger_patrol() -> dict[str, Any]:
    return DEFAULT_PATROL_WORKER.run_patrol_sweep()


def handle_list_pending_approvals() -> dict[str, Any]:
    pending = DEFAULT_APPROVAL_ENGINE.get_pending_requests()
    return {
        "count": len(pending),
        "approvals": [req.to_dict() for req in pending],
    }


def handle_decide_approval(
    request_id: str,
    decision: str,
    approver: str = "user",
    reason: Optional[str] = None,
) -> dict[str, Any]:
    dec = decision.lower().strip()
    if dec == "approve":
        ok = DEFAULT_APPROVAL_ENGINE.approve(request_id, approver=approver, reason=reason)
        if not ok:
            return {"success": False, "message": "Failed to approve or request not found"}
        # Execute remediation
        rem_res = DEFAULT_PATROL_WORKER.apply_approved_remediation(request_id)
        return {"success": True, "decision": "APPROVED", "remediation": rem_res}
    elif dec == "reject":
        ok = DEFAULT_APPROVAL_ENGINE.reject(request_id, approver=approver, reason=reason)
        if not ok:
            return {"success": False, "message": "Failed to reject or request not found"}
        return {"success": True, "decision": "REJECTED", "message": "Proposal rejected by user"}
    return {"success": False, "message": f"Invalid decision: {decision}. Use 'approve' or 'reject'."}


def handle_bulk_decide_approvals(decision: str, approver: str = "user") -> dict[str, Any]:
    pending = DEFAULT_APPROVAL_ENGINE.get_pending_requests()
    dec = decision.lower().strip()
    count = len(pending)
    if dec == "approve":
        for req in pending:
            DEFAULT_APPROVAL_ENGINE.approve(req.request_id, approver=approver)
            DEFAULT_PATROL_WORKER.apply_approved_remediation(req.request_id)
        return {"success": True, "decision": "APPROVED_ALL", "processed_count": count}
    elif dec == "reject":
        for req in pending:
            DEFAULT_APPROVAL_ENGINE.reject(req.request_id, approver=approver)
        return {"success": True, "decision": "REJECTED_ALL", "processed_count": count}
    return {"success": False, "message": f"Invalid decision: {decision}"}



