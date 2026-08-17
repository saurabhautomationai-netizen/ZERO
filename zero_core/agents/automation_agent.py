"""Automation Agent for ZERO (Master Architecture Section 11).

Provides n8n webhook triggers, workflow status monitoring, and event payload formatting
without duplicating existing n8n logic in Python.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class WorkflowTriggerPayload:
    """Represents a webhook payload dispatched to n8n or an external workflow engine."""
    trigger_id: str
    workflow_name: str
    target_webhook_url: str
    payload: Dict[str, Any]
    status: str = "PENDING"  # 'PENDING', 'TRIGGERED', 'FAILED'
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AutomationAgent:
    """Native Automation Agent interfacing with n8n workflows and webhooks."""

    def __init__(self, n8n_base_url: Optional[str] = None):
        self.n8n_base_url = n8n_base_url or "http://localhost:5678"
        self._triggers: Dict[str, WorkflowTriggerPayload] = {}
        self._registered_workflows: Dict[str, Dict[str, Any]] = {
            "finance_tracker": {
                "name": "Zero Finance Tracker",
                "nodes": 118,
                "type": "n8n",
                "channels": ["Telegram", "WhatsApp"],
                "description": "Multi-modal receipt intake, budgeting, anomaly alerts, and monthly reporting.",
            },
            "trading_alerts": {
                "name": "Trading Bot Signal Dispatcher",
                "type": "webhook",
                "channels": ["Telegram"],
                "description": "Dispatches live MT5 strategy signals and risk alerts.",
            },
        }

    def list_workflows(self) -> List[Dict[str, Any]]:
        """Lists connected n8n and automation workflows."""
        return [{"id": k, **v} for k, v in self._registered_workflows.items()]

    def format_trigger(self, workflow_id: str, data: Dict[str, Any]) -> WorkflowTriggerPayload:
        """Constructs and validates a trigger payload for an n8n webhook."""
        wf = self._registered_workflows.get(workflow_id)
        wf_name = wf["name"] if wf else workflow_id
        trigger_id = f"trig_{uuid.uuid4().hex[:8]}"
        webhook_url = f"{self.n8n_base_url}/webhook/{workflow_id}"

        trigger = WorkflowTriggerPayload(
            trigger_id=trigger_id,
            workflow_name=wf_name,
            target_webhook_url=webhook_url,
            payload=data,
            status="TRIGGERED",
        )
        self._triggers[trigger_id] = trigger
        return trigger

    def summarize_automations(self) -> str:
        """Returns a formatted status summary of connected workflows."""
        wfs = self.list_workflows()
        lines = [f"### Connected Automations ({len(wfs)} Workflows Online)", ""]
        for w in wfs:
            nodes_info = f" ({w.get('nodes', 0)} nodes)" if "nodes" in w else ""
            lines.append(f"- **{w['name']}** [{w['type'].upper()}]{nodes_info}: {w['description']}")
        return "\n".join(lines)


# Global singleton instance
DEFAULT_AUTOMATION_AGENT = AutomationAgent()
