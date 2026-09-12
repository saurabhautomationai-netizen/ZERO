"""Automation & Workflow Specialist Worker for ZERO Engineering Organization.

Performs strictly READ-ONLY reverse-engineering, inspection, and auditing of
n8n workflows, webhook graphs, triggers, and integration pipelines.
Enforces execution guardrails preventing workflow mutations or webhook triggers.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any, Dict, List, Optional

from zero_core.engineering.discovery.policy import ReadOnlyPolicyEnforcer
from zero_core.engineering.workers.base import (
    EngineeringWorker,
    ProjectContextPackage,
    WorkerCapability,
    WorkerResult,
    WorkerStatus,
    WorkerType,
)

logger = logging.getLogger("zero.engineering.workers.automation")


class AutomationWorker(EngineeringWorker):
    """Specialist worker for auditing n8n workflows and webhook architectures in READ-ONLY mode."""

    def __init__(self):
        super().__init__(
            worker_id="worker_automation",
            name="Automation & Workflow Specialist",
            worker_type=WorkerType.NATIVE,
            capabilities=[
                WorkerCapability.AUTOMATION,
                WorkerCapability.WORKFLOW_AUDIT,
            ],
            risk_level="LOW",
            transport="IN_PROCESS_CALL",
        )
        self.enforcer = ReadOnlyPolicyEnforcer()

    def health_check(self) -> WorkerStatus:
        return WorkerStatus.AVAILABLE

    def run_task(self, context: ProjectContextPackage) -> WorkerResult:
        """Audits workflow JSON definitions in context strictly in read-only mode."""
        self.enforcer.verify_action_allowed("audit_workflows")

        workflows_found = []
        total_nodes = 0
        node_type_counts: Counter[str] = Counter()
        triggers_detected: List[str] = []
        integrations_detected: List[str] = []
        findings: List[str] = []

        for rel_path, content in context.relevant_files.items():
            if not rel_path.endswith(".json"):
                continue

            try:
                data = json.loads(content)
            except Exception:
                continue

            # Check if this JSON resembles an n8n workflow export (contains 'nodes' array)
            if isinstance(data, dict) and "nodes" in data and isinstance(data["nodes"], list):
                nodes = data["nodes"]
                wf_name = data.get("name", rel_path)
                num_nodes = len(nodes)
                total_nodes += num_nodes
                workflows_found.append({"path": rel_path, "name": wf_name, "node_count": num_nodes})

                for node in nodes:
                    if not isinstance(node, dict):
                        continue
                    ntype = node.get("type", "unknown")
                    nname = node.get("name", "")
                    node_type_counts[ntype] += 1

                    # Trigger detection
                    if "webhook" in ntype.lower() or "trigger" in ntype.lower():
                        triggers_detected.append(f"{nname} ({ntype}) in {rel_path}")

                    # Integration channel detection
                    if "telegram" in ntype.lower() or "telegram" in nname.lower():
                        if "Telegram" not in integrations_detected:
                            integrations_detected.append("Telegram")
                    elif "whatsapp" in ntype.lower() or "whatsapp" in nname.lower():
                        if "WhatsApp" not in integrations_detected:
                            integrations_detected.append("WhatsApp")
                    elif "postgres" in ntype.lower() or "supabase" in ntype.lower():
                        if "PostgreSQL / Supabase" not in integrations_detected:
                            integrations_detected.append("PostgreSQL / Supabase")
                    elif "gmail" in ntype.lower() or "email" in nname.lower():
                        if "Email / Gmail" not in integrations_detected:
                            integrations_detected.append("Email / Gmail")
                    elif "openAi" in ntype.lower() or "ai" in nname.lower() or "llm" in ntype.lower():
                        if "AI LLM Service" not in integrations_detected:
                            integrations_detected.append("AI LLM Service")

        if workflows_found:
            top_node_types = ", ".join(f"{k.split('.')[-1]}: {v}" for k, v in node_type_counts.most_common(5))
            summary = (
                f"Discovered {len(workflows_found)} workflow(s) comprising {total_nodes} total nodes. "
                f"Key node types: {top_node_types}. Integrations: {', '.join(integrations_detected) or 'Internal'}."
            )
            analysis = (
                f"Workflow Architecture:\n"
                + "\n".join(f"- **{w['name']}** (`{w['path']}`): {w['node_count']} nodes" for w in workflows_found)
                + f"\n\n**Connected Channels**: {', '.join(integrations_detected) or 'None'}\n"
                + f"**Triggers Identified**: {len(triggers_detected)} ({', '.join(triggers_detected[:4])})"
            )
        else:
            summary = "No n8n workflow definitions discovered in project context."
            analysis = "Scanned context files; no 'nodes' workflow graph schema was detected."

        return WorkerResult(
            task_id=context.task_id,
            worker_id=self.worker_id,
            status="SUCCESS",
            summary=summary,
            analysis=analysis,
            project_id=context.project_id,
            files_read=list(context.relevant_files.keys()),
            artifacts_created=[w["path"] for w in workflows_found],
            decisions={
                "workflow_count": str(len(workflows_found)),
                "total_nodes": str(total_nodes),
                "channels": ", ".join(integrations_detected),
            },
        )
