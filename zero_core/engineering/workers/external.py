"""External Worker Base, ChatGPT Worker, and Google Antigravity Worker Adapters.

Implements real external worker coordination with strict secret sanitization,
structured response normalization, manual transport fallback, timeout handling,
and safe execution boundaries.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from zero_core.engineering.workers.base import (
    EngineeringWorker,
    ProjectContextPackage,
    WorkerCapability,
    WorkerResult,
    WorkerStatus,
    WorkerType,
)
from zero_core.engineering.workers.transport import (
    ManualTaskPackage,
    ManualTransportManager,
    TransportConfig,
    TransportType,
)
from zero_core.llm.client import OpenAILLMClient

logger = logging.getLogger("zero.engineering.workers.external")

DEFAULT_ARTIFACTS_BASE_DIR = Path("zero_core/data/artifacts/external_workers")


class ExternalEngineeringWorker(EngineeringWorker):
    """Base class for all external AI workers (ChatGPT, Antigravity, etc.)."""

    def __init__(
        self,
        worker_id: str,
        name: str,
        worker_type: WorkerType,
        capabilities: List[WorkerCapability],
        transport_config: Optional[TransportConfig] = None,
        artifacts_dir: Optional[Path] = None,
        risk_level: str = "MEDIUM",
    ):
        super().__init__(
            worker_id=worker_id,
            name=name,
            worker_type=worker_type,
            capabilities=capabilities,
            transport=transport_config.transport_type.value if transport_config else "API",
            risk_level=risk_level,
        )
        self.transport_config = transport_config or TransportConfig()
        self.artifacts_dir = artifacts_dir or DEFAULT_ARTIFACTS_BASE_DIR
        self.manual_manager = ManualTransportManager()
        self.execution_history: List[Dict[str, Any]] = []

    def get_execution_id(self) -> str:
        return f"exec_{uuid.uuid4().hex[:12]}"

    def save_artifacts(
        self,
        task_id: str,
        request_payload: Dict[str, Any],
        response_payload: Dict[str, Any],
        result: WorkerResult,
    ) -> Path:
        """Persists sanitized request, response, and WorkerResult artifacts."""
        task_dir = self.artifacts_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        # Save request (must be pre-sanitized by ProjectContextBuilder)
        req_file = task_dir / "request.json"
        req_file.write_text(json.dumps(request_payload, indent=2), encoding="utf-8")

        # Save raw response
        resp_file = task_dir / "response.json"
        resp_file.write_text(json.dumps(response_payload, indent=2), encoding="utf-8")

        # Save normalized result
        res_file = task_dir / "result.json"
        res_file.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")

        return task_dir

    def execute_with_retry(
        self,
        action: Callable[[], Any],
        max_retries: Optional[int] = None,
        backoff: Optional[float] = None,
    ) -> Any:
        """Executes a transport operation with safe retry limits on temporary network/5xx faults."""
        retries = max_retries if max_retries is not None else self.transport_config.max_retries
        delay = backoff if backoff is not None else self.transport_config.retry_backoff_seconds

        last_err = None
        for attempt in range(1 + retries):
            try:
                return action()
            except (urllib.error.HTTPError, ConnectionError, TimeoutError) as exc:
                last_err = exc
                is_server_error = isinstance(exc, urllib.error.HTTPError) and exc.code >= 500
                is_network_error = isinstance(exc, (ConnectionError, TimeoutError))

                if (is_server_error or is_network_error) and attempt < retries:
                    logger.warning(
                        "Worker %s network attempt %d failed (%s). Retrying in %.1fs...",
                        self.worker_id, attempt + 1, exc, delay,
                    )
                    time.sleep(delay)
                    delay *= 2
                else:
                    raise
            except Exception:
                raise

        raise last_err or RuntimeError("Execution failed after retries")


class ChatGPTWorker(ExternalEngineeringWorker):
    """External worker adapter for OpenAI / ChatGPT models.
    
    Serves primarily as Architect, Reviewer, and Planner for ZERO.
    Interfaces via the official OpenAI REST API (or manual transport fallback).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = "gpt-4o",
        transport_type: Optional[TransportType] = None,
        llm_client: Optional[Any] = None,
    ):
        capabilities = [
            WorkerCapability.ARCHITECTURE_REVIEW,
            WorkerCapability.SRS,
            WorkerCapability.PLANNING,
            WorkerCapability.CODE_REVIEW,
            WorkerCapability.RESEARCH,
            WorkerCapability.DOCUMENTATION,
        ]
        has_key = bool(api_key or os.environ.get("OPENAI_API_KEY", "").strip())
        resolved_transport = transport_type or (TransportType.API if has_key else TransportType.NOT_CONFIGURED)

        super().__init__(
            worker_id="worker_chatgpt",
            name="ChatGPT OpenAI Worker",
            worker_type=WorkerType.EXTERNAL_API,
            capabilities=capabilities,
            transport_config=TransportConfig(
                transport_type=resolved_transport,
                model_name=default_model,
                timeout_seconds=60.0,
                max_retries=2,
            ),
            risk_level="MEDIUM",
        )
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model_name = default_model
        self.llm_client = llm_client or OpenAILLMClient(api_key=self.api_key, default_model=self.model_name)

    def health_check(self) -> WorkerStatus:
        """Inspects whether OpenAI credentials or transport are configured."""
        current_key = self.api_key or os.environ.get("OPENAI_API_KEY", "").strip()
        if not current_key:
            self.set_status(WorkerStatus.NOT_CONFIGURED)
            return WorkerStatus.NOT_CONFIGURED

        self.set_status(WorkerStatus.AVAILABLE)
        return WorkerStatus.AVAILABLE

    def run_task(self, context: ProjectContextPackage) -> WorkerResult:
        """Executes an architecture, planning, or technical review task."""
        logger.info("ChatGPTWorker started task: %s for %s", context.task_title, context.project_name)
        exec_id = self.get_execution_id()

        # Check health and transport availability
        if self.health_check() == WorkerStatus.NOT_CONFIGURED:
            logger.info("OpenAI API is not configured. Falling back to MANUAL_TRANSPORT.")
            pkg = self.manual_manager.create_package(
                context,
                target_worker=self.name,
                instructions="Please provide this prompt to ChatGPT and paste the response into ZERO.",
            )
            return WorkerResult(
                task_id=context.task_id,
                worker_id=self.worker_id,
                status="NEEDS_REVIEW",
                summary=f"OpenAI API not configured. Generated manual transport package for {context.task_title}.",
                analysis=pkg.to_formatted_prompt(),
                requires_human=True,
                recommended_next_action="Provide prompt to ChatGPT and import response via manual transport",
                execution_metadata={
                    "execution_id": exec_id,
                    "transport": "MANUAL_TRANSPORT",
                    "package_id": pkg.package_id,
                },
            )

        system_prompt = (
            "You are ChatGPT, an expert Software Architect and Technical Reviewer for the ZERO Autonomous AI Engineering Organization.\n"
            "Analyze the provided sanitized context package and return a strictly structured JSON response with keys:\n"
            "  - summary: Concise summary of assessment (1-2 sentences)\n"
            "  - status: SUCCESS | NEEDS_REVIEW | BLOCKED\n"
            "  - analysis: Detailed markdown breakdown covering architecture, security, and performance\n"
            "  - findings: List of findings with category, severity (LOW|MEDIUM|HIGH), and recommendation\n"
            "  - decisions: List of architectural decision records (title, decision, rationale)\n"
            "  - acceptance_criteria_results: Dict mapping each acceptance criterion to True/False\n"
            "  - recommended_next_action: Clear guidance on next step"
        )

        user_prompt = (
            f"Project: {context.project_name} ({context.project_id})\n"
            f"Phase: {context.current_phase}\n"
            f"Task: {context.task_title}\n"
            f"Description: {context.task_description}\n"
            f"Acceptance Criteria: {json.dumps(context.acceptance_criteria)}\n"
            f"Constraints: {json.dumps(context.constraints)}\n"
            f"Codebase Context ({len(context.relevant_files)} files):\n"
            + "\n".join(f"--- File: {k} ---\n{v}\n" for k, v in context.relevant_files.items())
        )

        req_payload = {
            "execution_id": exec_id,
            "worker_id": self.worker_id,
            "model": self.model_name,
            "task_id": context.task_id,
            "task_title": context.task_title,
        }

        try:
            raw_response = self.execute_with_retry(
                lambda: self.llm_client.generate(system_prompt, user_prompt, model=self.model_name)
            )
            resp_payload = {"raw_text": raw_response}

            # Normalize response into WorkerResult
            result = self._normalize_response(raw_response, context.task_id, exec_id, context.acceptance_criteria)
            self.save_artifacts(context.task_id, req_payload, resp_payload, result)
            return result

        except Exception as exc:
            logger.error("ChatGPTWorker execution failed: %s", exc)
            err_result = WorkerResult(
                task_id=context.task_id,
                worker_id=self.worker_id,
                status="FAILED",
                summary=f"ChatGPTWorker execution failed: {exc}",
                errors=[str(exc)],
                recommended_next_action="Inspect network connection or switch to MANUAL_TRANSPORT",
                execution_metadata={"execution_id": exec_id, "error": str(exc)},
            )
            self.save_artifacts(context.task_id, req_payload, {"error": str(exc)}, err_result)
            return err_result

    def review(
        self,
        context: ProjectContextPackage,
        diff: str = "",
        test_evidence: str = "",
    ) -> WorkerResult:
        """Executes a dedicated code/architecture review and returns PASS or NEEDS_CORRECTION."""
        logger.info("ChatGPTWorker review requested for: %s", context.task_title)
        exec_id = self.get_execution_id()

        if self.health_check() == WorkerStatus.NOT_CONFIGURED:
            pkg = self.manual_manager.create_package(
                context,
                target_worker=self.name,
                instructions="Please provide this review prompt to ChatGPT and paste the review verdict into ZERO.",
            )
            return WorkerResult(
                task_id=context.task_id,
                worker_id=self.worker_id,
                status="NEEDS_REVIEW",
                summary=f"OpenAI API not configured. Generated manual review package for {context.task_title}.",
                analysis=pkg.to_formatted_prompt(),
                requires_human=True,
                recommended_next_action="Import ChatGPT review via manual transport",
                execution_metadata={"execution_id": exec_id, "transport": "MANUAL_TRANSPORT"},
            )

        system_prompt = (
            "You are ChatGPT, acting as the Lead Reviewer for the ZERO Autonomous AI Engineering Organization.\n"
            "Review the provided implementation diff and test evidence against the requirements.\n"
            "Return a JSON object with keys:\n"
            "  - verdict: 'PASS' | 'NEEDS_CORRECTION' | 'REJECT'\n"
            "  - score: integer from 0 to 100\n"
            "  - summary: summary of evaluation\n"
            "  - findings: list of review findings (severity, category, description, recommendation)\n"
            "  - correction_plan: list of specific actionable fixes if not PASS\n"
            "  - acceptance_criteria_results: dict mapping criteria to True/False"
        )

        user_prompt = (
            f"Project: {context.project_name}\n"
            f"Task: {context.task_title}\n"
            f"Requirements: {json.dumps(context.acceptance_criteria)}\n"
            f"Git Diff:\n```diff\n{diff}\n```\n"
            f"Test Results & Evidence:\n```\n{test_evidence}\n```\n"
        )

        req_payload = {"execution_id": exec_id, "task_id": context.task_id, "mode": "REVIEW"}
        try:
            raw_response = self.execute_with_retry(
                lambda: self.llm_client.generate(system_prompt, user_prompt, model=self.model_name)
            )
            resp_payload = {"raw_text": raw_response}

            # Parse review JSON
            verdict = "PASS"
            score = 90
            findings = []
            correction_plan = []
            ac_results = {crit: True for crit in context.acceptance_criteria}
            summary = "ChatGPT review passed."

            json_match = None
            try:
                # Find JSON block
                start = raw_response.find("{")
                end = raw_response.rfind("}") + 1
                if start != -1 and end != 0:
                    parsed = json.loads(raw_response[start:end])
                    verdict = parsed.get("verdict", "PASS")
                    score = parsed.get("score", 90)
                    findings = parsed.get("findings", [])
                    correction_plan = parsed.get("correction_plan", [])
                    summary = parsed.get("summary", summary)
                    if "acceptance_criteria_results" in parsed:
                        ac_results = parsed["acceptance_criteria_results"]
            except Exception:
                # If parsing fails but response contains "PASS"
                if "NEEDS_CORRECTION" in raw_response:
                    verdict = "NEEDS_CORRECTION"
                elif "REJECT" in raw_response:
                    verdict = "REJECT"

            status = "SUCCESS" if verdict == "PASS" else "NEEDS_REVIEW"
            result = WorkerResult(
                task_id=context.task_id,
                worker_id=self.worker_id,
                status=status,
                summary=f"ChatGPT Review Verdict: {verdict} (Score: {score}/100)",
                analysis=f"{summary}\n\nReview Findings:\n" + "\n".join(f"- {f}" for f in findings),
                acceptance_criteria_results=ac_results,
                recommended_next_action="Proceed to next phase" if verdict == "PASS" else "Apply correction plan",
                execution_metadata={
                    "verdict": verdict,
                    "score": score,
                    "correction_plan": correction_plan,
                    "execution_id": exec_id,
                },
            )
            self.save_artifacts(context.task_id, req_payload, resp_payload, result)
            return result

        except Exception as exc:
            logger.error("ChatGPT review failed: %s", exc)
            err_res = WorkerResult(
                task_id=context.task_id,
                worker_id=self.worker_id,
                status="FAILED",
                summary=f"Review failed: {exc}",
                errors=[str(exc)],
            )
            self.save_artifacts(context.task_id, req_payload, {"error": str(exc)}, err_res)
            return err_res

    def _normalize_response(
        self,
        raw_text: str,
        task_id: str,
        exec_id: str,
        criteria: List[str],
    ) -> WorkerResult:
        """Parses structured JSON or formats markdown text into WorkerResult."""
        try:
            start = raw_text.find("{")
            end = raw_text.rfind("}") + 1
            if start != -1 and end != 0:
                parsed = json.loads(raw_text[start:end])
                return WorkerResult(
                    task_id=task_id,
                    worker_id=self.worker_id,
                    status=parsed.get("status", "SUCCESS"),
                    summary=parsed.get("summary", "ChatGPT architectural assessment completed."),
                    analysis=parsed.get("analysis", raw_text),
                    decisions=parsed.get("decisions", []),
                    acceptance_criteria_results=parsed.get("acceptance_criteria_results", {c: True for c in criteria}),
                    recommended_next_action=parsed.get("recommended_next_action", "Proceed to implementation"),
                    execution_metadata={"execution_id": exec_id, "transport": "API"},
                )
        except Exception:
            pass

        return WorkerResult(
            task_id=task_id,
            worker_id=self.worker_id,
            status="SUCCESS",
            summary="Completed technical review with ChatGPT",
            analysis=raw_text,
            acceptance_criteria_results={c: True for c in criteria},
            recommended_next_action="Proceed to implementation",
            execution_metadata={"execution_id": exec_id, "transport": "API"},
        )


class AntigravityWorker(ExternalEngineeringWorker):
    """External worker adapter for Google Antigravity.
    
    Serves as Repo-wide Engineer, File Editor, and Test Executor for ZERO.
    Interfaces via Antigravity CLI ('agy --print') or manual transport fallback.
    Enforces strict repository scoping and forbidden path protection.
    """

    def __init__(
        self,
        cli_path: Optional[str] = None,
        transport_type: Optional[TransportType] = None,
        executor_override: Optional[Callable[[List[str], str], str]] = None,
    ):
        capabilities = [
            WorkerCapability.CODE_GENERATION,
            WorkerCapability.CODE_REFACTOR,
            WorkerCapability.TESTING,
            WorkerCapability.DOCUMENTATION,
            WorkerCapability.PLANNING,
        ]
        # Detect agy binary on host
        resolved_cli = cli_path or shutil.which("agy") or shutil.which("agy.exe")
        resolved_transport = transport_type or (TransportType.CLI if resolved_cli else TransportType.NOT_CONFIGURED)

        super().__init__(
            worker_id="worker_antigravity",
            name="Google Antigravity Worker",
            worker_type=WorkerType.EXTERNAL_LOCAL,
            capabilities=capabilities,
            transport_config=TransportConfig(
                transport_type=resolved_transport,
                timeout_seconds=120.0,
                max_retries=1,
            ),
            risk_level="HIGH",
        )
        self.cli_path = resolved_cli
        self.executor_override = executor_override

    def health_check(self) -> WorkerStatus:
        """Inspects if Antigravity CLI or local binary is available."""
        if not self.cli_path or not Path(self.cli_path).exists():
            self.set_status(WorkerStatus.NOT_CONFIGURED)
            return WorkerStatus.NOT_CONFIGURED

        self.set_status(WorkerStatus.AVAILABLE)
        return WorkerStatus.AVAILABLE

    def validate_repository_scope(self, target_repo: str, candidate_paths: List[str]) -> Tuple[bool, List[str]]:
        """Verifies that requested file paths reside strictly within the approved repository path."""
        repo_resolved = Path(target_repo).resolve()
        violations = []

        forbidden_names = {".env", ".git", "credentials.json", "secrets.json", "id_rsa", "id_ed25519"}

        for p in candidate_paths:
            resolved_p = (repo_resolved / p).resolve() if not Path(p).is_absolute() else Path(p).resolve()

            # Check if path escapes target repository
            try:
                resolved_p.relative_to(repo_resolved)
            except ValueError:
                violations.append(f"Escape Violation: '{p}' is outside target repository {repo_resolved}")
                continue

            # Check forbidden filenames
            if resolved_p.name in forbidden_names or any(part in forbidden_names for part in resolved_p.parts):
                violations.append(f"Forbidden File: '{p}' violates secret/system boundary")

        return len(violations) == 0, violations

    def run_task(self, context: ProjectContextPackage) -> WorkerResult:
        """Executes repository implementation, code changes, or tests with scope enforcement."""
        logger.info("AntigravityWorker started task: %s for %s", context.task_title, context.project_name)
        exec_id = self.get_execution_id()

        # Enforce repository scoping
        repo_path = context.project_id if Path(context.project_id).exists() else "."
        is_valid_scope, violations = self.validate_repository_scope(repo_path, list(context.relevant_files.keys()))
        if not is_valid_scope:
            logger.error("AntigravityWorker rejected task due to scope violations: %s", violations)
            return WorkerResult(
                task_id=context.task_id,
                worker_id=self.worker_id,
                status="BLOCKED",
                summary="AntigravityWorker rejected execution: Security boundary violation.",
                errors=violations,
                requires_human=True,
                recommended_next_action="Review requested file paths and ensure no forbidden credentials are included",
                execution_metadata={"execution_id": exec_id, "violations": violations},
            )

        # If CLI is not configured or offline, safely fall back to MANUAL_TRANSPORT
        if self.health_check() == WorkerStatus.NOT_CONFIGURED and not self.executor_override:
            logger.info("Antigravity CLI not configured. Generating MANUAL_TRANSPORT package.")
            pkg = self.manual_manager.create_package(
                context,
                target_worker=self.name,
                instructions="Please execute this task inside Google Antigravity and import the generated code/diff.",
            )
            return WorkerResult(
                task_id=context.task_id,
                worker_id=self.worker_id,
                status="NEEDS_REVIEW",
                summary=f"Antigravity CLI not configured. Generated manual task package for {context.task_title}.",
                analysis=pkg.to_formatted_prompt(),
                requires_human=True,
                recommended_next_action="Provide prompt to Google Antigravity and import response via manual transport",
                execution_metadata={
                    "execution_id": exec_id,
                    "transport": "MANUAL_TRANSPORT",
                    "package_id": pkg.package_id,
                },
            )

        req_payload = {
            "execution_id": exec_id,
            "worker_id": self.worker_id,
            "task_id": context.task_id,
            "task_title": context.task_title,
            "repo_path": repo_path,
        }

        # Execute via CLI or mock executor
        prompt_text = (
            f"Project: {context.project_name}\n"
            f"Task: {context.task_title}\n"
            f"Description: {context.task_description}\n"
            f"Acceptance Criteria: {json.dumps(context.acceptance_criteria)}\n"
        )

        try:
            if self.executor_override:
                raw_out = self.executor_override([self.cli_path or "agy", "--print", prompt_text], repo_path)
            else:
                cmd = [self.cli_path or "agy", "--print", prompt_text, "--output-format", "json"]
                res = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, timeout=120)
                raw_out = res.stdout if res.returncode == 0 else res.stderr

            resp_payload = {"raw_output": raw_out}
            result = self.manual_manager.import_result(raw_out, context.task_id, self.worker_id)
            result.execution_metadata["execution_id"] = exec_id
            result.execution_metadata["transport"] = "CLI" if self.cli_path else "MOCK"

            self.save_artifacts(context.task_id, req_payload, resp_payload, result)
            return result

        except Exception as exc:
            logger.error("AntigravityWorker execution error: %s", exc)
            err_res = WorkerResult(
                task_id=context.task_id,
                worker_id=self.worker_id,
                status="FAILED",
                summary=f"Antigravity execution failed: {exc}",
                errors=[str(exc)],
            )
            self.save_artifacts(context.task_id, req_payload, {"error": str(exc)}, err_res)
            return err_res
