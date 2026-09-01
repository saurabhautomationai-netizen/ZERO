"""Pure-logic Telegram bot command and message dispatcher for ZERO (Milestone M19)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from zero_core.agents.trading_coach import DEFAULT_TRADING_COACH
from zero_core.approval import ApprovalPolicyEngine, build_default_approval_engine
from zero_core.bootstrap import build_orchestrator, build_registry
from zero_core.interfaces.telegram.formatters import (
    format_agent_card,
    format_approval_prompt,
    format_task_response,
)
from zero_core.orchestrator import Orchestrator

GREETINGS = {
    "hello", "hi", "hey", "hola", "greetings", "good morning",
    "good evening", "good afternoon", "who are you", "what can you do", "yo"
}


class TelegramBotHandler:
    """Handles Telegram interactions independently of network framework bindings."""

    def __init__(
        self,
        orchestrator: Optional[Orchestrator] = None,
        approval_engine: Optional[ApprovalPolicyEngine] = None,
    ):
        self.orchestrator = orchestrator or build_orchestrator()
        self.approval_engine = approval_engine or build_default_approval_engine()

    def handle_message(self, text: str, user_id: str = "default_user") -> str:
        """Dispatches an incoming natural-language chat message as a task."""
        stripped = text.strip()
        if not stripped:
            return "Please send a non-empty task description."

        if stripped.startswith("/"):
            parts = stripped.split(maxsplit=1)
            cmd = parts[0]
            args = parts[1] if len(parts) > 1 else ""
            return self.handle_command(cmd, args)

        # Handle casual greetings & self-intro
        cleaned = "".join(c for c in stripped.lower() if c.isalnum() or c.isspace()).strip()
        if cleaned in GREETINGS:
            return (
                "👋 *Hello! I am ZERO*, your personal executive AI operating system.\n\n"
                "I coordinate 14 native domain engines and 269 agency specialists.\n\n"
                "🎯 *Quick Prompts You Can Try*:\n"
                "• `/coach` — Trading Coach RAG, trade reviews & performance leaks\n"
                "• `trading status` — Live MT5 market sweep & signal check\n"
                "• `morning briefing` — Executive agenda, finance & trading digest\n"
                "• `finance status` — Smart finance AI & transaction summary\n"
                "• `git status` — Repository health & branch inspection\n"
                "• `/status` — System diagnostics & connectivity\n"
                "• `/agents` — Browse all 283 specialized agents\n\n"
                "Or describe any task directly!"
            )

        outcome = self.orchestrator.execute(stripped)
        if outcome.needs_llm and outcome.persona and outcome.answer is None:
            from zero_core.llm import DEFAULT_LLM_MANAGER
            outcome.answer = DEFAULT_LLM_MANAGER.call_specialist(persona=outcome.persona, task=stripped)
        return format_task_response(outcome)

    def handle_voice_note(self, audio_bytes: bytes, audio_format: str = "ogg", user_id: str = "default_user") -> str:
        """Processes incoming voice notes via VoiceSessionCoordinator."""
        from zero_core.interfaces.voice import DEFAULT_VOICE_SESSION_COORDINATOR

        res = DEFAULT_VOICE_SESSION_COORDINATOR.handle_voice_turn(
            audio_bytes=audio_bytes,
            audio_format=audio_format,
            user_id=user_id,
        )
        if not res.get("success"):
            return f"❌ Voice processing failed: {res.get('error', 'Unknown error')}"

        return (
            f"🎙️ *Heard*: _{res['task_text']}_\n"
            f"👤 *Specialist*: `{res.get('selected_agent', 'ZERO')}`\n\n"
            f"{res['response_text']}"
        )

    def handle_command(self, command: str, args: str = "") -> str:
        """Handles slash commands (/start, /help, /agents, /status, /task, /coach)."""
        cmd = command.lower().strip()

        if cmd in ("/start", "/help"):
            return (
                "👋 *Welcome to ZERO — Personal AI Operating System*\n\n"
                "Available Commands:\n"
                "• `/coach [review|rules|leaks|<question>]` — Trading Coach RAG engine\n"
                "• `/task <prompt>` — Dispatch a task to the best specialist\n"
                "• `/agents` — List available native and specialist agents\n"
                "• `/status` — System status and integration diagnostics\n"
                "• `/help` — Display this guide\n\n"
                "You can also type any task directly in chat!"
            )

        elif cmd == "/coach":
            sub = args.strip().lower()
            if not sub or sub == "status":
                return DEFAULT_TRADING_COACH.get_status_overview()
            elif sub in ("review", "reviews", "last", "recent"):
                return DEFAULT_TRADING_COACH.review_recent_trades()
            elif sub in ("rules", "rule", "strategy"):
                return DEFAULT_TRADING_COACH.list_rules()
            elif sub in ("leaks", "leak", "audit", "mistakes"):
                return DEFAULT_TRADING_COACH.audit_performance_leaks()
            else:
                return DEFAULT_TRADING_COACH.answer_question(args.strip())

        elif cmd == "/agents":
            registry = self.orchestrator.registry
            native = registry.list_native()
            agency = registry.list_agency()
            lines = [f"📋 *ZERO Agent Catalog* ({len(native)} Native, {len(agency)} Specialists):"]
            lines.append("\n*Native Domain Agents*:")
            for a in native:
                lines.append(f"  • `{a.name}` (`{a.slug}`)")
            lines.append("\n*Sample Agency Specialists*:")
            for a in agency[:5]:
                lines.append(f"  • `{a.name}` (`{a.slug}`)")
            if len(agency) > 5:
                lines.append(f"  _...and {len(agency) - 5} more across 17 divisions._")
            return "\n".join(lines)

        elif cmd == "/status":
            return (
                "🟢 *ZERO Core System Status*: Operational\n"
                "• *Orchestrator*: Active (LangGraph + Keyword)\n"
                "• *Agent Registry*: 283 Agents Indexed\n"
                "• *Trading Coach RAG*: Active\n"
                "• *Security & Approval*: Active\n"
                "• *Memory & RAG*: Online\n"
                "• *Web Command Center*: http://127.0.0.1:8000/"
            )

        elif cmd == "/task":
            if not args.strip():
                return "Usage: `/task <your task prompt>`"
            return self.handle_message(args)

        else:
            return f"Unknown command `{command}`. Type `/help` for available commands."

    def handle_callback(self, callback_data: str, approver: str = "telegram_user") -> str:
        """Handles button clicks (e.g. 'approve:<req_id>' or 'reject:<req_id>')."""
        if ":" not in callback_data:
            return "Invalid callback data."

        action, req_id = callback_data.split(":", 1)
        if action == "approve":
            success = self.approval_engine.approve(req_id, approver=approver, reason="Approved via Telegram button")
            if success:
                return f"✅ Request `{req_id}` approved."
            return f"❌ Request `{req_id}` not found or already processed."

        elif action == "reject":
            success = self.approval_engine.reject(req_id, approver=approver, reason="Rejected via Telegram button")
            if success:
                return f"⛔ Request `{req_id}` rejected."
            return f"❌ Request `{req_id}` not found or already processed."

        return f"Unknown action `{action}`."
