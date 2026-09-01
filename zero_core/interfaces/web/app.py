"""FastAPI wiring only — see handlers.py for all actual logic."""

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from zero_core.interfaces.web import handlers

app = FastAPI(title="ZERO", version="0.1.0-phase1")

STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class TaskRequest(BaseModel):
    task: str


@app.get("/")
def get_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(str(index_file))
    return {"message": "ZERO Core API is active. See /docs for OpenAPI specifications."}


@app.post("/task")
@app.post("/api/task")
def post_task(body: TaskRequest):
    return handlers.handle_task(body.task)


@app.get("/agents")
@app.get("/api/agents")
def get_agents(division: Optional[str] = None):
    return handlers.handle_list_agents(division=division)


@app.get("/agents/{slug:path}")
@app.get("/api/agents/{slug:path}")
def get_agent(slug: str):
    result = handlers.handle_get_agent(slug)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No agent found for slug '{slug}'")
    return result


class ProjectActionRequest(BaseModel):
    action: str
    payload: Optional[dict] = None


@app.get("/engineering/projects")
@app.get("/api/v1/engineering/projects")
def list_engineering_projects():
    return handlers.handle_list_engineering_projects()


@app.get("/engineering/projects/{project_id}")
@app.get("/api/v1/engineering/projects/{project_id}")
def get_engineering_project(project_id: str):
    result = handlers.handle_get_engineering_project(project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No project found for ID '{project_id}'")
    return result


@app.post("/engineering/projects/{project_id}/action")
@app.post("/api/v1/engineering/projects/{project_id}/action")
def engineering_project_action(project_id: str, body: ProjectActionRequest):
    return handlers.handle_engineering_project_action(project_id, body.action, body.payload)


# -------------------------------------------------------------------------
# SALES & COMMERCIAL GROWTH ENDPOINTS
# -------------------------------------------------------------------------
@app.get("/saas-website")
def get_saas_website():
    saas_file = Path("F:/AI Automation/Projects/HR Recruitment Assistant/Dashboard/ai-recruitment-dashboard/public_website/index.html")
    if saas_file.is_file():
        return FileResponse(str(saas_file))
    return {"error": "SaaS website index.html not found"}


@app.post("/api/v1/sales/lead")
def post_sales_lead(body: dict):
    return handlers.handle_sales_lead(body)


@app.post("/api/v1/sales/demo")
def post_sales_demo(body: dict):
    return handlers.handle_sales_demo(body)


@app.post("/api/v1/sales/trial/signup")
def post_sales_trial_signup(body: dict):
    return handlers.handle_sales_trial_signup(body)


@app.get("/api/v1/sales/pipeline")
def get_sales_pipeline():
    return handlers.handle_sales_pipeline()


@app.get("/api/v1/sales/campaign/{channel}")
def get_sales_campaign(channel: str):
    return handlers.handle_sales_campaign(channel)


@app.get("/api/trading/status")
@app.get("/api/v1/trading/status")
def get_trading_status():
    from zero_core.trading_status import TradingStatusAdapter
    adapter = TradingStatusAdapter()
    status = adapter.get_status()
    return {
        "status": "ACTIVE",
        "last_signal_time": str(status.last_signal_time) if status.last_signal_time else None,
        "last_demo_signal_id": status.last_demo_signal_id,
        "summary": status.summary(),
        "combined": status.combined.raw if status.combined else None,
        "buy": status.buy.raw if status.buy else None,
        "sell": status.sell.raw if status.sell else None,
    }


# -------------------------------------------------------------------------
# AUTONOMOUS PATROL & HITL APPROVAL ENDPOINTS
# -------------------------------------------------------------------------
class ApprovalDecisionRequest(BaseModel):
    decision: str
    approver: Optional[str] = "user"
    reason: Optional[str] = None


@app.get("/api/patrol/status")
def get_patrol_status():
    return handlers.handle_patrol_status()


@app.post("/api/patrol/trigger")
def trigger_patrol():
    return handlers.handle_trigger_patrol()


@app.get("/api/approvals/pending")
def list_pending_approvals():
    return handlers.handle_list_pending_approvals()


@app.post("/api/approvals/{request_id}/decide")
def decide_approval(request_id: str, body: ApprovalDecisionRequest):
    return handlers.handle_decide_approval(
        request_id=request_id,
        decision=body.decision,
        approver=body.approver or "user",
        reason=body.reason,
    )


@app.post("/api/approvals/bulk-decide")
def bulk_decide_approvals(body: ApprovalDecisionRequest):
    return handlers.handle_bulk_decide_approvals(
        decision=body.decision,
        approver=body.approver or "user",
    )



