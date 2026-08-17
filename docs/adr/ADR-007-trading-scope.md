# ADR-007: Trading Integration Scope — Signal State Only

**Status**: Accepted  
**Date**: 2026-08-16  
**Deciders**: ZERO Core Team  

---

## Context
The sibling `Trading bot` project maintains real-time strategy state across four local files:
- `trade_state.json` (combined state)
- `trade_state_buy.json` (buy-side state)
- `trade_state_sell.json` (sell-side state + `last_demo_signal_id`)
- `last_signal_time.txt` (timestamp string)

These files contain signal-detection data: last evaluated candle time, stale counters, active trade flags, and SMC pattern detection memory. They do NOT contain live open position tickets, execution lot sizes, or real-time MT5 P&L.

## Problem
Should ZERO query the live MetaTrader 5 terminal directly for open positions and account P&L, or restrict its current integration to reading signal state files?

## Decision
[`TradingStatusAdapter`](file:///f:/AI%20Automation/Projects/Zero/zero_core/trading_status.py) is strictly scoped to reading and parsing the four signal-state files on disk. It will NOT connect to live MT5 or import execution modules (`mt5_bridge`, `mt5_executor`, `MetaTrader5`).

If live position or account balance queries are required in future milestones, they MUST be implemented as an isolated, explicitly-reviewed adapter (e.g. `MT5ReadOnlyAdapter`) under a separate ADR.

## Why We Made the Decision
1. **Safety Boundary**: Reading static JSON/text files from disk is completely decoupled from trade execution pipelines.
2. **Terminal Stability**: Prevents ZERO from interfering with active MT5 IPC connections or execution locks held by the live trading bot.
3. **Transparent Reporting**: Accurately reports bot heartbeat and signal activity without conflating signal state with account balance.

## Alternatives Considered
- **Direct MT5 API Connection in `TradingStatusAdapter`**: Rejected to avoid execution adjacency and potential race conditions with live bot runners.
- **Parsing Deal History Cache Files**: Rejected because deal caches do not represent current open positions.

## Consequences
- **Positive**: Absolute protection against trading side-effects; fast file-based inspection.
- **Negative**: Queries regarding open position P&L or account equity cannot be answered until a dedicated MT5 read adapter is formally approved and implemented.
