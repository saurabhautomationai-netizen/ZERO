# ZERO — Target Folder Structure & Ecosystem Blueprint

**Version**: 1.0  
**Status**: Formalized (Milestone M1)  
**Date**: 2026-08-17  

---

## 1. System Ecosystem & Host Layout

ZERO operates as a central coordination OS alongside independent sibling projects under `F:\AI Automation\Projects\`:

```
F:\AI Automation\Projects\
├── Zero/                                 # [This Repository] Personal AI Operating System
│   ├── .venv/                            # Local virtual environment (Python 3.11+)
│   ├── docs/                             # Engineering specifications, SRS, ADRs, Roadmap
│   ├── zero_core/                        # Core OS routing, registry, executors, and adapters
│   └── tests/                            # Automated test suite (zero external dependencies)
│
├── Agency-agents/                        # Upstream clone of msitarzewski/agency-agents
│   ├── academic/                         # Specialist persona definitions (.md)
│   ├── engineering/
│   ├── finance/
│   ├── ... (17 total divisions, 269 agents)
│   └── divisions.json
│
├── Trading bot/                          # Live MT5 Trading Engine (Production System)
│   ├── trade_state.json                  # Signal state snapshot (read-only by ZERO)
│   ├── trade_state_buy.json              # Buy-side signal state
│   ├── trade_state_sell.json             # Sell-side signal state
│   ├── last_signal_time.txt              # Heartbeat timestamp
│   ├── mt5_bridge.py                     # Execution engine (FORBIDDEN to import into ZERO core)
│   └── risk_validator.py                 # Live risk validator
│
└── Smart Finance AI Tracker/             # Personal Finance Automation
    └── Personal Finance Tracker/         # 118-node n8n workflow system & Postgres database
        └── public.transactions           # Postgres transaction ledger (read-only by ZERO)
```

---

## 2. ZERO Repository Target Folder Structure

```
Zero/
├── .env.example                          # Environment variable template
├── .gitignore                            # Git ignore definitions
├── pytest.ini                            # Pytest configuration
├── requirements.txt                      # Project dependency specification
├── README.md                             # Quickstart & architectural summary
├── ARCHITECTURE.md                       # High-level architecture & reference map
│
├── docs/                                 # Engineering Documentation
│   ├── SRS.md                            # Software Requirements Specification (M1)
│   ├── FOLDER_STRUCTURE.md               # Target directory blueprint & module layout
│   ├── ROADMAP.md                        # Implementation roadmap (Milestones M1–M21)
│   └── adr/                              # Architecture Decision Records
│       ├── ADR-001-native-agents-in-zero-repo.md
│       ├── ADR-002-agency-agents-live-index.md
│       ├── ADR-003-read-only-adapters.md
│       ├── ADR-004-keyword-token-routing.md
│       ├── ADR-005-langgraph-optional.md
│       ├── ADR-006-executor-behavior.md
│       └── ADR-007-trading-scope.md
│
├── zero_core/                            # Core Operating System Package
│   ├── __init__.py                       # Package initialization
│   ├── config.py                         # Single source of truth for all paths & settings (M2)
│   ├── bootstrap.py                      # System bootstrap & CLI entrypoint factory (M2)
│   ├── agent_registry.py                 # AgencyAgentsAdapter + AgentRegistry (M4, M17)
│   ├── native_agents.py                  # ZERO-native agent specifications (M2)
│   ├── executors.py                      # Deterministic & handoff execution dispatcher (M2)
│   ├── orchestrator.py                   # State machine & LangGraph routing engine (M3)
│   ├── trading_status.py                 # Read-only Trading Bot status adapter (M10)
│   ├── finance_status.py                 # Read-only Finance Tracker Postgres adapter (M9)
│   │
│   ├── data/                             # Bundled Static Metadata Snapshots
│   │   └── agency_agents_inventory.json  # Roster snapshot for persona enrichment (M17)
│   │
│   ├── tools/                            # [Planned: M5] Tool Registry & Execution Layer
│   │   ├── __init__.py
│   │   ├── registry.py                   # Tool definition registry & schema reflection
│   │   ├── base.py                       # BaseTool abstract class
│   │   └── definitions/                  # Built-in tool implementations
│   │       ├── filesystem.py
│   │       └── web_search.py
│   │
│   ├── approval/                         # [Planned: M6] Human-in-the-Loop Approval System
│   │   ├── __init__.py
│   │   ├── engine.py                     # Policy engine & risk-tier evaluator
│   │   └── handlers.py                   # CLI/Web/Telegram confirmation handlers
│   │
│   ├── memory/                           # [Planned: M7, M8] Memory & Knowledge Base
│   │   ├── __init__.py
│   │   ├── README.md                     # Memory architecture guidelines
│   │   ├── session.py                    # Multi-turn conversational buffer (M7)
│   │   ├── store.py                      # Long-term entity & user preference store (M7)
│   │   └── vector_rag.py                 # pgvector / Supabase RAG retriever (M8)
│   │
│   ├── agents/                           # [Planned: M11–M16, M18] Domain Agent Implementations
│   │   ├── __init__.py
│   │   ├── trading_coach.py              # Trade history RAG explanation agent (M11)
│   │   ├── email_agent.py                # Gmail API triage & draft agent (M12)
│   │   ├── calendar_agent.py             # Calendar scheduling & conflict agent (M13)
│   │   ├── research_agent.py             # Autonomous web & synthesis agent (M14)
│   │   ├── project_builder.py            # Spec-to-Code generator (M15)
│   │   ├── coding_agent.py               # Local code refactoring & test agent (M16)
│   │   └── learning_agent.py             # Feedback loop & self-improvement (M18)
│   │
│   ├── interfaces/                       # Consumer Interface Bindings
│   │   ├── web/                          # Web & REST Interface (FastAPI) (M2)
│   │   │   ├── README.md
│   │   │   ├── handlers.py               # Pure, framework-free business logic (100% tested)
│   │   │   └── app.py                    # FastAPI route bindings
│   │   │
│   │   ├── telegram/                     # [Planned: M19] Telegram Bot Interface
│   │   │   ├── README.md
│   │   │   ├── bot.py                    # Telegram bot polling/webhook runner
│   │   │   └── formatters.py             # Message formatting & inline keyboard menus
│   │   │
│   │   └── voice/                        # [Planned: M19] Voice Interface
│   │       ├── transcriber.py            # Audio-to-text intake
│   │       └── synthesizer.py            # Text-to-speech output
│   │
│   └── observability/                    # [Planned: M20] Logging, Tracing & Security
│       ├── __init__.py
│       ├── logger.py                     # Structured JSON logging & audit trail
│       └── tracer.py                     # Latency & decision routing telemetry
│
└── tests/                                # Automated Unit & Integration Tests
    ├── conftest.py                       # Shared test fixtures (synthetic Agency-agents clone)
    ├── test_agent_registry.py            # 13 tests (token overlap, division filtering, lookup)
    ├── test_executors.py                 # 6 tests (deterministic execution & persona handoff)
    ├── test_finance_status.py            # 6 tests (mocked Postgres queries & error states)
    ├── test_trading_status.py            # 5 tests (state file parsing & AST execution guard)
    ├── test_orchestrator.py              # 5 tests (StateGraph & fallback state machine)
    ├── test_web_handlers.py              # 5 tests (web endpoint logic verification)
    ├── test_tools.py                     # [Planned: M5] Tool registry tests
    ├── test_approval.py                  # [Planned: M6] Approval system tests
    └── test_memory.py                    # [Planned: M7, M8] Memory & vector RAG tests
```

---

## 3. Key Design Principles & Architectural Invariants

1. **Config Centralization**: Every filesystem path, external directory reference, and environment variable MUST originate in `zero_core/config.py`. Hardcoded paths in submodules are strictly prohibited.
2. **Framework Decoupling**: Business logic in `zero_core` and `interfaces/*/handlers.py` must remain pure Python, free from framework lock-in (e.g. FastAPI, python-telegram-bot).
3. **Execution Safety Invariant**: Under no circumstances may `zero_core` modules import execution engines from `Trading bot` (`mt5_bridge`, `mt5_executor`, `MetaTrader5`). This invariant is enforced by static AST analysis in `tests/test_trading_status.py`.
4. **Honest Handoff Invariant**: Core code never simulates or hallucinates LLM completions. Native agents without active adapters return explicit status messages; Agency-agents specialists hand off raw persona text for consumer-side LLM invocation.
