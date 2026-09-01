"""Transport abstraction and Manual Transport Engine for External Engineering Workers.

Provides transport definitions (API, SDK, CLI, MCP, LOCAL_PROCESS, MANUAL_TRANSPORT)
and safe clipboard/prompt exchange handling for development and fallback modes.
"""

from __future__ import annotations

import enum
import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from zero_core.engineering.workers.base import (
    ProjectContextPackage,
    WorkerCapability,
    WorkerResult,
    WorkerStatus,
)

logger = logging.getLogger("zero.engineering.workers.transport")


class TransportType(str, enum.Enum):
    """Transport protocol used to invoke external workers."""
    API = "API"                          # Direct REST / HTTP API
    SDK = "SDK"                          # Official client SDK
    CLI = "CLI"                          # Local command line binary (e.g. agy --print)
    MCP = "MCP"                          # Model Context Protocol
    LOCAL_PROCESS = "LOCAL_PROCESS"      # Spawned daemon or subprocess
    WEBHOOK = "WEBHOOK"                  # Outbound webhook callback
    MANUAL_TRANSPORT = "MANUAL_TRANSPORT"# Human-in-the-loop clipboard / prompt queue
    NOT_CONFIGURED = "NOT_CONFIGURED"    # Missing credentials / binary setup
    UNAVAILABLE = "UNAVAILABLE"          # Endpoint down / network offline


@dataclass
class TransportConfig:
    """Operational settings for an external worker transport."""
    transport_type: TransportType = TransportType.MANUAL_TRANSPORT
    endpoint: Optional[str] = None
    model_name: Optional[str] = None
    timeout_seconds: float = 60.0
    max_retries: int = 2
    retry_backoff_seconds: float = 1.5
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class ManualTaskPackage:
    """Exportable, sanitized task package presented to a human operator."""
    package_id: str
    task_id: str
    project_id: str
    project_name: str
    target_worker: str
    created_at: str
    task_title: str
    task_description: str
    acceptance_criteria: List[str]
    constraints: List[str]
    relevant_files: Dict[str, str]
    instructions_for_human: str
    expected_response_format: str
    forbidden_items: List[str] = field(default_factory=lambda: [
        ".env files and production credentials",
        "Modifications outside target repository path",
        "Destructive Git commands (e.g. force push, reset --hard)",
        "Modifications to ZERO core codebase",
    ])

    def to_formatted_prompt(self) -> str:
        """Renders an unambiguous, copy-pasteable prompt for ChatGPT or Antigravity."""
        files_section = []
        for path, content in self.relevant_files.items():
            files_section.append(f"### File: {path}\n```\n{content}\n```\n")

        prompt_lines = [
            f"# ZERO Autonomous AI Engineering Organization — Task Dispatch",
            f"**Target Worker**: {self.target_worker}",
            f"**Project**: {self.project_name} (`{self.project_id}`)",
            f"**Task**: {self.task_title} (`{self.task_id}`)",
            f"**Generated**: {self.created_at}",
            "",
            "## 1. Task Objective",
            self.task_description,
            "",
            "## 2. Acceptance Criteria",
            "\n".join(f"- [ ] {crit}" for crit in self.acceptance_criteria) if self.acceptance_criteria else "- [ ] Task completed according to specification",
            "",
            "## 3. Strict Constraints & Security Boundaries",
            "\n".join(f"- {c}" for c in self.constraints) if self.constraints else "- Adhere strictly to project architecture",
            "\n".join(f"- **FORBIDDEN**: {f}" for f in self.forbidden_items),
            "",
            "## 4. Relevant Codebase Context",
            "\n".join(files_section) if files_section else "No additional source files needed.",
            "",
            "## 5. Expected Output Format",
            self.expected_response_format,
        ]
        return "\n".join(prompt_lines)


class ManualTransportManager:
    """Manages the creation of export packages and parsing of imported responses."""

    @staticmethod
    def create_package(
        context: ProjectContextPackage,
        target_worker: str,
        instructions: str = "Please execute the following engineering task and paste the response back into ZERO.",
        expected_response_format: Optional[str] = None,
    ) -> ManualTaskPackage:
        """Builds a strictly sanitized task package for manual transmission."""
        default_format = (
            "Return a structured JSON or clean Markdown response containing:\n"
            "- SUMMARY: Concise overview of work performed\n"
            "- STATUS: SUCCESS | NEEDS_CORRECTION | BLOCKED\n"
            "- ANALYSIS / FINDINGS: Technical breakdown\n"
            "- FILES_CREATED / FILES_MODIFIED: List of affected paths\n"
            "- DIFF: Code changes or patch\n"
            "- ACCEPTANCE_CRITERIA_RESULTS: Status of each criterion"
        )

        return ManualTaskPackage(
            package_id=f"pkg_{uuid.uuid4().hex[:10]}",
            task_id=context.task_id,
            project_id=context.project_id,
            project_name=context.project_name,
            target_worker=target_worker,
            created_at=datetime.now(timezone.utc).isoformat(),
            task_title=context.task_title,
            task_description=context.task_description,
            acceptance_criteria=list(context.acceptance_criteria),
            constraints=list(context.constraints),
            relevant_files=dict(context.relevant_files),
            instructions_for_human=instructions,
            expected_response_format=expected_response_format or default_format,
        )

    @staticmethod
    def import_result(
        raw_text: str,
        task_id: str,
        worker_id: str,
    ) -> WorkerResult:
        cleaned = (raw_text or "").strip()
        # 1. Detect provider / server errors
        err_signatures = (
            "internal server error", "internal service unavailable", "service unavailable",
            "502 bad gateway", "503 service", "504 gateway", "http error", "connection refused",
            "rate limit exceeded", "traceback (most recent call last)"
        )
        if any(cleaned.lower().startswith(sig) for sig in err_signatures):
            from zero_core.observability import DEFAULT_LOGGER
            DEFAULT_LOGGER.error(
                event_type="worker_response_parse_failed",
                message=f"Worker {worker_id} response was a provider error: {cleaned[:100]}",
                worker_id=worker_id,
                stage="Response Parsing",
                error_category="WORKER_EXECUTION_FAILED",
                expected="WorkerResult JSON",
                received=cleaned[:100],
            )
            return WorkerResult(
                task_id=task_id,
                worker_id=worker_id,
                status="FAILED",
                summary=f"Worker {worker_id} failed: Provider returned error response ({cleaned[:60]})",
                analysis=cleaned,
                errors=[f"Provider error: {cleaned[:200]}"],
                requires_human=True,
                recommended_next_action="Fallback to native capable worker or retry via manual transport",
                execution_metadata={
                    "transport": "MANUAL_TRANSPORT",
                    "stage": "Response Parsing",
                    "error_category": "WORKER_RESPONSE_PARSE_FAILED",
                    "expected": "WorkerResult JSON",
                    "received": cleaned[:100],
                    "imported_at": datetime.now(timezone.utc).isoformat(),
                },
            )

        # Check if user pasted JSON
        parsed_json: Optional[Dict[str, Any]] = None
        json_match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
        if json_match:
            try:
                parsed_json = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        if parsed_json and isinstance(parsed_json, dict):
            status = str(parsed_json.get("status", "SUCCESS")).upper()
            summary = parsed_json.get("summary", "Imported manual external worker response.")
            analysis = parsed_json.get("analysis", "") or parsed_json.get("findings", "") or cleaned
            files_created = parsed_json.get("files_created", [])
            files_modified = parsed_json.get("files_modified", [])
            diff = parsed_json.get("diff", "")
            ac_results = parsed_json.get("acceptance_criteria_results", {})
            decisions = parsed_json.get("decisions", [])
            next_action = parsed_json.get("recommended_next_action", "Proceed to ZERO validation")

            return WorkerResult(
                task_id=task_id,
                worker_id=worker_id,
                status=status if status in ("SUCCESS", "FAILED", "BLOCKED", "NEEDS_REVIEW") else "SUCCESS",
                summary=summary,
                analysis=str(analysis),
                files_created=list(files_created),
                files_modified=list(files_modified),
                diff=diff,
                decisions=decisions,
                acceptance_criteria_results=ac_results,
                recommended_next_action=next_action,
                execution_metadata={"transport": "MANUAL_TRANSPORT", "imported_at": datetime.now(timezone.utc).isoformat()},
            )

        # Fallback: Parse Markdown text
        summary = "Imported manual external worker response"
        for line in cleaned.splitlines():
            line_str = line.strip()
            if line_str.startswith("#") or "summary" in line_str.lower():
                summary = line_str.lstrip("#").strip()
                break

        return WorkerResult(
            task_id=task_id,
            worker_id=worker_id,
            status="SUCCESS",
            summary=summary,
            analysis=cleaned,
            files_created=[],
            files_modified=[],
            diff="",
            acceptance_criteria_results={},
            recommended_next_action="Review manual response and validate against acceptance criteria",
            execution_metadata={"transport": "MANUAL_TRANSPORT", "imported_at": datetime.now(timezone.utc).isoformat()},
        )
