"""Finance domain tools for ZERO Tool Registry."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from zero_core.finance_status import FinanceDBUnavailable, FinanceStatusAdapter
from zero_core.tools.base import BaseTool, tool


class GetRecentTransactionsInput(BaseModel):
    limit: int = Field(default=10, description="Maximum number of recent transactions to return (1-100)")


class GetCategoryTotalsInput(BaseModel):
    since_date: Optional[str] = Field(default=None, description="Optional ISO date string (YYYY-MM-DD) to filter totals from")


@tool(
    name="finance_recent_transactions",
    description="Queries recent personal expense and income transactions from Postgres / Supabase database.",
    args_model=GetRecentTransactionsInput,
    risk_level="read_only",
)
def finance_recent_transactions_tool(limit: int = 10) -> List[Dict[str, Any]]:
    capped_limit = max(1, min(limit, 100))
    adapter = FinanceStatusAdapter()
    try:
        records = adapter.get_recent_transactions(limit=capped_limit)
        return [
            {
                "id": r.id,
                "amount": r.amount,
                "type": r.type,
                "date": str(r.transaction_date) if r.transaction_date else None,
                "category": r.category,
                "vendor": r.vendor,
                "platform": r.platform,
                "currency": r.currency,
                "notes": r.notes,
            }
            for r in records
        ]
    except Exception as exc:
        return [{"status": "unconfigured", "error": str(exc)}]


@tool(
    name="finance_category_totals",
    description="Aggregates spending totals grouped by category across transactions.",
    args_model=GetCategoryTotalsInput,
    risk_level="read_only",
)
def finance_category_totals_tool(since_date: Optional[str] = None) -> List[Dict[str, Any]]:
    adapter = FinanceStatusAdapter()
    from datetime import date
    parsed_date = None
    if since_date:
        try:
            parsed_date = date.fromisoformat(since_date)
        except ValueError:
            parsed_date = None

    try:
        totals = adapter.get_category_totals(since=parsed_date)
        return [
            {
                "category": t.category or "Uncategorized",
                "total_amount": t.total_amount,
                "currency": t.currency,
                "transaction_count": t.count,
            }
            for t in totals
        ]
    except Exception as exc:
        return [{"status": "unconfigured", "error": str(exc)}]


FINANCE_TOOLS: List[BaseTool] = [
    finance_recent_transactions_tool,
    finance_category_totals_tool,
]
