"""Project Context Builder and Secret Sanitization Engine for ZERO.

Enforces:
  LEAST CONTEXT + LEAST PRIVILEGE + SECRET REDACTION + TRACEABILITY

Provides task-specific, strictly sanitized ProjectContextPackage objects
for internal and external workers (ChatGPT, Antigravity, Project Builder,
Coding Agent, UI/UX specialists, and Agency-agents).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from zero_core.engineering.manifest import ProjectManifest, TaskItem
from zero_core.engineering.workers.base import (
    EngineeringWorker,
    ProjectContextPackage,
    WorkerCapability,
    WorkerStatus,
    WorkerType,
)
from zero_core.engineering.workers.registry import WorkerSpec

logger = logging.getLogger("zero.engineering.context_builder")


class ContextSecurityError(Exception):
    """Raised when context building fails closed due to prohibited secrets or files."""
    def __init__(self, message: str, reason: str = "CONTEXT_SECURITY_REVIEW_REQUIRED"):
        super().__init__(message)
        self.reason = reason


# ---------------------------------------------------------------------------
# File Filtering Policy (Denylist & Binary Extensions)
# ---------------------------------------------------------------------------

DENIED_FILE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.test",
    "credentials.json",
    "secrets.json",
    "token.json",
    "tokens.json",
    "auth.json",
    "cookies.txt",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "id_dsa",
}

DENIED_FILE_EXTENSIONS = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".pkcs12",
    ".crt",
    ".der",
    ".kdbx",
    ".keystore",
    ".jks",
}

DENIED_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".agents",
    ".claude",
    ".gemini",
}

BINARY_FILE_EXTENSIONS = {
    ".exe", ".bin", ".dll", ".so", ".dylib",
    ".db", ".sqlite", ".sqlite3",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".svg",
    ".mp4", ".mp3", ".wav", ".avi", ".mov",
    ".zip", ".tar", ".gz", ".7z", ".rar",
    ".parquet", ".arrow", ".feather",
    ".pyc", ".pyo", ".wasm", ".pdf",
}


# ---------------------------------------------------------------------------
# Secret Sanitization Patterns
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SecretPattern:
    name: str
    pattern: re.Pattern
    replacement: str


SECRET_PATTERNS: List[SecretPattern] = [
    # 1. Private Cryptographic Keys
    SecretPattern(
        name="PRIVATE_KEY",
        pattern=re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP |ENCRYPTED )?PRIVATE KEY-----"
            r"[\s\S]*?"
            r"-----END (?:RSA |EC |OPENSSH |DSA |PGP |ENCRYPTED )?PRIVATE KEY-----",
            re.MULTILINE,
        ),
        replacement="[REDACTED_PRIVATE_KEY]",
    ),
    # 2. OpenAI API Keys (legacy sk-, new sk-proj-, sk-live-)
    SecretPattern(
        name="OPENAI_API_KEY",
        pattern=re.compile(r"\b(sk-(?:proj-|live-)?[a-zA-Z0-9_\-]{20,})\b"),
        replacement="[REDACTED_OPENAI_API_KEY]",
    ),
    # 3. Anthropic API Keys
    SecretPattern(
        name="ANTHROPIC_API_KEY",
        pattern=re.compile(r"\b(sk-ant-[a-zA-Z0-9_\-]{20,})\b"),
        replacement="[REDACTED_ANTHROPIC_API_KEY]",
    ),
    # 4. Google Gemini / Cloud API Key
    SecretPattern(
        name="GEMINI_API_KEY",
        pattern=re.compile(r"\b(AIza[0-9A-Za-z\-_]{35})\b"),
        replacement="[REDACTED_GEMINI_API_KEY]",
    ),
    # 5. GitHub Tokens (personal access tokens, oauth)
    SecretPattern(
        name="GITHUB_TOKEN",
        pattern=re.compile(r"\b(gh[pousr]_[A-Za-z0-9_]{20,})\b"),
        replacement="[REDACTED_GITHUB_TOKEN]",
    ),
    # 6. Telegram Bot Tokens (e.g. 123456789:ABCdefGhIJKlmNoPQRstuVWXyz)
    SecretPattern(
        name="TELEGRAM_TOKEN",
        pattern=re.compile(r"\b([0-9]{8,10}:[a-zA-Z0-9_\-]{20,})\b"),
        replacement="[REDACTED_TELEGRAM_TOKEN]",
    ),
    # 7. Slack & WhatsApp Access Tokens
    SecretPattern(
        name="SLACK_WHATSAPP_TOKEN",
        pattern=re.compile(r"\b(xox[baprs]-[0-9A-Za-z\-]{10,}|EAAB[0-9A-Za-z]{20,})\b"),
        replacement="[REDACTED_SERVICE_TOKEN]",
    ),
    # 8. AWS Access Key ID
    SecretPattern(
        name="AWS_ACCESS_KEY",
        pattern=re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
        replacement="[REDACTED_AWS_ACCESS_KEY]",
    ),
    # 9. AWS Secret Access Key
    SecretPattern(
        name="AWS_SECRET_KEY",
        pattern=re.compile(
            r"(?i)(aws_secret_access_key|aws_secret_key)\s*[:=]\s*['\"]?([a-zA-Z0-9/+=]{40})['\"]?"
        ),
        replacement=r"\1='[REDACTED_AWS_SECRET_KEY]'",
    ),
    # 10. Bearer / Authorization Headers
    SecretPattern(
        name="BEARER_TOKEN",
        pattern=re.compile(
            r"(?i)\b(bearer\s+)([a-zA-Z0-9\-_.~+/=]{20,})\b"
        ),
        replacement=r"\1[REDACTED_BEARER_TOKEN]",
    ),
    # 11. Database Connection URLs with passwords
    SecretPattern(
        name="DATABASE_URL",
        pattern=re.compile(
            r"(?i)\b(postgresql|postgres|mysql|mongodb(?:\+srv)?|redis|sqlite)://([^:\s]+):([^@\s]+)@([^\s/:]+)(?::\d+)?(/?[^\s\"']*)\b"
        ),
        replacement=r"\1://[REDACTED_USER]:[REDACTED_PASSWORD]@\4\5",
    ),
    # 12. Generic Key-Value secret assignments (password = "...", api_key = "...", etc.)
    SecretPattern(
        name="GENERIC_ASSIGNMENT_SECRET",
        pattern=re.compile(
            r"""(?i)\b(password|passwd|api[_-]?key|secret(?:[_-]?key)?|auth(?:[_-]?token)?|access[_-]?token|client[_-]?secret|jwt[_-]?secret|db[_-]?password|postgres[_-]?password|broker[_-]?(?:password|credentials?)|mt5[_-]?password)\s*([:=])\s*(['"])([^'"\n\r]{4,})\3"""
        ),
        replacement=r"\1 \2 \3[REDACTED_CREDENTIAL]\3",
    ),
    # 13. Supabase / JWT token payloads
    SecretPattern(
        name="JWT_SECRET",
        pattern=re.compile(r"\b(eyJh[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,})\b"),
        replacement="[REDACTED_JWT_TOKEN]",
    ),
]


class SecretSanitizer:
    """Detects and redacts sensitive credentials and tokens without losing structural context."""

    def sanitize(
        self,
        content: str,
        file_path: str = "unknown",
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Redacts all matching secrets and returns sanitized text + metadata log."""
        sanitized = content
        findings: List[Dict[str, Any]] = []

        for p in SECRET_PATTERNS:
            matches = list(p.pattern.finditer(sanitized))
            if matches:
                # Log only non-sensitive metadata (NEVER the matched secret)
                for m in matches:
                    line_num = content[:m.start()].count("\n") + 1
                    findings.append({
                        "secret_type": p.name,
                        "file_path": file_path,
                        "line_number": line_num,
                        "redaction_applied": True,
                    })
                    logger.info(
                        "Sanitized secret of type '%s' in '%s' on line %d",
                        p.name,
                        file_path,
                        line_num,
                    )
                sanitized = p.pattern.sub(p.replacement, sanitized)

        return sanitized, findings


# ---------------------------------------------------------------------------
# Context Builder Configuration
# ---------------------------------------------------------------------------

@dataclass
class ContextBuilderConfig:
    """Configurable sizing and filtering constraints for context generation."""
    max_files: int = 15
    max_file_bytes: int = 50_000           # 50 KB max per file
    max_total_context_bytes: int = 250_000 # 250 KB total text
    max_excerpt_lines: int = 200
    allow_external_exposure: bool = False
    fail_on_prohibited_secret: bool = False


# ---------------------------------------------------------------------------
# Project Context Builder
# ---------------------------------------------------------------------------

class ProjectContextBuilder:
    """Assembles task-specific, strictly sanitized ProjectContextPackage instances."""

    def __init__(self, config: Optional[ContextBuilderConfig] = None):
        self.config = config or ContextBuilderConfig()
        self.sanitizer = SecretSanitizer()

    def is_denied_file(self, path: Union[Path, str]) -> Tuple[bool, str]:
        """Evaluates whether a file is unconditionally denied from worker context."""
        p = Path(path)
        name = p.name.lower()
        ext = p.suffix.lower()

        # Denied directory ancestor
        for part in p.parent.parts:
            if part in DENIED_DIR_NAMES or (part.startswith(".") and part not in (".", "..")):
                return True, f"Denied directory: {part}"

        # Denied exact filename
        if name in DENIED_FILE_NAMES or name.startswith(".env"):
            return True, f"Denied sensitive file: {name}"

        # Denied extension
        if ext in DENIED_FILE_EXTENSIONS:
            return True, f"Denied sensitive extension: {ext}"

        # Denied binary extension
        if ext in BINARY_FILE_EXTENSIONS:
            return True, f"Denied binary format: {ext}"

        return False, ""

    def select_relevant_files(
        self,
        repo_path: Path,
        task: Union[TaskItem, Dict[str, Any]],
        target_files: Optional[List[str]] = None,
        max_files: int = 15,
    ) -> List[Path]:
        """Deterministically selects source files relevant to the active task."""
        if not repo_path.exists():
            return []

        task_title = task.title if isinstance(task, TaskItem) else task.get("title", "")
        task_desc = task.description if isinstance(task, TaskItem) else task.get("description", "")
        criteria = task.acceptance_criteria if isinstance(task, TaskItem) else task.get("acceptance_criteria", [])
        
        # 1. Explicit target files get highest priority
        selected: List[Path] = []
        explicit_candidates = target_files or []
        if isinstance(task, TaskItem):
            explicit_candidates.extend(task.modified_files + task.created_files)
        else:
            explicit_candidates.extend(task.get("modified_files", []) + task.get("created_files", []))

        for target in explicit_candidates:
            tp = repo_path / target if not Path(target).is_absolute() else Path(target)
            if tp.exists() and tp.is_file():
                denied, _ = self.is_denied_file(tp)
                if not denied and tp not in selected:
                    selected.append(tp)

        if len(selected) >= max_files:
            return selected[:max_files]

        # 2. Extract domain keywords from task
        text_corpus = f"{task_title} {task_desc} {' '.join(criteria)}".lower()
        tokens = {w for w in re.findall(r"[a-z0-9_]{3,}", text_corpus) if len(w) >= 3}
        
        # Noise filter
        noise = {"build", "create", "update", "verify", "check", "task", "project", "system", "file", "with", "from"}
        query_tokens = tokens - noise

        # 3. Scan repo candidates (deterministic ordering)
        candidates: List[Tuple[int, Path]] = []
        for root, dirs, files in os.walk(str(repo_path)):
            # Prune denied dirs
            dirs[:] = [d for d in dirs if d not in DENIED_DIR_NAMES and not d.startswith(".")]
            
            for fname in sorted(files):
                fpath = Path(root) / fname
                denied, _ = self.is_denied_file(fpath)
                if denied:
                    continue
                if fpath in selected:
                    continue

                # Score by token overlap with relative path and stem
                rel_parts = fpath.relative_to(repo_path).parts
                rel_text = " ".join(rel_parts).lower()
                
                score = sum(2 for t in query_tokens if t in fpath.stem.lower())
                score += sum(1 for t in query_tokens if t in rel_text)
                
                # Boost docs/SRS/ARCHITECTURE if task is requirements/architecture
                if any(k in text_corpus for k in ("srs", "requirements", "spec")) and "srs" in fpath.name.lower():
                    score += 5
                if any(k in text_corpus for k in ("architecture", "adr", "design")) and "architecture" in fpath.name.lower():
                    score += 5

                if score > 0:
                    candidates.append((score, fpath))

        # Sort by relevance score descending, then path ascending for determinism
        candidates.sort(key=lambda item: (-item[0], str(item[1])))
        for _, path in candidates:
            if len(selected) >= max_files:
                break
            selected.append(path)

        return selected

    def build_context(
        self,
        project: Union[ProjectManifest, Dict[str, Any]],
        task: Union[TaskItem, Dict[str, Any]],
        worker: Optional[Union[EngineeringWorker, WorkerSpec, str]] = None,
        current_phase: Optional[str] = None,
        acceptance_criteria: Optional[List[str]] = None,
        constraints: Optional[List[str]] = None,
        target_files: Optional[List[str]] = None,
    ) -> ProjectContextPackage:
        """Constructs a minimal, sanitized ProjectContextPackage for the target worker."""
        # 1. Project & Task Identity
        if isinstance(project, ProjectManifest):
            proj_id = project.project_id
            proj_name = project.project_name
            repo_path = Path(project.repository_path)
            phase = current_phase or (project.current_phase.value if hasattr(project.current_phase, "value") else str(project.current_phase))
            decisions = project.decision_history + project.architecture_decisions + project.uiux_decisions
            feature_scope = project.feature_scope
        else:
            proj_id = project.get("project_id", "proj_unknown")
            proj_name = project.get("project_name", "Unknown Project")
            repo_path = Path(project.get("repository_path", "."))
            phase = current_phase or project.get("current_phase", "PHASE_0_INTAKE")
            decisions = project.get("decision_history", []) + project.get("architecture_decisions", []) + project.get("uiux_decisions", [])
            feature_scope = project.get("feature_scope", {})

        if isinstance(task, TaskItem):
            task_id = task.task_id
            task_title = task.title
            task_desc = task.description
            criteria = acceptance_criteria or task.acceptance_criteria
        else:
            task_id = task.get("task_id", "t_unknown")
            task_title = task.get("title", "")
            task_desc = task.get("description", "")
            criteria = acceptance_criteria or task.get("acceptance_criteria", [])

        # Check explicit target_files for prohibited secrets if fail_on_prohibited_secret is enabled
        if target_files and self.config.fail_on_prohibited_secret:
            for tf in target_files:
                tp = repo_path / tf if not Path(tf).is_absolute() else Path(tf)
                denied, reason = self.is_denied_file(tp)
                if denied:
                    raise ContextSecurityError(
                        f"Prohibited sensitive file '{tp.name}' requested in context: {reason}",
                        reason="CONTEXT_SECURITY_REVIEW_REQUIRED",
                    )

        # 2. Determine Worker Security Policy & Limits
        is_external = False
        max_files = self.config.max_files
        max_total_bytes = self.config.max_total_context_bytes

        if worker:
            worker_type = None
            transport = ""
            if isinstance(worker, EngineeringWorker):
                worker_type = worker.worker_type
                transport = worker.transport
            elif isinstance(worker, WorkerSpec):
                worker_type = worker.worker_type
                transport = worker.transport
            elif isinstance(worker, str):
                if any(x in worker.lower() for x in ("chatgpt", "openai", "external", "manual")):
                    is_external = True

            if worker_type in (WorkerType.EXTERNAL_API, WorkerType.AGENCY, WorkerType.MANUAL) or transport == "MANUAL_TRANSPORT":
                is_external = True

        if is_external:
            security_level = "SENSITIVE_REDACTED"
            max_files = min(max_files, 10)
            max_total_bytes = min(max_total_bytes, 150_000)
        else:
            security_level = "PROJECT_INTERNAL"

        # 3. File Selection & Filtering
        selected_paths = self.select_relevant_files(
            repo_path=repo_path,
            task=task,
            target_files=target_files,
            max_files=max_files,
        )

        relevant_files: Dict[str, str] = {}
        provenance_map: Dict[str, Dict[str, Any]] = {}
        truncated_files: Dict[str, Dict[str, Any]] = {}
        
        files_considered = len(selected_paths)
        files_included = 0
        files_excluded = 0
        sensitive_files_skipped = 0
        redactions_applied = 0
        secret_patterns_detected: Set[str] = set()
        current_total_bytes = 0

        for fpath in selected_paths:
            denied, reason = self.is_denied_file(fpath)
            if denied:
                files_excluded += 1
                sensitive_files_skipped += 1
                logger.warning("Excluded sensitive file from context: %s (%s)", fpath.name, reason)
                if self.config.fail_on_prohibited_secret:
                    raise ContextSecurityError(
                        f"Prohibited sensitive file {fpath.name} requested in context.",
                        reason="CONTEXT_SECURITY_REVIEW_REQUIRED",
                    )
                continue

            try:
                raw_bytes = fpath.read_bytes()
            except Exception as exc:
                logger.error("Failed to read candidate file %s: %s", fpath, exc)
                files_excluded += 1
                continue

            rel_str = str(fpath.relative_to(repo_path)).replace("\\", "/")
            orig_size = len(raw_bytes)

            # Check if file has binary null bytes
            if b"\x00" in raw_bytes[:1024]:
                files_excluded += 1
                sensitive_files_skipped += 1
                continue

            raw_text = raw_bytes.decode("utf-8", errors="replace")

            # 4. Truncation Handling
            is_truncated = False
            inc_text = raw_text
            if orig_size > self.config.max_file_bytes:
                is_truncated = True
                inc_text = raw_text[:self.config.max_file_bytes] + f"\n\n... [TRUNCATED: original {orig_size} bytes, included {self.config.max_file_bytes} bytes. Reason: Exceeded max file size] ..."
                truncated_files[rel_str] = {
                    "original_size": orig_size,
                    "included_size": len(inc_text),
                    "selection_reason": "File size exceeds single file threshold",
                }

            # Check total context budget
            if current_total_bytes + len(inc_text) > max_total_bytes:
                files_excluded += 1
                continue

            # 5. Secret Sanitization
            sanitized_text, findings = self.sanitizer.sanitize(inc_text, file_path=rel_str)
            if findings:
                redactions_applied += len(findings)
                for f in findings:
                    secret_patterns_detected.add(f["secret_type"])

            relevant_files[rel_str] = sanitized_text
            current_total_bytes += len(sanitized_text)
            files_included += 1

            # Provenance recording
            file_hash = hashlib.sha256(raw_bytes).hexdigest()[:12]
            provenance_map[rel_str] = {
                "source_type": "project_source_file",
                "path": rel_str,
                "sha256": file_hash,
                "line_count": sanitized_text.count("\n") + 1,
                "truncated": is_truncated,
            }

        # 6. Excerpt Extraction (SRS & Architecture)
        srs_excerpts: List[str] = []
        if feature_scope and isinstance(feature_scope, dict):
            must_have = feature_scope.get("must_have", [])
            if must_have:
                srs_excerpts.append(f"Approved Must-Have Scope: {', '.join(must_have[:5])}")

        arch_excerpts: List[str] = []
        for dec in decisions[:5]:
            if isinstance(dec, dict):
                arch_excerpts.append(f"{dec.get('category', 'Architecture')}: {dec.get('decision', '')}")

        # 7. Build Sanitization Report
        sanitization_report = {
            "files_considered": files_considered,
            "files_included": files_included,
            "files_excluded": files_excluded,
            "secret_patterns_detected": sorted(list(secret_patterns_detected)),
            "redactions_applied": redactions_applied,
            "context_size_bytes": current_total_bytes,
            "truncations": len(truncated_files),
            "sensitive_files_skipped": sensitive_files_skipped,
            "security_level": security_level,
        }

        logger.info(
            "Built context package for task %s (%s): %d files included, %d redactions",
            task_id,
            security_level,
            files_included,
            redactions_applied,
        )

        return ProjectContextPackage(
            task_id=task_id,
            project_id=proj_id,
            project_name=proj_name,
            current_phase=phase,
            task_title=task_title,
            task_description=task_desc,
            acceptance_criteria=criteria,
            constraints=constraints or [],
            relevant_files=relevant_files,
            srs_excerpts=srs_excerpts,
            architecture_excerpts=arch_excerpts,
            prior_decisions=decisions[:5],
            sanitization_report=sanitization_report,
            source_provenance=provenance_map,
            security_level=security_level,
            truncated_files=truncated_files,
        )


# Global singleton instance
DEFAULT_CONTEXT_BUILDER = ProjectContextBuilder()
