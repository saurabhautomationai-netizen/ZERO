# ZERO — Architecture

## 1. Master Conceptual Architecture

ZERO is designed as a modular, extensible, secure, testable, and observable personal AI Operating System platform:

```text
                         ZERO
             Personal AI Operating System
                              │
                ┌─────────────┴─────────────┐
                │                           │
          ZERO CORE                    INTERFACES
                │                    Telegram / Voice
                │                    Web / API
                │
        ┌───────┼────────┬──────────┐
        │       │        │          │
   Orchestrator Memory   RAG   Project Context
        │
   ┌────┴───────────────────────────────────┐
   │                                        │
Agent Registry                         Tool Registry
   │                                        │
   └────────────────┬───────────────────────┘
                    │
             SPECIALIZED AGENTS
                    │
    ┌───────────────┼───────────────────────┐
    │               │                       │
 Finance         Trading                  Email
 Agent            Agent                   Agent
    │               │                       │
 Calendar        Trading RAG             Gmail
 Agent               │
    │           Trading Coach
 Research           │
 Agent         Logs + Trades
    │           + Code + MT5
 Project
 Builder
 Agent
    │
 Coding / Git / Automation / Learning / Deployment
```

---

## 2. Reference Documents

- **SRS**: [`docs/SRS.md`](docs/SRS.md) — Comprehensive Software Requirements Specification (103/103 tests mapped)
- **ADRs**: [`docs/adr/`](docs/adr/) — Architecture Decision Records
  - [ADR-001: Native Agents in ZERO Repository](docs/adr/ADR-001-native-agents-in-zero-repo.md)
  - [ADR-002: Agency-agents Live Filesystem Index](docs/adr/ADR-002-agency-agents-live-index.md)
  - [ADR-003: Read-only Finance and Trading Adapters](docs/adr/ADR-003-read-only-adapters.md)
  - [ADR-004: Keyword/Token Routing Before Embedding-Based Routing](docs/adr/ADR-004-keyword-token-routing.md)
  - [ADR-005: LangGraph-Optional Orchestrator](docs/adr/ADR-005-langgraph-optional.md)
  - [ADR-006: Executor Behavior: Answer or Persona Handoff](docs/adr/ADR-006-executor-behavior.md)
  - [ADR-007: Trading Integration Scope — Signal State Only](docs/adr/ADR-007-trading-scope.md)
- **Roadmap**: [`docs/ROADMAP.md`](docs/ROADMAP.md) — Milestones M1 through M21
- **Folder Structure**: [`docs/FOLDER_STRUCTURE.md`](docs/FOLDER_STRUCTURE.md) — Directory layout blueprint

---

## 3. Core Principles & Isolation

Two mature, independent projects sit next to ZERO on disk:

- `../Trading bot` — Live MT5 trading system (execution engines, risk validator, live buy/sell runners).
- `../Smart Finance AI Tracker/Personal Finance Tracker` — 118-node n8n workflow ("Zero Finance Tracker") with real Telegram/WhatsApp intake and PostgreSQL `public.transactions`.
- `../Agency-agents` — Live indexed library of 269 specialist agent personas across 17 divisions.

ZERO coordinates across all three without duplicating or modifying them, using read-only adapters, least-privilege security roles, and human-in-the-loop approval gates.

## Folder structure

```
Zero/
  zero_core/
    config.py            # single source of truth for paths (mirrors
                          # Agency-agents' own divisions.json/tools.json
                          # pattern — see review notes below)
    agent_registry.py     # AgencyAgentsAdapter + AgentRegistry
    native_agents.py       # ZERO's own agent stubs (Finance/Trading/Email/Calendar)
    trading_status.py       # Phase 1.5: read-only Trading bot status adapter
    finance_status.py         # Phase 1.5b: read-only Finance Tracker (Postgres) adapter
    orchestrator.py             # routing skeleton (LangGraph-optional)
    bootstrap.py             # wires registry + orchestrator; the one entrypoint
                              # everything else (CLI/API/bot) should import
    memory/                  # Phase 2 placeholder — pgvector/Supabase RAG
    interfaces/
      telegram/              # Phase 2+ placeholder
      web/                    # Phase 2+ placeholder
    data/
      agency_agents_inventory.json   # bundled README-roster snapshot,
                                       # used only to enrich agency specs
                                       # with "when to use" text
  tests/
    test_agent_registry.py
    test_orchestrator.py
    conftest.py             # synthetic fake Agency-agents clone fixture
```

## Data flow (Phase 1)

```
task string
    |
    v
Orchestrator.run(task)
    |
    v
AgentRegistry.resolve(task)
    |
    +-- checks ZERO-native agents first (keyword match against
    |   native_agents.py's `keywords` tuples) — ZERO owns these domains,
    |   so they get first refusal
    |
    +-- falls back to AgencyAgentsAdapter.search() per significant word
    |   in the task, scanning the live clone at AGENCY_AGENTS_PATH
    |
    v
RegistryMatch(candidates=[...])  -> OrchestratorResult(selected, alternatives)
```

Nothing downstream of `selected` exists yet — Phase 1 stops at "here is
who should handle this," not "here is the answer." That boundary is
deliberate: routing quality can be tested and iterated on independently of
execution.

## Key architectural decisions

**1. Native agent personas live in this repo, not inside the Agency-agents
clone.** The original suggestion was to scaffold a `zero` division inside
the Agency-agents fork, using its existing frontmatter/lint conventions.
Rejected, because that repo tracks an external `origin/main` — mixing
personal, data-bound agent definitions into a tree meant for `git pull`
from a public upstream risks both merge conflicts and an accidental push
of personal context to a public fork. `native_agents.py` borrows the
*shape* of Agency-agents' AgentSpec model (frontmatter-like fields) without
borrowing its git history.

**2. The Agency-agents clone is read at query time, never copied.**
`AgencyAgentsAdapter.index()` walks the filesystem live. If you
`git pull` inside `Agency-agents/` to pick up new upstream agents, call
`registry.agency.index(force=True)` (or just restart the process) — no
ZERO code needs to change.

**3. Trading bot and Personal Finance Tracker are wrapped, not
rewritten.** `native_agents.py`'s `TRADING_AGENT` and `FINANCE_AGENT`
stubs are deliberately inert right now — seeing "NOT reimplement" spelled
out in the integration_note is the point. The concrete next steps for each
are described inline in that file. Trading bot in particular is flagged as
a safety decision (should ZERO ever get execute access?) that's yours to
make, not something to default into.

**4. Routing is naive keyword matching in Phase 1, on purpose.** Building
embedding-based routing before you have real usage data to tune against is
premature. The `AgentRegistry.resolve()` contract (task in, ranked
candidates out) is what matters for now — its internals can be replaced
wholesale once Memory/RAG exists, without touching the Orchestrator or any
future interface code.

**5. LangGraph is optional, not required, for Phase 1.** `orchestrator.py`
detects langgraph via `try/except ImportError` and falls back to a 3-line
pure-Python state machine. This means tests run in any environment, and
you can defer the `pip install langgraph` decision until you actually need
multi-node graphs with conditional edges — Phase 1's graph is a single
node, so LangGraph buys nothing yet.

## What's explicitly NOT built yet

- Memory/RAG (pgvector/Supabase) — `zero_core/memory/README.md` has the
  planned shape.
- Telegram/Voice interfaces — placeholders only.
- Live MT5 position/P&L data — `trading_status.py` reads only the four
  signal-state files; it does not query MT5. See its module docstring for
  why (no position ledger exists in those files; a live query is a
  separate, bigger scope decision).
- Any integration code inside Trading bot or Personal Finance Tracker
  themselves — those projects are untouched.
- Semantic/embedding-based routing.

## Delivered so far

- **Phase 1**: Agent Registry + Agency-agents Adapter + Orchestrator
  skeleton. Verified against the real 269-agent clone.
- **Phase 1.5**: `zero_core.trading_status.TradingStatusAdapter` —
  read-only status over Trading bot's `trade_state*.json` +
  `last_signal_time.txt`. Verified against real files from the live
  Trading bot project. A test (`test_adapter_never_imports_execution_modules`)
  guards against this module quietly growing an import of
  `mt5_bridge`/`mt5_executor` later.
- **Phase 1.5b**: `zero_core.finance_status.FinanceStatusAdapter` —
  read-only `get_recent_transactions()` / `get_category_totals()` against
  the real Postgres `transactions` table behind the Zero Finance Tracker
  n8n workflow. Requires `FINANCE_DB_URL` pointing at a DEDICATED
  read-only DB role (not yet created — exact `CREATE ROLE`/`GRANT` SQL is
  in the module's docstring; you run it, this code doesn't). Tests mock
  the DB connection entirely — no live database was touched building this.
  **Security note found along the way**: `.mcp.json` in the Finance
  Tracker project had a live n8n API key committed in plaintext — flagged
  separately, rotate it if you haven't yet.
- **Phase 1.6**: `zero_core.executors.execute()` + `Orchestrator.execute()`
  — closes the "Orchestrator only decides, doesn't invoke" gap, honestly:
  native agents backed by a real adapter (Trading, Finance) get actually
  executed (deterministic Python, no LLM); native agents without an
  adapter yet say so plainly instead of pretending; Agency-agents
  specialists are never faked into an answer — `execute()` returns
  `needs_llm=True` plus the raw persona text, for an interface layer
  (Phase 2) to actually pass to a model. Verified end-to-end against real
  Trading bot files (real answer) and the real absence of `FINANCE_DB_URL`
  (honest "not configured" message, not fabricated data). 33/33 tests pass.
- **Phase 1.7**: `zero_core/interfaces/web/` — `handlers.py` (pure logic:
  task routing/execution, agent listing, agent lookup) is fully unit
  tested with no FastAPI dependency at all. `app.py` is the FastAPI route
  wiring on top of it (`POST /task`, `GET /agents`, `GET /agents/{slug}`)
  — written but **never run**: the sandbox building this had no network
  access to install fastapi. Verify `app.py` yourself before trusting it;
  `handlers.py` is the part that's actually proven. 39/39 tests pass.

## Suggested next phase (your call on priority)

(1) Create the `zero_finance_reader` read-only role (SQL in
`finance_status.py`) and set `FINANCE_DB_URL`, then wire
`FinanceStatusAdapter` into `native_agents.FINANCE_AGENT` the same way
`trading_status` is wired to `TRADING_AGENT` — this is the fastest
remaining step to a real answer to "what did I spend on X"; (2) Memory/RAG,
once you have a concrete first use case (e.g. Trading Coach, once trade
history is in a query-able form) to build it against rather than in the
abstract; (3) if/when you decide ZERO should see live position/P&L, a
reviewed, explicitly-scoped MT5 read-query adapter — kept separate from
`trading_status.py` on purpose.
