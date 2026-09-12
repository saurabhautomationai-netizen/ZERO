"""Project Resolver & Structured Engineering Request Engine for ZERO.

Enforces:
  EXPLICIT IDENTITY PRECEDENCE + FAIL-CLOSED AMBIGUITY DETECTION +
  CANONICAL PATH NORMALIZATION + REPOSITORY BOUNDARY INTEGRITY

This module replaces all brittle keyword-based project selection with a
deterministic 8-tier resolution precedence engine and structured EngineeringRequest.
"""

from __future__ import annotations

import enum
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from zero_core.engineering.manifest import ProjectManifest
from zero_core.engineering.store import DEFAULT_PROJECT_STORE, EngineeringProjectStore

logger = logging.getLogger("zero.engineering.resolver")


class ResolutionStatus(str, enum.Enum):
    RESOLVED = "RESOLVED"
    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
    PROJECT_AMBIGUOUS = "PROJECT_AMBIGUOUS"
    BOUNDARY_VIOLATION = "BOUNDARY_VIOLATION"


class ResolutionError(Exception):
    """Raised when project resolution fails closed or detects boundary violations."""

    def __init__(
        self,
        status: ResolutionStatus,
        message: str,
        query: str = "",
        candidates: Optional[List[str]] = None,
    ):
        super().__init__(message)
        self.status = status
        self.message = message
        self.query = query
        self.candidates = candidates or []


class EngineeringIntent(str, enum.Enum):
    """Explicit operational intent for Loop Engineering instructions."""
    DISCOVERY = "DISCOVERY"
    DEEP_DISCOVERY = "DEEP_DISCOVERY"
    CONTINUATION_PLAN = "CONTINUATION_PLAN"
    DIAGNOSTIC = "DIAGNOSTIC"
    STATUS = "STATUS"
    PLAN = "PLAN"
    RESUME = "RESUME"
    GATE_APPROVAL = "GATE_APPROVAL"
    TASK_EXECUTION = "TASK_EXECUTION"
    EXECUTE_MILESTONE = "EXECUTE_MILESTONE"
    POST_MILESTONE_AUDIT = "POST_MILESTONE_AUDIT"
    RECONCILE_MILESTONE_SCOPE = "RECONCILE_MILESTONE_SCOPE"
    REPLAN_MILESTONE = "REPLAN_MILESTONE"
    RESET_MILESTONE = "RESET_MILESTONE"
    AUTONOMOUS_BUILD = "AUTONOMOUS_BUILD"
    UNKNOWN = "UNKNOWN"


@dataclass
class EngineeringRequest:
    """Structured internal request representation for Loop Engineering."""
    raw_instruction: str
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    repository_path: Optional[str] = None
    intent: EngineeringIntent = EngineeringIntent.UNKNOWN
    read_only: bool = False
    requested_gate: Optional[str] = None
    target_milestone: Optional[str] = None
    target_files: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    source_interface: str = "web"
    requested_title: Optional[str] = None
    requested_sections: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


def normalize_repo_path(path_str: Union[str, Path]) -> str:
    """Safely normalizes Windows and POSIX filesystem paths for deterministic comparison.

    Normalizes drive letters, replaces backslashes with forward slashes,
    strips trailing slashes, and resolves relative components without weakening boundaries.
    """
    if not path_str:
        return ""
    p_str = str(path_str).strip().strip("'\"")
    # Normalize slashes first
    p_str = p_str.replace("\\", "/")
    
    # Lowercase drive letter if present (e.g., F:/ -> f:/)
    if len(p_str) >= 2 and p_str[1] == ":":
        p_str = p_str[0].lower() + p_str[1:]
        
    # Remove redundant slashes and trailing slashes
    norm = os.path.normpath(p_str).replace("\\", "/")
    if len(norm) >= 2 and norm[1] == ":":
        norm = norm[0].lower() + norm[1:]
    return norm.rstrip("/")


# Canonical project alias mapping (both directions supported)
CANONICAL_PROJECT_ALIASES: Dict[str, str] = {
    # alias / short slug -> canonical project_id
    "finance_tracker": "proj_personal_finance_tracker",
    "personal_finance_tracker": "proj_personal_finance_tracker",
    "smart_finance_ai_tracker": "proj_personal_finance_tracker",
    "smart_finance": "proj_personal_finance_tracker",
    "pft": "proj_personal_finance_tracker",
    "trading_bot": "proj_trading_dashboard",
    "trading_dashboard": "proj_trading_dashboard",
    "hr_recruitment": "proj_hr_recruitment_ai_assistant",
    "hr_recruitment_assistant": "proj_hr_recruitment_ai_assistant",
    "hr_recruitment_ai_assistant": "proj_hr_recruitment_ai_assistant",
    "talent_lead_gen_agent": "proj_talent_lead_gen_agent",
    "talent_lead_gen": "proj_talent_lead_gen_agent",
    "zero_project": "proj_execute_an_autonomous_full",
    "zero_core": "proj_execute_an_autonomous_full",
}


class ProjectResolver:
    """Deterministic Multi-Project Resolution Engine.

    Enforces 8-tier precedence hierarchy:
      1. Explicit project_id in request or header
      2. Exact normalized repository path
      3. Exact registered project name (case-insensitive)
      4. Exact registered project alias
      5. Structured project metadata
      6. Active session project ONLY when no explicit project supplied
      7. Fuzzy/token resolution with ambiguity detection
      8. Clarification / fail closed (PROJECT_NOT_FOUND or PROJECT_AMBIGUOUS)
    """

    def __init__(self, store: Optional[EngineeringProjectStore] = None):
        self.store = store or DEFAULT_PROJECT_STORE

    def parse_request(
        self,
        raw_instruction: str,
        explicit_project_id: Optional[str] = None,
        explicit_repo_path: Optional[str] = None,
        session_project_id: Optional[str] = None,
        source_interface: str = "web",
    ) -> EngineeringRequest:
        """Parses a natural-language or structured task into a validated EngineeringRequest."""
        text = raw_instruction.strip()
        
        # Strip leading @mention if present
        cleaned_text = text
        if cleaned_text.startswith("@"):
            if "\n" in cleaned_text:
                cleaned_text = cleaned_text.split("\n", 1)[1].strip()
            elif ":" in cleaned_text:
                cleaned_text = cleaned_text.split(":", 1)[1].strip()
            else:
                parts = cleaned_text.split(None, 3)
                if len(parts) > 1:
                    cleaned_text = parts[-1]

        # 1. Check for explicit structured headers in prompt:
        # e.g., "Project ID: proj_personal_finance_tracker" or "project_id: foo"
        extracted_pid = explicit_project_id
        if not extracted_pid:
            pid_match = re.search(r'(?im)^(?:\s*-\s*)?(?:project[_\s]id|proj_id|project_slug)\s*[:=]\s*([a-zA-Z0-9_\-]+)', text)
            if pid_match:
                extracted_pid = pid_match.group(1).strip()

        # 2. Check for explicit repository path in prompt:
        # e.g., "Repository: F:\AI Automation\..." or "- Repository Path: `F:\...`"
        extracted_repo = explicit_repo_path
        if not extracted_repo:
            repo_match = re.search(r'(?im)^(?:\s*-\s*)?(?:repository(?:\s*path)?|repo_path|repo|path|location)\s*[:=]\s*([^\r\n]+)', text)
            if repo_match:
                extracted_repo = repo_match.group(1).strip().strip("'\"`")

        # 3. Check for explicit project name in prompt:
        # e.g., "Project: Personal Finance Tracker"
        extracted_pname = None
        pname_match = re.search(r'(?im)^(?:\s*-\s*)?(?:project[_\s]name|project)\s*[:=]\s*([^\r\n]+)', text)
        if pname_match:
            cand = pname_match.group(1).strip().strip("'\"`")
            if not cand.lower().startswith(("id:", "path:", "location:")):
                extracted_pname = cand

        # 4. Extract output contract requirements (if any)
        requested_title = None
        title_match = re.search(r'(?im)(?:return|generate|produce)\s*:\s*\n+[#\s]*([^\n\r]+)', text)
        if title_match:
            cand_title = title_match.group(1).strip().lstrip("# ")
            if len(cand_title) >= 6 and not any(k in cand_title.lower() for k in ("with a", "detailed", "analysis", "covering", "sections")):
                requested_title = cand_title
        if not requested_title:
            # Check for top-level markdown heading
            top_h_match = re.search(r'(?im)^#\s+([^\n\r]+)', text)
            if top_h_match:
                cand_h = top_h_match.group(1).strip()
                if len(cand_h) >= 5 and "—" in cand_h or "-" in cand_h or "PREFLIGHT" in cand_h.upper() or "PLAN" in cand_h.upper():
                    requested_title = cand_h

        requested_sections: List[str] = []
        # Find explicit output contract block (e.g. under Return:, Output:, Required Sections:, or Sections:)
        contract_block = None
        block_match = re.search(r'(?im)(?:return|output|required sections|sections to include|analysis covering)\s*:\s*\n+([\s\S]+?)(?=(?:\n\s*(?:then|do not|important|stop|===|---))|\Z)', text)
        if block_match:
            contract_block = block_match.group(1)
        else:
            # Fallback: Check if there is a block under a markdown title '# ... — ...' containing a numbered list
            header_block_match = re.search(r'(?im)^#\s+[^\n]+(?:—|-)[^\n]+\n+([\s\S]+?)(?=(?:\n\s*(?:then|do not|important|stop|===|---))|\Z)', text)
            if header_block_match:
                contract_block = header_block_match.group(1)

        if contract_block:
            raw_items = []
            for line in contract_block.splitlines():
                sline = line.strip()
                if not sline or sline.startswith('#'):
                    continue
                num_match = re.match(r'^\s*\d+[\.\)]\s+(.+)$', sline)
                if num_match:
                    item = num_match.group(1).strip()
                    header_prefixes = ("repository:", "project id:", "location:", "path:")
                    if not any(item.lower().startswith(p) for p in header_prefixes):
                        raw_items.append(item)
                elif sline.startswith(('-', '*', '•')) and len(sline) > 2:
                    item = sline.lstrip('-*• ').strip()
                    header_prefixes = ("repository:", "project id:", "location:", "path:", "action:", "git state:", "safety constraint:", "checkpoint directive:")
                    if not any(item.lower().startswith(p) for p in header_prefixes):
                        raw_items.append(item)
            if len(raw_items) >= 2:
                requested_sections = raw_items

        # Target Milestone extraction (Must NOT extract words like 'discovery' from negative instructions)
        extracted_milestone = None
        m_canonical = re.search(r'(?im)\b(M\d+(?:_[A-Za-z0-9_\-]+)?)\b', text)
        if m_canonical:
            extracted_milestone = m_canonical.group(1).strip()
        else:
            m_milestone = re.search(r'(?im)(?:execute|run|implement|reconcile(?:\s+scope)?|audit|reset(?:\s+phantom)?|replan)\s+milestone\s+([a-zA-Z0-9_\-]+)', text)
            if m_milestone:
                cand_ms = m_milestone.group(1).strip()
                if cand_ms.lower() not in ("discovery", "task", "project", "audit", "preflight", "all", "scope"):
                    extracted_milestone = cand_ms

        # 5. Determine intent
        intent, read_only, requested_gate = self.classify_intent(text)

        return EngineeringRequest(
            raw_instruction=text,
            project_id=extracted_pid,
            project_name=extracted_pname,
            repository_path=extracted_repo,
            intent=intent,
            read_only=read_only,
            requested_gate=requested_gate,
            target_milestone=extracted_milestone,
            source_interface=source_interface,
            requested_title=requested_title,
            requested_sections=requested_sections,
            metadata={"session_project_id": session_project_id} if session_project_id else {},
        )

    def classify_intent(self, text: str) -> Tuple[EngineeringIntent, bool, Optional[str]]:
        """Classifies engineering intent and read-only requirements from task text."""
        # Clean negative directives like "do not run discovery" so they do not trigger unintended discovery intents
        cleaned_text = re.sub(r'(?im)\b(?:do\s+not|dont|never)\s+(?:run|execute|perform|do)?\s+discovery\b', '', text)
        t_lower = cleaned_text.lower()
        t_raw_lower = text.lower()

        # Milestone Reset Intent (Human-Authorized Reset of Phantom Milestone)
        # Note: Must NOT trigger on generic words like "reset project" or "reset the project"
        if not re.search(r'(?im)\breset\s+(?:the\s+)?project\b', t_lower) and (
            re.search(r'(?im)\breset\s+(?:phantom\s+)?(?:milestone\s+)?m\d+[a-zA-Z0-9_\-]*\b', t_lower)
            or any(w in t_lower for w in ("reset milestone", "reset phantom milestone"))
        ):
            return EngineeringIntent.RESET_MILESTONE, False, None

        # Scope Reconciliation Intent (Repository-backed comparison of planned tasks vs codebase reality)
        if any(w in t_lower for w in (
            "scope reconciliation", "reconcile scope", "reconcile milestone scope",
            "repository-backed reconciliation", "repository-backed scope reconciliation",
            "reconcile planned scope", "scope reconcile", "reconcile m2 scope", "reconcile m1 scope",
            "scope reconciliation and final execution plan", "scope reconciliation and execution plan",
            "scope reconciliation and replan", "scope reconciliation and replanning",
            "reconcile and replan"
        )) or (
            ("reconcile" in t_lower or "reconciliation" in t_lower)
            and ("scope" in t_lower or "final execution plan" in t_lower or "replan" in t_lower)
        ):
            return EngineeringIntent.RECONCILE_MILESTONE_SCOPE, True, None

        # Replan Milestone Intent (Generate corrected prescriptive plan based on repository reality)
        if any(w in t_lower for w in (
            "replan milestone", "milestone replan", "replan m2", "replan m1",
            "replan execution plan", "final execution plan", "replan"
        )):
            return EngineeringIntent.REPLAN_MILESTONE, True, None

        # Post-Milestone Forensic Audit & Execution Reconciliation (Verification of claimed past completions)
        if any(w in t_lower for w in (
            "reconcile milestone", "reconcile m", "audit milestone",
            "post-milestone audit", "post milestone audit", "milestone forensic audit",
            "forensic audit of milestone", "audit phantom", "reconciliation"
        )):
            return EngineeringIntent.POST_MILESTONE_AUDIT, True, None

        # Milestone execution intent (explicit execution of a milestone)
        if any(w in t_lower for w in (
            "execute milestone", "run milestone", "implement milestone"
        )):
            return EngineeringIntent.EXECUTE_MILESTONE, False, None

        # Gate approval intent
        for gate_key, gate_name in [
            ("scope", "GATE_1_FEATURE_SCOPE"),
            ("feature", "GATE_1_FEATURE_SCOPE"),
            ("ui", "GATE_2_UIUX"),
            ("design", "GATE_2_UIUX"),
            ("security", "GATE_3_SECURITY"),
            ("deploy", "GATE_4_DEPLOYMENT"),
        ]:
            if f"approve {gate_key}" in t_lower:
                return EngineeringIntent.GATE_APPROVAL, False, gate_name

        # Continuation Plan / Preflight intent (Engineering reasoning, master planning, architecture synthesis, preflights)
        if any(w in t_lower for w in (
            "continuation plan", "continuation master plan", "create a continuation plan",
            "verified continuation master plan", "target architecture", "continuation roadmap",
            "preflight", "execution preflight", "m2 preflight", "pre-flight"
        )):
            return EngineeringIntent.CONTINUATION_PLAN, True, None

        # Deep Discovery intent (Comprehensive read-only reverse engineering, audit, and feature verification)
        if any(w in t_lower for w in (
            "deep discovery", "audit", "audit this existing", "audit existing",
            "recover the real", "recover and verify", "verify the real", "verify what is actually built",
            "verify what is built", "verified feature scope", "reverse engineer", "reverse engineering",
            "compare planned", "compare planned features", "inspect the entire existing project",
            "feature recovery", "existing project discovery", "existing project audit",
            "continuation gate", "product state recovery", "real existing", "real implementation state",
            "actual implemented features", "deep project discovery"
        )):
            return EngineeringIntent.DEEP_DISCOVERY, True, None

        # Diagnostic intent (System crashes, errors, tracebacks, runtime bugs in ZERO itself)
        if any(w in t_lower for w in (
            "diagnose", "diagnosis", "why did zero", "why is", "root-cause",
            "root cause", "bug report", "troubleshoot", "debug", "traceback", "exception"
        )):
            return EngineeringIntent.DIAGNOSTIC, True, None

        # Lightweight discovery / state recovery
        if any(w in t_lower for w in (
            "read-only discovery", "read only discovery",
            "recover project state", "stop at continuation hitl gate",
            "continuation hitl gate", "perform read-only discovery",
            "perform read only discovery", "discovery mode",
            "discovery", "inspect project", "inspect the existing"
        )):
            return EngineeringIntent.DISCOVERY, True, None

        # Status intent
        if any(w in t_lower for w in (
            "status of", "where are we with", "progress on", "show status",
            "summary of", "how is the", "get status", "current status",
            "give me the current status", "give me status", "check status",
            "status.", "status\n", "whats the status", "what's the status"
        )) or t_lower.strip().endswith("status"):
            return EngineeringIntent.STATUS, True, None

        # Plan intent
        if any(w in t_lower for w in (
            "plan", "task plan", "create plan", "generate roadmap", "break down"
        )):
            return EngineeringIntent.PLAN, True, None

        # Resume intent
        if any(w in t_lower for w in (
            "resume", "continue development", "continue project", "resume project",
            "continue the", "resume the"
        )):
            return EngineeringIntent.RESUME, False, None

        # Autonomous build intent (requires clear imperative trigger)
        if any(w in t_lower for w in (
            "execute autonomous build", "build autonomous", "execute an autonomous",
            "build me a complete", "create a completely new"
        )):
            return EngineeringIntent.AUTONOMOUS_BUILD, False, None

        # Task execution intent
        if any(w in t_lower for w in (
            "execute task", "run task", "implement task", "fix bug"
        )):
            return EngineeringIntent.TASK_EXECUTION, False, None

        return EngineeringIntent.UNKNOWN, False, None

    def resolve_project(
        self,
        request: EngineeringRequest,
        session_project_id: Optional[str] = None,
    ) -> ProjectManifest:
        """Resolves a ProjectManifest matching the EngineeringRequest using strict 8-tier precedence."""
        self.store.reload()
        all_projects = self.store.list_projects()

        # =========================================================================
        # TIER 1: Explicit project_id (ALWAYS WINS)
        # =========================================================================
        if request.project_id:
            pid = request.project_id.strip()
            # Direct match
            manifest = self.store.get_project(pid)
            if manifest:
                logger.info("Tier 1: Resolved via exact project_id: %s", manifest.project_id)
                return manifest

            # Check alias map
            canonical_id = CANONICAL_PROJECT_ALIASES.get(pid.lower())
            if canonical_id:
                manifest = self.store.get_project(canonical_id)
                if manifest:
                    logger.info("Tier 1: Resolved via aliased project_id: %s -> %s", pid, manifest.project_id)
                    return manifest

            # FAIL CLOSED: Explicit ID was supplied but does not exist
            avail_ids = [p.project_id for p in all_projects]
            raise ResolutionError(
                status=ResolutionStatus.PROJECT_NOT_FOUND,
                message=f"Project with explicit ID '{pid}' not found. Available projects: {', '.join(avail_ids)}",
                query=pid,
                candidates=avail_ids,
            )

        # =========================================================================
        # TIER 2: Exact normalized repository path
        # =========================================================================
        if request.repository_path:
            norm_target = normalize_repo_path(request.repository_path)
            for p in all_projects:
                if normalize_repo_path(p.repository_path) == norm_target:
                    logger.info("Tier 2: Resolved via exact repository path: %s -> %s", norm_target, p.project_id)
                    return p

            # Also check if target path is a direct parent or child of an existing project repo
            matching_paths = []
            for p in all_projects:
                p_norm = normalize_repo_path(p.repository_path)
                if p_norm and (norm_target.startswith(p_norm) or p_norm.startswith(norm_target)):
                    matching_paths.append(p)
            if len(matching_paths) == 1:
                return matching_paths[0]

            avail_repos = [p.repository_path for p in all_projects]
            raise ResolutionError(
                status=ResolutionStatus.PROJECT_NOT_FOUND,
                message=f"No registered project found with repository path '{request.repository_path}'.",
                query=request.repository_path,
                candidates=avail_repos,
            )

        # =========================================================================
        # TIER 3: Exact registered project_name (case-insensitive)
        # =========================================================================
        if request.project_name:
            pname_clean = request.project_name.lower().strip()
            for p in all_projects:
                if p.project_name.lower() == pname_clean:
                    logger.info("Tier 3: Resolved via exact project_name: %s -> %s", pname_clean, p.project_id)
                    return p

        # =========================================================================
        # TIER 4: Exact registered alias
        # =========================================================================
        # Check if the instruction or project_name matches a registered alias key
        candidate_words = set(re.findall(r'[a-zA-Z0-9_\-]+', request.raw_instruction.lower()))
        alias_matches = []
        for alias_key, canon_id in CANONICAL_PROJECT_ALIASES.items():
            if alias_key in candidate_words:
                p = self.store.get_project(canon_id)
                if p and p not in alias_matches:
                    alias_matches.append(p)

        if len(alias_matches) == 1:
            logger.info("Tier 4: Resolved via exact alias: %s", alias_matches[0].project_id)
            return alias_matches[0]
        elif len(alias_matches) > 1:
            # Ambiguity detected among multiple aliases
            raise ResolutionError(
                status=ResolutionStatus.PROJECT_AMBIGUOUS,
                message=f"Instruction contains multiple conflicting project aliases: {[p.project_name for p in alias_matches]}.",
                query=request.raw_instruction,
                candidates=[p.project_id for p in alias_matches],
            )

        # =========================================================================
        # RESET_MILESTONE Invariant: Explicit project identity is MANDATORY
        # Do NOT fall back to active session project or fuzzy guessing
        # =========================================================================
        if request.intent == EngineeringIntent.RESET_MILESTONE:
            avail_ids = [p.project_id for p in all_projects]
            if len(all_projects) > 1:
                raise ResolutionError(
                    status=ResolutionStatus.PROJECT_AMBIGUOUS,
                    message=f"Milestone reset requires explicit project identity. Multiple projects exist: {', '.join(avail_ids)}. Please specify 'Project ID: <id>'.",
                    query=request.raw_instruction,
                    candidates=avail_ids,
                )
            elif len(all_projects) == 1:
                return all_projects[0]
            else:
                raise ResolutionError(
                    status=ResolutionStatus.PROJECT_NOT_FOUND,
                    message="No registered projects exist to reset.",
                    query=request.raw_instruction,
                )

        # =========================================================================
        # TIER 5: Structured project metadata in request envelope
        # =========================================================================
        if request.metadata and "project_id" in request.metadata:
            meta_pid = request.metadata["project_id"]
            p = self.store.get_project(meta_pid)
            if p:
                logger.info("Tier 5: Resolved via request metadata project_id: %s", p.project_id)
                return p

        # =========================================================================
        # TIER 6: Active session project (ONLY when NO explicit identity given)
        # =========================================================================
        sess_pid = session_project_id or request.metadata.get("session_project_id")
        # Ensure session project is only considered if the user prompt didn't ask for a different project
        if sess_pid:
            p = self.store.get_project(sess_pid)
            if p:
                logger.info("Tier 6: Resolved via active session: %s", p.project_id)
                return p

        # =========================================================================
        # TIER 7: Strict token / fuzzy search with ambiguity detection
        # =========================================================================
        scored_candidates = self._score_candidates(request.raw_instruction, all_projects)
        if scored_candidates:
            top_score, top_project = scored_candidates[0]
            if top_score >= 0.5:
                # Check for ambiguity with second candidate
                if len(scored_candidates) > 1:
                    second_score, second_project = scored_candidates[1]
                    if (top_score - second_score) < 0.15:
                        raise ResolutionError(
                            status=ResolutionStatus.PROJECT_AMBIGUOUS,
                            message=(
                                f"Project reference is ambiguous between '{top_project.project_name}' ({top_project.project_id}) "
                                f"and '{second_project.project_name}' ({second_project.project_id}). Please specify an explicit Project ID."
                            ),
                            query=request.raw_instruction,
                            candidates=[top_project.project_id, second_project.project_id],
                        )
                logger.info("Tier 7: Resolved via token scoring (%0.2f): %s", top_score, top_project.project_id)
                return top_project

        # =========================================================================
        # TIER 8: Fail closed
        # =========================================================================
        avail_projects = [f"{p.project_name} (`{p.project_id}`)" for p in all_projects]
        raise ResolutionError(
            status=ResolutionStatus.PROJECT_NOT_FOUND,
            message=(
                f"Could not resolve any registered project from instruction. "
                f"Available registered projects: {', '.join(avail_projects)}."
            ),
            query=request.raw_instruction,
            candidates=[p.project_id for p in all_projects],
        )

    def _score_candidates(
        self,
        query: str,
        projects: List[ProjectManifest],
    ) -> List[Tuple[float, ProjectManifest]]:
        """Calculates token overlap and similarity scores without reverse substring bias."""
        noise_words = {
            "the", "project", "assistant", "a", "an", "for", "with", "status",
            "of", "in", "to", "my", "existing", "development", "please", "can",
            "you", "zero", "agent", "loop", "engineering", "show", "get", "check"
        }
        q_tokens = {
            w for w in re.findall(r'[a-zA-Z0-9]+', query.lower())
            if len(w) > 1 and w not in noise_words
        }
        if not q_tokens:
            return []

        scored: List[Tuple[float, ProjectManifest]] = []
        for p in projects:
            p_tokens = {
                w for w in re.findall(r'[a-zA-Z0-9]+', p.project_name.lower())
                if len(w) > 1 and w not in noise_words
            }
            if not p_tokens:
                continue

            intersection = q_tokens & p_tokens
            if not intersection:
                continue

            # Jaccard index over project tokens
            score = len(intersection) / len(p_tokens)
            scored.append((score, p))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    def verify_mutation_boundary(
        self,
        manifest: ProjectManifest,
        target_path: Optional[Union[str, Path]] = None,
        checkpoint_project_id: Optional[str] = None,
    ) -> None:
        """Enforces the pre-mutation invariant across resolver, manifest, checkpoint, and repository guards.

        Invariant:
          resolved_manifest.project_id == checkpoint.project_id
          target_path must reside within canonical manifest.repository_path
        """
        if checkpoint_project_id and checkpoint_project_id != manifest.project_id:
            raise ResolutionError(
                status=ResolutionStatus.BOUNDARY_VIOLATION,
                message=(
                    f"PROJECT_BOUNDARY_VIOLATION: Checkpoint project ID '{checkpoint_project_id}' "
                    f"does not match resolved project ID '{manifest.project_id}'."
                ),
            )

        if target_path:
            norm_target = normalize_repo_path(target_path)
            norm_manifest_repo = normalize_repo_path(manifest.repository_path)
            if not norm_target.startswith(norm_manifest_repo):
                raise ResolutionError(
                    status=ResolutionStatus.BOUNDARY_VIOLATION,
                    message=(
                        f"PROJECT_BOUNDARY_VIOLATION: Target mutation path '{target_path}' "
                        f"is outside resolved repository boundary '{manifest.repository_path}'."
                    ),
                )


DEFAULT_PROJECT_RESOLVER = ProjectResolver()
