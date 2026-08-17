# ZERO & Trading Bot — System Checkpoint & Restart State

**Date**: August 17, 2026  
**Status**: All services configured for 100% automated background execution on Windows startup.

---

## 1. Automated Windows Startup Configuration
- **Startup Entry**: `C:\Users\admin\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\ZERO_AutoStart.vbs`
- **Launcher Script**: [`F:\AI Automation\Projects\Zero\scripts\start_zero_background.ps1`](file:///F:/AI%20Automation/Projects/Zero/scripts/start_zero_background.ps1)
- **Behavior**: Launches automatically on every Windows login with zero manual interaction.

---

## 2. Active Services

### A. ZERO Personal AI Operating System
- **Location**: `F:\AI Automation\Projects\Zero`
- **Web Command Center**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Telegram Bot**: Long-polling daemon with automated briefing scheduler
- **Orchestrator**: Dual-Engine (LangGraph state machine + deterministic router) coordinating 13 native domain engines and 269 agency specialists
- **Test Suite**: 133 / 133 tests passing (100%)
- **Logs**: `F:\AI Automation\Projects\Zero\logs\zero.log`

### B. Unified Paper Trading Bot
- **Location**: `F:\AI Automation\Projects\Trading bot`
- **Runner**: [`paper_runner.py`](file:///F:/AI%20Automation/Projects/Trading%20bot/paper_runner.py)
- **Strategy Engines**:
  - `[1/4]` SELL Strategy Check (`paper_live.py`)
  - `[2/4]` SELL Outcome Tracker (`paper_outcome_tracker.py`)
  - `[3/4]` BUY Strategy Check (`paper_live_buy.py`)
  - `[4/4]` BUY Outcome Tracker (`paper_outcome_tracker_buy.py`)
- **MetaTrader 5 Bridge**: Connected to `VantageMarkets-Demo` (Login: `25931817`)
- **Alerts**: Hourly heartbeat status & daily performance summaries delivered to Telegram
- **Logs**: `F:\AI Automation\Projects\Trading bot\trading_bot.log`

---

## 3. Quick Control Commands

| Action | PowerShell Command |
| :--- | :--- |
| **Start All Services** | `cd "F:\AI Automation\Projects\Zero"; .\start_zero_background.ps1` |
| **Stop All Services** | `cd "F:\AI Automation\Projects\Zero"; .\stop_zero_background.ps1` |
| **Watch Trading Logs** | `Get-Content "F:\AI Automation\Projects\Trading bot\trading_bot.log" -Wait -Tail 30` |
| **Watch ZERO Logs** | `Get-Content "F:\AI Automation\Projects\Zero\logs\zero.log" -Wait -Tail 30` |

---

## 4. Post-Restart Verification Checklist
1. Log into Windows.
2. Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your browser (Zero Command Center should be ONLINE).
3. Send `Hello` or `/status` to your ZERO Telegram Bot.
4. Ensure **MetaTrader 5** application is open for live tick/candle updates.
