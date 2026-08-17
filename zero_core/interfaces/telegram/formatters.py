"""Message and inline button formatters for Telegram interface (Milestone M19)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from zero_core.agent_registry import AgentSpec
from zero_core.approval.models import ApprovalRequest
from zero_core.executors import ExecutionResult


def format_agent_card(spec: AgentSpec) -> str:
    """Formats an agent specification for chat display."""
    lines = [
        f"🤖 *{spec.name}*",
        f"• *Division*: `{spec.division}`",
        f"• *Source*: `{spec.source}`",
        f"• *Slug*: `{spec.slug}`",
        "",
        f"_{spec.description}_",
    ]
    return "\n".join(lines)


def format_task_response(outcome: ExecutionResult) -> str:
    """Formats execution result for Telegram delivery."""
    if outcome.spec is None:
        return (
            "🔍 *ZERO*: No specialist matched this specific task.\n\n"
            "Try phrasing as a command or action:\n"
            "• `trading status` — Live MT5 market sweeps & signal check\n"
            "• `morning briefing` — Combined finance, agenda & trading digest\n"
            "• `finance summary` — Recent expenses & balance\n"
            "• `git status` — Repository health\n"
            "• Or type `/agents` to view all specialists."
        )

    header = f"🎯 *Dispatched to*: `{outcome.spec.name}`\n"
    if outcome.answer:
        return f"{header}\n{outcome.answer}"
    elif outcome.needs_llm and outcome.persona:
        return f"{header}\n⚡ *Persona Loaded*:\n{outcome.persona[:300]}..."
    return f"{header}\n(Task completed with no output)"


def format_approval_prompt(req: ApprovalRequest) -> Dict[str, Any]:
    """Formats an approval request with inline keyboard buttons."""
    text = (
        f"⚠️ *Security Approval Required*\n\n"
        f"• *Action*: `{req.action_type}`\n"
        f"• *Target*: `{req.target}`\n"
        f"• *Risk Level*: *{req.risk_level.value.upper()}*\n"
        f"• *Request ID*: `{req.request_id}`\n"
    )
    keyboard = [
        [
            {"text": "✅ Approve", "callback_data": f"approve:{req.request_id}"},
            {"text": "❌ Reject", "callback_data": f"reject:{req.request_id}"},
        ]
    ]
    return {
        "text": text,
        "reply_markup": {"inline_keyboard": keyboard},
    }
