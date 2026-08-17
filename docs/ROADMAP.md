# ZERO — Implementation Roadmap (Milestones M1–M21)

**Version**: 1.0  
**Status**: Formalized (Milestone M1)  
**Date**: 2026-08-17  

---

## 1. Roadmap Overview & Status Summary

| Milestone | Capability | Status | Primary Output Files |
|---|---|---|---|
| **M1** | Formalization (SRS, Architecture, ADRs, Structure) | **Complete** | `docs/SRS.md`, `docs/adr/*`, `docs/FOLDER_STRUCTURE.md` |
| **M2** | ZERO Core (Config, Stubs, Executors, Bootstrap, Web) | **Complete** | `zero_core/config.py`, `native_agents.py`, `executors.py`, `bootstrap.py` |
| **M3** | Orchestrator (LangGraph & Fallback State Machine) | **Complete** | `zero_core/orchestrator.py` |
| **M4** | Agent Registry (Token Overlap & Lookup) | **Complete** | `zero_core/agent_registry.py` |
| **M5** | Tool Registry (Tool Abstraction & Schema Reflection) | **Complete** | `zero_core/tools/` |
| **M6** | Approval System (Human-in-the-loop Guardrails) | **Complete** | `zero_core/approval/` |
| **M7** | Memory (Short-term Sessions & Entity Store) | **Complete** | `zero_core/memory/session.py`, `zero_core/memory/store.py` |
| **M8** | RAG (pgvector / Vector Retrieval Store) | **Complete** | `zero_core/memory/vector_rag.py` |
| **M9** | Finance Integration (Postgres DB Role & Live Verification) | **Partial** | `zero_core/finance_status.py` (needs `FINANCE_DB_URL` role) |
| **M10** | Trading Integration (Signal State Adapter & Live Smoke Tests) | **Partial** | `zero_core/trading_status.py` (signal state verified) |
| **M11** | Trading Coach (Trade Log RAG & Historical Analysis) | **Complete** | `zero_core/agents/trading_coach.py` |
| **M12** | Email Agent (Gmail Triage & Drafting) | **Complete** | `zero_core/agents/email_agent.py` |
| **M13** | Calendar Agent (Calendar Read/Write & Scheduling) | **Complete** | `zero_core/agents/calendar_agent.py` |
| **M14** | Research Agent (Autonomous Search & Synthesis) | **Complete** | `zero_core/agents/research_agent.py` |
| **M15** | Project Builder (SRS-to-Code Pipeline) | **Complete** | `zero_core/agents/project_builder.py` |
| **M16** | Coding & Git Agents (Local Code Refactoring) | **Complete** | `zero_core/agents/coding_agent.py`, `zero_core/agents/git_agent.py` |
| **M17** | Agency-agents Integration (269 Persona Live Index) | **Complete** | `zero_core/agent_registry.py`, `zero_core/data/` |
| **M18** | Learning Agent (Continuous Optimization & Feedback) | **Complete** | `zero_core/agents/learning_agent.py` |
| **M19** | Voice & Telegram Interfaces | **Complete** | `zero_core/interfaces/telegram/`, `zero_core/interfaces/voice/` |
| **M20** | Observability & Security Hardening | **Complete** | `zero_core/observability/` |
| **M21** | Deployment (Containerization & Windows Services) | **Complete** | `Dockerfile`, `docker-compose.yml`, `scripts/` |

---

## 2. Milestone Deep Dives & Acceptance Criteria

### Milestone M1 — Formalization [COMPLETE]
- **Deliverables**: SRS specification (`docs/SRS.md`), ADR records 001–007 (`docs/adr/`), Ecosystem Blueprint (`docs/FOLDER_STRUCTURE.md`), and Implementation Roadmap (`docs/ROADMAP.md`).
- **Acceptance Criteria**: All documents formalize existing codebase state and future trajectory without code modification. 39/39 tests passing.

---

### Milestone M2 — ZERO Core [COMPLETE]
- **Deliverables**: Centralized configuration (`config.py`), 5 native agent stubs (`native_agents.py`), execution dispatcher (`executors.py`), bootstrap factory (`bootstrap.py`), framework-agnostic web handlers (`interfaces/web/handlers.py`), and FastAPI route bindings (`interfaces/web/app.py` verified).
- **Acceptance Criteria**: All paths single-sourced in `config.py`. All native slugs mapped in `NATIVE_EXECUTORS`. Automated ASGI test suite passing.

---

### Milestone M3 — Orchestrator [COMPLETE]
- **Deliverables**: `Orchestrator` class providing `run()` for routing decisions and `execute()` for agent dispatch. LangGraph `StateGraph` support with automated pure-Python state machine fallback.
- **Acceptance Criteria**: 5/5 orchestrator unit tests passing without requiring `langgraph` in CI/test environments.

---

### Milestone M4 & M17 — Agent Registry & Agency-agents [COMPLETE]
- **Deliverables**: `AgencyAgentsAdapter` for dynamic filesystem indexing of 269 Agency-agents across 17 divisions. `AgentRegistry` providing unified lookup, native first-refusal, and exact token-overlap scoring.
- **Acceptance Criteria**: 13/13 agent registry unit tests passing. Token overlap eliminates substring false positives.

---

### Milestone M5 — Tool Registry [COMPLETE]
- **Deliverables**: `zero_core/tools/base.py` (`BaseTool`, `ToolResult`, `@tool`), `zero_core/tools/registry.py` (`ToolRegistry`), and `zero_core/tools/definitions/filesystem.py` (safe filesystem & system tools).
- **Acceptance Criteria**: 10 unit tests in `tests/test_tools.py` verifying Pydantic schema generation, argument validation, and execution.

---

### Milestone M6 — Approval System [COMPLETE]
- **Deliverables**: `zero_core/approval/models.py` (`RiskLevel`, `ApprovalStatus`, `ApprovalRequest`) and `zero_core/approval/engine.py` (`ApprovalPolicyEngine`).
- **Acceptance Criteria**: 6 unit tests in `tests/test_approval.py` verifying auto-approval of low risk, hold/escalation of high risk, and custom evaluator hooks.

---

### Milestone M7 — Memory (Session & Store) [COMPLETE]
- **Deliverables**: `zero_core/memory/session.py` (`SessionMemory`, `Message`) and `zero_core/memory/store.py` (`EntityStore`).
- **Acceptance Criteria**: 4 unit tests in `tests/test_memory.py` verifying multi-turn message history, window truncation, entity key-value CRUD, and JSON file persistence.

---

### Milestone M8 — RAG (Retrieval-Augmented Generation) [COMPLETE]
- **Deliverables**: `zero_core/memory/vector_rag.py` (`VectorRAGStore`, `VectorDocument`, `default_embedder`) with deterministic CRC32 feature hashing and cosine similarity.
- **Acceptance Criteria**: 3 unit tests in `tests/test_vector_rag.py` verifying document indexing, metadata filtering, and semantic relevance ranking.

---

### Milestone M11 — Trading Coach [COMPLETE]
- **Deliverables**: `zero_core/agents/trading_coach.py` (`TradingCoachAgent`, `TradeLogRecord`, `DEFAULT_TRADING_COACH`) and wired into `zero_core/executors.py:execute()`.
- **Acceptance Criteria**: 3 unit tests in `tests/test_trading_coach.py` verifying rule ingestion, trade reviews, RAG question-answering, and executor dispatch.

---

### Milestone M12 — Email Agent [COMPLETE]
- **Deliverables**: `zero_core/agents/email_agent.py` (`EmailAgent`, `EmailMessage`, `DEFAULT_EMAIL_AGENT`) and wired into `zero_core/executors.py:execute()`.
- **Acceptance Criteria**: 4 unit tests in `tests/test_email_agent.py` verifying inbox triage, summary generation, draft creation, and executor dispatch.

---

### Milestone M13 — Calendar Agent [COMPLETE]
- **Deliverables**: `zero_core/agents/calendar_agent.py` (`CalendarAgent`, `CalendarEvent`, `DEFAULT_CALENDAR_AGENT`) and wired into `zero_core/executors.py:execute()`.
- **Acceptance Criteria**: 4 unit tests in `tests/test_calendar_agent.py` verifying schedule listing, conflict detection, meeting briefs, and executor dispatch.

---

### Milestone M19 — Voice & Telegram Interfaces [COMPLETE]
- **Deliverables**: `zero_core/interfaces/telegram/` (`TelegramBotHandler`, inline keyboard formatters) and `zero_core/interfaces/voice/` (`AudioTranscriber`, `SpeechSynthesizer`).
- **Acceptance Criteria**: 6 unit tests in `tests/test_telegram_interface.py` and `tests/test_voice_interface.py` verifying message routing, callback approval handling, and voice I/O formatting.

---

### Milestone M20 — Observability & Security [COMPLETE]
- **Deliverables**: `zero_core/observability/logger.py` (`StructuredLogger`, secret redaction) and `zero_core/observability/tracer.py` (`Tracer`, `TraceSpan`).
- **Acceptance Criteria**: 4 unit tests in `tests/test_observability.py` verifying JSON event logging, sensitive password redaction, and execution latency timing.

---

### Milestone M21 — Deployment & Operations [COMPLETE]
- **Deliverables**: Multi-stage `Dockerfile`, `docker-compose.yml` (ZERO + pgvector PostgreSQL), and local Windows startup scripts (`scripts/start_zero.ps1`, `scripts/run_tests.ps1`).
- **Acceptance Criteria**: Ready-to-run container and local service definitions.
