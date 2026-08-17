# ADR-003: Read-Only Adapters for Trading Bot and Finance Tracker

**Date**: 2026-08-16  
**Status**: Accepted  
**Deciders**: ZERO Core Team  

---

## Context

ZERO coordinates with two mature sibling projects:
1. **Trading Bot** — Live MT5 system with execution engines (`mt5_bridge.py`, `mt5_executor.py`, `paper_live_buy/sell.py`, `risk_validator.py`)
2. **Smart Finance AI Tracker** — 118-node n8n workflow writing to Postgres (`public.transactions`, `public.users`)

ZERO must NOT reimplement these systems.

## Decision

**Both integrations are read-only adapters** that expose a minimal, safe slice of data:

| Adapter | Source | Operations | Safety Guard |
|---------|--------|------------|--------------|
| `TradingStatusAdapter` | `trade_state*.json`, `last_signal_time.txt` | `get_status()` → signal state only | Test forbids `import mt5_bridge/mt5_executor/MetaTrader5` |
| `FinanceStatusAdapter` | Postgres `public.transactions` | `get_recent_transactions()`, `get_category_totals()` | Requires dedicated read-only DB role; raises `FinanceDBUnavailable` if not configured |

Neither adapter writes. Neither adapter calls execution code.

## Consequences

### Positive
- **Safety by construction** — Trading adapter physically cannot place trades (enforced by test)
- **Clear scope boundary** — "signal state only" for Trading; "transactions only" for Finance
- **No schema coupling** — Adapters read raw fields, don't reinterpret strategy internals

### Negative
- **Limited visibility** — Trading positions/P&L require live MT5 query (separate scope)
- **Finance features in n8n/Sheets unavailable** — Budget alerts, forecasting, credit cards stay in n8n

## Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| Full Trading bot integration (read + write) | Safety risk; execution adjacent even if read-only MT5 query |
| Replicate n8n features in ZERO | Violates "don't reimplement" — n8n already does this well |
| Direct MT5 connection for positions | Bigger scope; requires reviewed decision (ADR-007) |

## Implementation Notes
- `TradingStatusAdapter` — `BotStateSnapshot.raw` carries full JSON for unmodeled fields
- `FinanceStatusAdapter` — Opens short-lived connection per call (no pool needed for personal use)
- Both raise explicit errors on missing config rather than returning empty data

## References
- `zero_core/trading_status.py` — implementation + test guard
- `zero_core/finance_status.py` — implementation + read-only role SQL
- `ARCHITECTURE.md` — "Key Architectural Decisions #3", "Delivered so far"