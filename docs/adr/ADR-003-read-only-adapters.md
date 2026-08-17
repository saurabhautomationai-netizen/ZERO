# ADR-003: Read-Only Finance and Trading Adapters

**Status**: Accepted  
**Date**: 2026-08-16  
**Deciders**: ZERO Core Team  

---

## Context
Two active sibling systems exist on the host machine:
1. **Trading Bot** (`../Trading bot`): A production MetaTrader 5 trading engine with execution pipelines, order routing, and risk management.
2. **Personal Finance Tracker** (`../Smart Finance AI Tracker/Personal Finance Tracker`): An automated 118-node n8n workflow writing financial records to a PostgreSQL database.

ZERO must interact with both systems to provide personal assistance without risking financial loss or data corruption.

## Problem
How should ZERO interface with external personal data systems without destabilizing live workflows, causing concurrency conflicts, or accidentally triggering unwanted trades or transaction mutations?

## Decision
All integrations into the Trading Bot and Finance Tracker are implemented as **strictly read-only adapters**:
- [`FinanceStatusAdapter`](file:///f:/AI%20Automation/Projects/Zero/zero_core/finance_status.py): Connects to Postgres strictly over a dedicated read-only database role (`zero_finance_reader`). Executes `SELECT` statements with parameterized queries; never writes.
- [`TradingStatusAdapter`](file:///f:/AI%20Automation/Projects/Zero/zero_core/trading_status.py): Parses generated status files (`trade_state*.json`, `last_signal_time.txt`) from disk. Never imports execution or bridge modules (`mt5_bridge`, `mt5_executor`, `MetaTrader5`), enforced by automated AST regression tests.

## Why We Made the Decision
1. **Safety by Construction**: Accidental execution of trades or mutation of ledger entries is architecturally prevented.
2. **Respect for Existing Infrastructure**: Sibling projects continue operating autonomously without modification.
3. **Auditability**: Explicit boundary enforcement ensures ZERO remains a safe assistant and query layer.

## Alternatives Considered
- **Direct Dual Read/Write Integration**: Rejected due to catastrophic risk of unintended live orders or double-booked transactions.
- **Reimplementing n8n and Trading Logic in ZERO**: Rejected because existing systems are already mature and operational.

## Consequences
- **Positive**: Absolute safety against unwanted side-effects; zero risk of corrupting database records or executing market orders.
- **Negative**: ZERO cannot place trades or insert transactions directly without introducing a subsequent, strictly-reviewed approval and write architecture (M5/M6).
