# ADR-007: Trading Integration Scope — Signal State Only (No Positions/P&L)

**Date**: 2026-08-16  
**Status**: Accepted  
**Deciders**: ZERO Core Team  

---

## Context

The Trading Bot project maintains signal-detection state in four files:
- `trade_state.json` — combined state
- `trade_state_buy.json` — buy-side state
- `trade_state_sell.json` — sell-side state + `last_demo_signal_id`
- `last_signal_time.txt` — timestamp

These files contain: last candle time, stale count, `active_buy_trade` flag, pending SMC pattern memory (sweep/MSS/retest-zone/displacement).

**They do NOT contain**: entry price, lot size, stop/target, live P&L, open position list.

Real-time position data requires a live MT5 query via `mt5_bridge.py` — which is execution-adjacent code.

## Decision

**`TradingStatusAdapter` reads ONLY the four signal-state files.** It explicitly does not:
- Import `mt5_bridge`, `mt5_executor`, or `MetaTrader5` (enforced by `test_adapter_never_imports_execution_modules`)
- Query live MT5 for positions/P&L
- Attempt to reconstruct positions from deal history

The adapter returns `TradingStatus` with:
- `combined`, `buy`, `sell` → `BotStateSnapshot` (last_candle_time, stale_count, active_buy_trade, raw JSON)
- `last_signal_time` → parsed datetime
- `last_demo_signal_id` → from sell state

**If live position/P&L is needed later**, it will be a **separate, explicitly-scoped adapter** (e.g., `MT5ReadOnlyAdapter`) with its own ADR and safety review.

## Consequences

### Positive
- **Safety by test** — execution imports caught at test time
- **Clear scope** — "what's the bot's last signal / is a buy trade active" answered honestly
- **No execution adjacency** — reading JSON files is fundamentally different from querying MT5

### Negative
- **Incomplete picture** — user sees signal state, not actual positions
- **Potential confusion** — "trading status" ≠ "account status"

## Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| Add MT5 read query to TradingStatusAdapter | Scope creep; execution-adjacent; requires reviewed safety decision |
| Parse `synced_deals.json` for positions | File only has deal IDs, not position data |
| Call `mt5_bridge` from adapter | Violates ADR-003 (read-only, no execution imports) |

## Migration Path (If Position Access Needed)
1. Write ADR for `MT5ReadOnlyAdapter` with explicit scope
2. Implement as separate class in `zero_core/trading_positions.py`
3. Add safety review checklist (read-only MT5, no order_send, connection pooling)
4. Wire into `TRADING_AGENT` executor as optional enhancement
5. Keep `TradingStatusAdapter` unchanged for signal-state queries

## References
- `zero_core/trading_status.py` — implementation + docstring
- `tests/test_trading_status.py::test_adapter_never_imports_execution_modules` — guard test
- `zero_core/native_agents.py:TRADING_AGENT.integration_note` — documents limitation
- `ARCHITECTURE.md` — "Key Architectural Decisions #3", "What's explicitly NOT built"