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
