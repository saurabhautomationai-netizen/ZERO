# Web interface — Verified (FastAPI + Pure Handlers)

`handlers.py` has all the business logic (task routing + execution, agent listing,
agent lookup) and is fully unit tested (`tests/test_web_handlers.py`).

`app.py` is the FastAPI route wiring on top of it:
- `POST /task`: Accepts `{ "task": string }` and returns decision, execution outcome, or persona handoff.
- `GET /agents?division=`: Lists native and agency agents with optional division filtering.
- `GET /agents/{slug}`: Retrieves specific agent metadata (or 404 if not found).

`app.py` is verified via automated ASGI tests in `tests/test_web_app.py`. To run locally:
```bash
uvicorn zero_core.interfaces.web.app:app --reload
```
