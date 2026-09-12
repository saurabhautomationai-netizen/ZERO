"""ZERO Task Execution Context.

Preserves structured execution context (project identity, intent, correlation,
explicit agent targets) across all orchestration, routing, and executor boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Optional


@dataclass
class TaskExecutionContext:
    """Structured execution context carrying task data across all orchestration layers."""

    raw_instruction: str
    directive: str
    explicit_agent_slug: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    repository_path: Optional[str] = None
    engineering_intent: Optional[str] = None
    target_milestone: Optional[str] = None
    source_interface: str = "web"
    correlation_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_task(
        cls,
        task: str,
        agent_slug: Optional[str] = None,
        project_id: Optional[str] = None,
        source_interface: str = "web",
        correlation_id: Optional[str] = None,
    ) -> "TaskExecutionContext":
        """Extracts structured project identity and intent once from the incoming task."""
        raw = task.strip() if task else ""

        # 1. Project ID
        extracted_pid = project_id
        if not extracted_pid:
            pid_match = re.search(
                r'(?im)^(?:\s*-\s*)?(?:project[_\s]id|proj_id|project_slug)\s*[:=]\s*([a-zA-Z0-9_\-]+)',
                raw,
            )
            if pid_match:
                extracted_pid = pid_match.group(1).strip()

        # 2. Project Name
        extracted_pname = None
        pname_match = re.search(
            r'(?im)^(?:\s*-\s*)?(?:project[_\s]name|project)\s*[:=]\s*([^\r\n]+)',
            raw,
        )
        if pname_match:
            cand = pname_match.group(1).strip().strip("'\"`")
            if not cand.lower().startswith(("id:", "path:", "location:")):
                extracted_pname = cand

        # 3. Repository Path
        extracted_repo = None
        repo_match = re.search(
            r'(?im)^(?:\s*-\s*)?(?:repository(?:\s*path)?|repo_path|repo|path|location)\s*[:=]\s*([^\r\n]+)',
            raw,
        )
        if repo_match:
            extracted_repo = repo_match.group(1).strip().strip("'\"`")

        # 4. Target Milestone
        extracted_milestone = None
        m_milestone = re.search(
            r'(?im)(?:execute|run|implement)\s+milestone\s+([a-zA-Z0-9_\-]+)',
            raw,
        )
        if m_milestone:
            extracted_milestone = m_milestone.group(1).strip()

        return cls(
            raw_instruction=raw,
            directive=raw,
            explicit_agent_slug=agent_slug,
            project_id=extracted_pid,
            project_name=extracted_pname,
            repository_path=extracted_repo,
            target_milestone=extracted_milestone,
            source_interface=source_interface,
            correlation_id=correlation_id,
        )
