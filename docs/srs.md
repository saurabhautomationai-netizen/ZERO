# ZERO — Software Requirements Specification (SRS)

**Document Version**: 1.1  
**Status**: Formalized (Milestone M1)  
**Date**: 2026-08-17  
**Project**: ZERO (Personal AI Operating System)  

---

## 1. Executive Summary & Purpose

ZERO is a **Personal AI Operating System** that coordinates specialist agents across personal data domains, trading workflows, and analytical intelligence. Rather than rebuilding existing production capabilities, ZERO serves as a unified routing and execution orchestrator that connects:
1. **Sibling Projects**: Wraps the existing live `Trading bot` and `Smart Finance AI Tracker` without modifying or duplicating their core code.
2. **Specialist Catalog**: Indexes 269 specialist agent personas from `Agency-agents` (`msitarzewski/agency-agents`) dynamically at runtime.
3. **Native Domain Agents**: Executes custom ZERO-native agents with direct, read-only integration into local personal systems.

---

## 2. Milestone Roadmap & Implementation State Taxonomy

Requirements throughout this document are categorized using the official implementation states:
- **[Already Implemented]**: Fully developed, integrated, and covered by automated unit tests.
- **[Partially Implemented]**: Core logic/adapters built and tested; full external service wiring or live DB role configuration pending.
- **[Planned]**: Architecture and interfaces designed; implementation scheduled in upcoming milestones.
- **[Future]**: Long-term capabilities scheduled for post-core milestones.

### Roadmap Alignment Matrix

| Milestone | Capability Area | Status |
|---|---|---|
| **M1** | Formalization (SRS, Architecture, ADRs) | **Already Implemented** |
| **M2** | ZERO Core (Config, Native Stubs, Executors, Bootstrap) | **Already Implemented** |
| **M3** | Orchestrator (Decision & Execution State Machine) | **Already Implemented** |
| **M4** | Agent Registry (Unified Lookup & Ranking) | **Already Implemented** |
| **M5** | Tool Registry (OpenAPI / Function Calling Abstraction) | **Already Implemented** |
| **M6** | Approval System (Human-in-the-loop Guardrails) | **Already Implemented** |
| **M7** | Memory (Short/Long-term Entity & User State) | **Already Implemented** |
| **M8** | RAG (Vector Retrieval Store & Embeddings) | **Already Implemented** |
| **M9** | Finance Integration (Read-only Postgres Adapter) | **Partially Implemented** |
| **M10** | Trading Integration (Signal State Adapter) | **Partially Implemented** |
| **M11** | Trading Coach (Historical RAG Explanation Agent) | **Already Implemented** |
| **M12** | Email Agent (Gmail Triage & Drafting) | **Already Implemented** |
| **M13** | Calendar Agent (Scheduling & Conflict Resolution) | **Already Implemented** |
| **M14** | Research Agent (Autonomous Web & Document Synthesis) | **Already Implemented** |
| **M15** | Project Builder (Spec-to-Code Pipeline) | **Already Implemented** |
| **M16** | Coding & Git Agents (Local Codebase Refactoring) | **Already Implemented** |
| **M17** | Agency-agents Integration (Live 269 Persona Index) | **Already Implemented** |
| **M18** | Learning Agent (Feedback Loop & Optimization) | **Already Implemented** |
| **M19** | Voice & Telegram Interfaces | **Already Implemented** |
| **M20** | Observability & Security Hardening | **Already Implemented** |
| **M21** | Deployment (Containerization & Local Service Daemons) | **Already Implemented** |

---

## 3. Functional Requirements

### 3.1 Task Routing & Dispatch (M3, M4)
- **FR-ROUTE-01 [Already Implemented]**: The system MUST accept arbitrary natural-language task strings and return a ranked set of candidate agents (top candidate + up to 2 alternatives).
- **FR-ROUTE-02 [Already Implemented]**: Native domain agents MUST receive first refusal for queries matching their defined domain keywords before querying general specialists.
- **FR-ROUTE-03 [Already Implemented]**: Agency-agents specialist matching MUST use exact token overlap (alphanumeric tokens $\ge 3$ characters with stopword filtering) to eliminate false-positive substring collisions.
- **FR-ROUTE-04 [Already Implemented]**: The registry MUST support deterministic lookup by unique slug (e.g., `native/finance-agent` or `engineering/python-pro`).
- **FR-ROUTE-05 [Already Implemented]**: The registry MUST support listing and filtering agents by division.
- **FR-ROUTE-06 [Already Implemented]**: Semantic / embedding-based routing capability introduced in M8 via `VectorRAGStore`.

### 3.2 Agent Execution & Handoff (M2, M3)
- **FR-EXEC-01 [Already Implemented]**: Native agents with active adapters MUST execute deterministically in Python without invoking external LLMs.
- **FR-EXEC-02 [Already Implemented]**: Native agents without active adapters MUST return an explicit status stating that the agent is planned and not yet implemented, without fabricating data.
- **FR-EXEC-03 [Already Implemented]**: Selection of an Agency-agents specialist MUST return `needs_llm=True` with the raw persona markdown loaded from the filesystem, delegating the LLM prompt invocation to the consumer interface.
- **FR-EXEC-04 [Already Implemented]**: Orchestrator execution MUST support a LangGraph-compiled state machine when `langgraph` is present, and gracefully fallback to a pure-Python state machine when absent.

### 3.3 Native Agents (M2, M11, M12, M13, M14, M15, M16, M18, Section 11, Section 13, Section 14)
- **FR-NAT-01 [Already Implemented]**: `Finance Agent` (`native/finance-agent`) stub defined to own personal financial history, spending analysis, and budget tracking.
- **FR-NAT-02 [Already Implemented]**: `Trading Agent` (`native/trading-agent`) stub defined to interface with the live Trading bot system.
- **FR-NAT-03 [Already Implemented]**: `Trading Coach` (`native/trading-coach`) implemented with RAG-driven historical trade reviews and strategy performance explanations (`TradingCoachAgent`).
- **FR-NAT-04 [Already Implemented]**: `Email Agent` (`native/email-agent`) implemented for inbox triage, summarization, and draft generation (`EmailAgent`).
- **FR-NAT-05 [Already Implemented]**: `Calendar Agent` (`native/calendar-agent`) implemented for schedule tracking, conflict detection, and meeting briefs (`CalendarAgent`).
- **FR-NAT-06 [Already Implemented]**: `Research Agent` (`native/research-agent`) implemented for multi-source technical synthesis and technology evaluation matrices (`ResearchAgent`).
- **FR-NAT-07 [Already Implemented]**: `Project Builder` (`native/project-builder`) implemented to execute the Idea -> SRS -> Architecture -> ADRs -> Folder Structure -> Roadmap lifecycle (`ProjectBuilderAgent`).
- **FR-NAT-08 [Already Implemented]**: `Coding Agent` (`native/coding-agent`) implemented for AST parsing, code metrics, and unified refactoring diff generation (`CodingAgent`).
- **FR-NAT-09 [Already Implemented]**: `Git Agent` (`native/git-agent`) implemented for working tree inspection, conventional commit generation, and destructive command guardrails (`GitAgent`).
- **FR-NAT-10 [Already Implemented]**: `Learning Agent` (`native/learning-agent`) implemented for skill tracking, mastery progression, and revision quizzes (`LearningAgent`).
- **FR-NAT-11 [Already Implemented]**: `Automation Agent` (`native/automation-agent`) implemented to interface with n8n webhooks and monitor workflow health (`AutomationAgent`).
- **FR-NAT-12 [Already Implemented]**: `Briefing Agent` (`native/briefing-agent`) implemented to generate unified morning and evening executive briefings across finance, trading, email, and calendar (`BriefingAgent`).
- **FR-NAT-13 [Already Implemented]**: `Deployment Agent` (`native/deployment-agent`) implemented for subsystem diagnostic inspections and readiness reports (`DeploymentAgent`).

### 3.4 Agency-agents Integration (M17)
- **FR-AGY-01 [Already Implemented]**: System MUST index the local sibling repository (`../Agency-agents`) at runtime across all configured divisions (`config.AGENCY_AGENTS_DIVISIONS`).
- **FR-AGY-02 [Already Implemented]**: Frontmatter parsing MUST extract agent metadata (`name`, `description`, `color`) without requiring third-party YAML libraries.
- **FR-AGY-03 [Already Implemented]**: The adapter MUST enrich agents with "when to use" context from the bundled roster snapshot (`agency_agents_inventory.json`).
- **FR-AGY-04 [Already Implemented]**: In-memory caching MUST be utilized post-initialization, with forced re-indexing supported via `index(force=True)`.

### 3.5 Tool Registry (M5)
- **FR-TOOL-01 [Already Implemented]**: Base tool abstraction (`BaseTool`, `ToolResult`, `@tool`) generating OpenAPI/Function-calling compatible parameter schemas.
- **FR-TOOL-02 [Already Implemented]**: Pydantic schema validation for tool input arguments with graceful validation error reporting.
- **FR-TOOL-03 [Already Implemented]**: Safe built-in inspection tools (`read_file`, `list_directory`, `system_status`) with read caps and error guards.

### 3.6 Approval System (M6)
- **FR-APP-01 [Already Implemented]**: Risk-tier classification (`LOW`, `MEDIUM`, `HIGH`) for operations and tool executions.
- **FR-APP-02 [Already Implemented]**: Immediate auto-approval for low-risk actions and pending gate for high-risk/mutating operations.
- **FR-APP-03 [Already Implemented]**: Policy engine allowing registration of custom security evaluators to escalate action risk dynamically.

### 3.7 Memory Architecture (M7, Project Knowledge)
- **FR-MEM-01 [Already Implemented]**: Multi-turn conversation session history management (`SessionMemory`, `Message`) with configurable message window truncation.
- **FR-MEM-02 [Already Implemented]**: Long-term entity, user preferences, and configuration fact store (`EntityStore`) with JSON persistence.
- **FR-MEM-03 [Already Implemented]**: Project Knowledge System (`ProjectKnowledgeStore`) indexing purpose, architecture, stack, status, and roadmaps for existing projects.

### 3.8 Personal Finance Integration (M9)
- **FR-FIN-01 [Partially Implemented]**: Adapter MUST connect to the PostgreSQL database backing the "Zero Finance Tracker" n8n workflow using `FINANCE_DB_URL`.
- **FR-FIN-02 [Partially Implemented]**: Provide `get_recent_transactions(limit)` returning structured `TransactionRecord` instances from `public.transactions`.
- **FR-FIN-03 [Partially Implemented]**: Provide `get_category_totals(since)` computing aggregated expenditures grouped by category.
- **FR-FIN-04 [Already Implemented]**: All SQL executions MUST be strictly read-only and use parameterized queries.
- **FR-FIN-05 [Already Implemented]**: If `FINANCE_DB_URL` is unset or database connectivity fails, the adapter MUST raise `FinanceDBUnavailable` rather than returning empty or simulated records.

### 3.9 Trading System Integration (M10)
- **FR-TRD-01 [Partially Implemented]**: Adapter MUST read state from `trade_state.json`, `trade_state_buy.json`, `trade_state_sell.json`, and `last_signal_time.txt` located in the `Trading bot` repository.
- **FR-TRD-02 [Already Implemented]**: Adapter MUST return a unified `TradingStatus` snapshot including candle timestamps, stale counts, active trade flags, and signal IDs.
- **FR-TRD-03 [Already Implemented]**: The adapter MUST NEVER import MT5 execution modules (`mt5_bridge`, `mt5_executor`, `MetaTrader5`). This invariant is strictly verified by automated test assertions.
- **FR-TRD-04 [Already Implemented]**: Missing or malformed state files MUST degrade gracefully without crashing the host process.
- **FR-TRD-05 [Planned]**: Real-time position and account P&L reading (if approved) MUST be implemented in a distinct, explicitly-scoped read-only adapter (`MT5ReadOnlyAdapter`), completely isolated from signal state file reading.

### 3.10 Web Interface (M2)
- **FR-WEB-01 [Already Implemented]**: Core web handler logic MUST remain completely independent of web frameworks (zero FastAPI imports in `handlers.py`) to ensure 100% unit-testability.
- **FR-WEB-02 [Already Implemented]**: `POST /task` endpoint MUST accept JSON `{ "task": string }` and return routing decisions, execution answers, or persona handoffs.
- **FR-WEB-03 [Already Implemented]**: `GET /agents` endpoint MUST return listings of all native and agency agents with optional division filtering.
- **FR-WEB-04 [Already Implemented]**: `GET /agents/{slug}` endpoint MUST retrieve specific agent metadata or return a 404 response.
- **FR-WEB-05 [Already Implemented]**: FastAPI app route wiring in `app.py` verified via automated ASGI integration tests in `tests/test_web_app.py`.

### 3.11 Telegram & Voice Interfaces (M19)
- **FR-INT-01 [Already Implemented]**: Telegram Bot interface (`TelegramBotHandler`, `formatters`) allowing direct task dispatch, status queries, and interactive agent selection over chat.
- **FR-INT-02 [Already Implemented]**: Voice input and speech synthesis interface (`AudioTranscriber`, `SpeechSynthesizer`).

### 3.12 RAG & Vector Memory (M8, M11)
- **FR-RAG-01 [Already Implemented]**: Vector retrieval store (`VectorRAGStore`) with cosine similarity search and metadata filtering.
- **FR-RAG-02 [Already Implemented]**: Contextual retrieval pipeline supplying historical trade logs to `Trading Coach` (`TradingCoachAgent`).

### 3.13 Security & Isolation (M20)
- **FR-SEC-01 [Already Implemented]**: Dedicated read-only PostgreSQL role (`zero_finance_reader`) required for database access.
- **FR-SEC-02 [Already Implemented]**: Complete separation from live trade execution code to prevent unauthorized or unintended financial actions.
- **FR-SEC-03 [Already Implemented]**: All sensitive secrets, URLs, and tokens sanitized and redacted via `zero_core/observability/logger.py`.

### 3.14 Observability & Telemetry (M20)
- **FR-OBS-01 [Already Implemented]**: Structured JSON event logging (`StructuredLogger`) with timestamps, log levels, and custom metadata.
- **FR-OBS-02 [Already Implemented]**: Traceability and latency metrics across agent resolution and adapter invocation pipelines via `Tracer`.

### 3.15 Deployment & Environment (M21)
- **FR-DEP-01 [Already Implemented]**: Zero external runtime dependencies required for core test execution (100% mocked/fixture-driven test suite).
- **FR-DEP-02 [Already Implemented]**: Docker containerization (`Dockerfile`), `docker-compose.yml`, and local PowerShell startup scripts (`scripts/start_zero.ps1`, `scripts/run_tests.ps1`).

---

## 4. Non-Functional Requirements

### 4.1 Performance (NFR-PERF)
- **NFR-PERF-01 [Already Implemented]**: Agency-agents catalog indexing must complete in $< 500\text{ ms}$ on cold start and $< 50\text{ ms}$ on cached queries.
- **NFR-PERF-02 [Already Implemented]**: Task routing resolution (`AgentRegistry.resolve()`) must complete in $< 100\text{ ms}$.
- **NFR-PERF-03 [Partially Implemented]**: Finance queries must return within $< 200\text{ ms}$ under normal database conditions.
- **NFR-PERF-04 [Already Implemented]**: Trading file state reads must complete in $< 50\text{ ms}$.

### 4.2 Reliability & Fault Tolerance (NFR-REL)
- **NFR-REL-01 [Already Implemented]**: Test suite must pass 100% without active internet access, live databases, or live MT5 terminals.
- **NFR-REL-02 [Already Implemented]**: Absence of sibling project directories must trigger graceful degradation with descriptive error messaging, never unhandled process crashes.
- **NFR-REL-03 [Already Implemented]**: Malformed JSON in state files or syntax errors in individual agent frontmatters must be logged and bypassed without interrupting registry initialization.

### 4.3 Maintainability & Clean Architecture (NFR-MNT)
- **NFR-MNT-01 [Already Implemented]**: Single source of truth for filesystem paths consolidated in `zero_core/config.py`.
- **NFR-MNT-02 [Already Implemented]**: Separation of concerns between routing decisions (`Orchestrator.run()`) and agent invocation (`Orchestrator.execute()`).
- **NFR-MNT-03 [Already Implemented]**: Framework decoupling: interfaces and handlers carry pure business logic, remaining agnostic to web framework bindings.

---

## 5. Verification & Testing Matrix

| Requirement Area | Unit Tests | Verification Mechanism | Status |
|---|---|---|---|
| **Agent Registry & Indexing** | `tests/test_agent_registry.py` (13 tests) | Synthetic filesystem fixture | Verified (13/13 passing) |
| **Executors & Handoff** | `tests/test_executors.py` (6 tests) | Deterministic mock invocation | Verified (6/6 passing) |
| **Trading Coach Agent** | `tests/test_trading_coach.py` (3 tests) | Rule ingestion & RAG trade review | Verified (3/3 passing) |
| **Email Agent** | `tests/test_email_agent.py` (4 tests) | Inbox triage, search & draft creation | Verified (4/4 passing) |
| **Calendar Agent** | `tests/test_calendar_agent.py` (4 tests) | Conflict detection & meeting briefs | Verified (4/4 passing) |
| **Research Agent** | `tests/test_research_agent.py` (3 tests) | Multi-source synthesis & tech evaluation | Verified (3/3 passing) |
| **Project Builder Agent** | `tests/test_project_builder.py` (2 tests) | Inception pipeline & blueprint generation | Verified (2/2 passing) |
| **Coding Agent** | `tests/test_coding_agent.py` (4 tests) | AST analysis & unified diff generation | Verified (4/4 passing) |
| **Git Agent** | `tests/test_git_agent.py` (4 tests) | Working tree status & safety guardrails | Verified (4/4 passing) |
| **Learning Agent** | `tests/test_learning_agent.py` (3 tests) | Mastery tracking & diagnostic quizzes | Verified (3/3 passing) |
| **Automation Agent** | `tests/test_automation_agent.py` (3 tests) | n8n triggers & workflow monitoring | Verified (3/3 passing) |
| **Briefing Agent** | `tests/test_briefing_agent.py` (2 tests) | Daily executive briefs & aggregation | Verified (2/2 passing) |
| **Deployment Agent** | `tests/test_deployment_agent.py` (2 tests) | Subsystem health & diagnostics matrix | Verified (2/2 passing) |
| **Telegram Interface** | `tests/test_telegram_interface.py` (4 tests) | Bot commands, messages & callbacks | Verified (4/4 passing) |
| **Voice Interface** | `tests/test_voice_interface.py` (2 tests) | Transcription & speech synthesis | Verified (2/2 passing) |
| **Observability & Security** | `tests/test_observability.py` (4 tests) | JSON logging, redaction & latency traces | Verified (4/4 passing) |
| **Tool Registry** | `tests/test_tools.py` (10 tests) | Pydantic schema validation & tool execution | Verified (10/10 passing) |
| **Approval System** | `tests/test_approval.py` (6 tests) | Risk tier policy & escalation evaluation | Verified (6/6 passing) |
| **Memory (Session & Store)** | `tests/test_memory.py` (4 tests) | History window & JSON persistence | Verified (4/4 passing) |
| **Project Knowledge Store** | `tests/test_project_knowledge.py` (3 tests) | Project profiles, queries & status answers | Verified (3/3 passing) |
| **Vector RAG Store** | `tests/test_vector_rag.py` (3 tests) | Cosine similarity & metadata filtering | Verified (3/3 passing) |
| **Finance Adapter** | `tests/test_finance_status.py` (6 tests) | Mocked `psycopg2` cursor/connection | Verified (6/6 passing) |
| **Trading Adapter** | `tests/test_trading_status.py` (5 tests) | Synthetic state files & AST import scan | Verified (5/5 passing) |
| **Orchestrator** | `tests/test_orchestrator.py` (5 tests) | StateMachine & LangGraph fallback | Verified (5/5 passing) |
| **Web Handlers** | `tests/test_web_handlers.py` (5 tests) | Framework-independent handler tests | Verified (5/5 passing) |
| **Web FastAPI App** | `tests/test_web_app.py` (4 tests) | Direct ASGI endpoint request tests | Verified (4/4 passing) |
| **Telegram Runner** | `tests/test_telegram_runner.py` (3 tests) | Polling, auth whitelist, button callbacks | Verified (3/3 passing) |
| **MT5 Live Reader** | `tests/test_trading_live_reader.py` (3 tests) | Read-only equity format, AST security guard | Verified (3/3 passing) |
| **Bootstrap CLI** | `zero_core/bootstrap.py` | Manual CLI smoke test against real disk | Verified |
| **LLM Client Manager** | `tests/test_llm_client.py` (6 tests) | Gemini, Ollama, OpenAI & auto-detection | Verified (6/6 passing) |
| **Total Automated Tests** | **126 tests** | `pytest -q` | **100% Passing (126/126)** |