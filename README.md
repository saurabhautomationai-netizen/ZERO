# ZERO — Personal AI Operating System

A modular, extensible Personal AI Operating System featuring a unified **Agent Registry** (14 native domain agents + 269 Agency-agents specialist personas), an **Orchestrator** with LangGraph and fallback state machines, a **Tool Registry**, a multi-tiered **Approval System**, **Session & Entity Memory**, **Vector RAG**, **Observability & Security Tracing**, **Telegram & Voice Interfaces**, a **Web Command Center UI**, and a verified **FastAPI Web Service**.

---

## 1. Quickstart

```bash
cd Zero
python -m venv .venv
.venv\Scripts\activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Run the complete test suite (136 tests passing):
pytest -q
# or run via the PowerShell helper:
.\scripts\run_tests.ps1

# Launch the interactive terminal session:
python -m zero_core.cli

# Run the live bootstrap smoke test:
python -m zero_core.bootstrap

# Start the Web Command Center & API on http://127.0.0.1:8000:
.\scripts\start_zero.ps1
```

---

## 2. Architecture & Modules

| Module | Purpose | Status |
|---|---|---|
| [`zero_core/config.py`](file:///f:/AI%20Automation/Projects/Zero/zero_core/config.py) | Centralized single source of truth for paths & environment (.env auto-loader) | Complete |
| [`zero_core/agent_registry.py`](file:///f:/AI%20Automation/Projects/Zero/zero_core/agent_registry.py) | Dynamic indexer for 269 Agency specialists + unified keyword/token ranking | Complete |
| [`zero_core/native_agents.py`](file:///f:/AI%20Automation/Projects/Zero/zero_core/native_agents.py) | 14 Native domain agent specs (Finance, Trading, Trading Coach, Email, Calendar, Research, Project Builder, Coding, Git, Learning, Automation, Briefing, Deployment, News) | Complete |
| [`zero_core/orchestrator.py`](file:///f:/AI%20Automation/Projects/Zero/zero_core/orchestrator.py) | Dual-engine routing: LangGraph `StateGraph` + pure-Python fallback | Complete |
| [`zero_core/executors.py`](file:///f:/AI%20Automation/Projects/Zero/zero_core/executors.py) | Deterministic Python execution for native agents & persona handoff for Agency specialists | Complete |
| [`zero_core/llm/`](file:///f:/AI%20Automation/Projects/Zero/zero_core/llm/) | Multi-provider AI Model Client (Gemini API, Ollama, OpenAI, Offline Mock) | Complete |
| [`zero_core/tools/`](file:///f:/AI%20Automation/Projects/Zero/zero_core/tools/) | Tool registry, Pydantic argument validation & OpenAPI schema reflection | Complete |
| [`zero_core/approval/`](file:///f:/AI%20Approval/Projects/Zero/zero_core/approval/) | Risk-tier classification (`LOW`, `MEDIUM`, `HIGH`) and human-in-the-loop security engine | Complete |
| [`zero_core/memory/`](file:///f:/AI%20Automation/Projects/Zero/zero_core/memory/) | Multi-turn `SessionMemory`, `EntityStore`, `ProjectKnowledgeStore`, and `VectorRAGStore` | Complete |
| [`zero_core/agents/`](file:///f:/AI%20Automation/Projects/Zero/zero_core/agents/) | 14 Domain agents including `NewsAgent` (The Hindu real-time RSS aggregator), `TradingCoachAgent`, `EmailAgent`, `CalendarAgent`, `ResearchAgent`, `ProjectBuilderAgent`, `CodingAgent`, `GitAgent`, `LearningAgent`, `AutomationAgent`, `BriefingAgent`, `DeploymentAgent` | Complete |
| [`zero_core/observability/`](file:///f:/AI%20Automation/Projects/Zero/zero_core/observability/) | Structured JSON event logging, sensitive secret redaction, and `Tracer` telemetry | Complete |
| [`zero_core/interfaces/web/`](file:///f:/AI%20Automation/Projects/Zero/zero_core/interfaces/web/) | Web Command Center UI (`/`), framework-agnostic handlers & FastAPI ASGI service (`POST /task`, `GET /agents`) | Complete |
| [`zero_core/interfaces/telegram/`](file:///f:/AI%20Automation/Projects/Zero/zero_core/interfaces/telegram/) | Telegram bot polling runner (`TelegramBotRunner`) & message dispatcher with inline callback approval buttons | Complete |
| [`zero_core/interfaces/voice/`](file:///f:/AI%20Automation/Projects/Zero/zero_core/interfaces/voice/) | Voice transcription and speech synthesis payload formatters | Complete |
| [`zero_core/finance_status.py`](file:///f:/AI%20Automation/Projects/Zero/zero_core/finance_status.py) | Read-only adapter for Postgres finance tracking database | Tested & Ready |
| [`zero_core/trading_status.py`](file:///f:/AI%20Automation/Projects/Zero/zero_core/trading_status.py) | Read-only signal state file parser with static AST execution import enforcement | Tested & Ready |
| [`zero_core/trading_live_reader.py`](file:///f:/AI%20Automation/Projects/Zero/zero_core/trading_live_reader.py) | Strictly read-only MT5 live position, balance, equity, and margin stream reader (ADR-007 guarded) | Tested & Ready |

---

## 3. Test Suite (136/136 Passing)

```bash
pytest -q
```

All 126 tests are fixture-driven and run in under 2 seconds without requiring external network connectivity, live databases, or running MT5 instances.
