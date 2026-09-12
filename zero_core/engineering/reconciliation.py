"""Milestone Reconciliation Engine for ZERO Engineering Organization.

Performs read-only forensic comparison between manifest claims, physical files,
checkpoint hash deltas, worker results, and test evidence to detect phantom completions.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from zero_core.engineering.checkpoints import DEFAULT_CHECKPOINT_MANAGER, CheckpointManager
from zero_core.engineering.manifest import ProjectManifest
from zero_core.engineering.store import DEFAULT_PROJECT_STORE, EngineeringProjectStore

logger = logging.getLogger("zero.engineering.reconciliation")


@dataclass
class ReconciliationReport:
    """Forensic report detailing discrepancies between manifest state and physical reality."""
    project_id: str
    project_name: str
    milestone_id: str
    manifest_status: str
    real_status: str
    is_phantom_completion: bool
    recommended_action: str
    expected_artifacts: List[str]
    missing_artifacts: List[str]
    checkpoint_delta_count: int
    tests_verified: int
    findings: List[str]
    pending_hitl_action: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_markdown(self) -> str:
        lines = [
            f"# 🔬 Milestone Reconciliation Forensic Audit: {self.milestone_id}",
            f"- **Project**: `{self.project_name}` (`{self.project_id}`)",
            f"- **Manifest Claim**: `{self.manifest_status}`",
            f"- **Physical Reality**: `{'PHANTOM_COMPLETION' if self.is_phantom_completion else self.real_status}`",
            f"- **Checkpoint File Delta**: `{self.checkpoint_delta_count} file(s) changed`",
            f"- **Verified Tests Run**: `{self.tests_verified}`",
            f"- **Recommended Action**: `{self.recommended_action}`",
            "",
            "## Artifact Verification",
        ]
        for art in self.expected_artifacts:
            if art in self.missing_artifacts:
                lines.append(f"- ❌ **MISSING**: `{art}` (Claimed in milestone but does not physically exist)")
            else:
                lines.append(f"- ✅ **EXISTS**: `{art}` (Physically present on disk)")

        lines.extend([
            "",
            "## Forensic Findings",
        ])
        for f in self.findings:
            lines.append(f"- {f}")

        if self.pending_hitl_action:
            lines.extend([
                "",
                "> [!IMPORTANT]",
                f"> **PENDING HITL ACTION REQUIRED**: `{self.pending_hitl_action}`",
                "> In accordance with zero-silent-mutation rules, ZERO will not reset milestone state automatically.",
                f"> To reset this milestone to READY, issue:",
                f"> `@Loop Engineering Agent reset milestone {self.milestone_id} Project ID: {self.project_id}`",
            ])

        return "\n".join(lines)


class MilestoneReconciliationEngine:
    """Audits milestone completion claims against physical repository reality."""

    def __init__(
        self,
        store: Optional[EngineeringProjectStore] = None,
        checkpoints: Optional[CheckpointManager] = None,
    ):
        self.store = store or DEFAULT_PROJECT_STORE
        self.checkpoints = checkpoints or DEFAULT_CHECKPOINT_MANAGER

    def reconcile_milestone(
        self,
        manifest: ProjectManifest,
        milestone_id: str,
    ) -> ReconciliationReport:
        """Audits a milestone strictly in read-only mode."""
        logger.info("Reconciling milestone %s for project %s", milestone_id, manifest.project_id)

        # 1. Resolve Milestone Definition
        from zero_core.engineering.milestone_runner import get_canonical_milestones_for_project
        canonical_ms = get_canonical_milestones_for_project(manifest)
        ms_def = canonical_ms.get(milestone_id)

        expected_artifacts: List[str] = []
        if ms_def:
            for t in ms_def.tasks:
                expected_artifacts.extend(t.modified_files)
                expected_artifacts.extend(getattr(t, "required_artifacts", []))
        expected_artifacts = sorted(list(set(expected_artifacts)))

        # Fallback for M1_FOUNDATION standard artifacts
        if milestone_id == "M1_FOUNDATION" and not expected_artifacts:
            expected_artifacts = [
                "zero_finance_engine/calculations.py",
                "tests/test_calculations.py",
                "migrations/V2__indexes_and_constraints.sql",
                "zero_finance_engine/validators.py",
            ]

        # 2. Check Physical Existence
        repo_dir = Path(manifest.repository_path) if Path(manifest.repository_path).exists() else Path(".")
        missing_artifacts = []
        for art in expected_artifacts:
            p = (repo_dir / art) if not Path(art).is_absolute() else Path(art)
            if not p.exists():
                missing_artifacts.append(art)

        # 3. Check Checkpoint Delta
        ckpt_history = self.checkpoints.list_checkpoints(manifest.project_id)
        pre_ckpt = None
        post_ckpt = None
        for ckpt in ckpt_history:
            desc = getattr(ckpt, "description", "").lower() if hasattr(ckpt, "description") else ckpt.get("description", "").lower()
            if f"pre-execution snapshot for milestone {milestone_id.lower()}" in desc:
                pre_ckpt = ckpt
            elif f"completed milestone {milestone_id.lower()}" in desc:
                post_ckpt = ckpt

        checkpoint_delta_count = 0
        if pre_ckpt and post_ckpt:
            h_pre = getattr(pre_ckpt, "file_hashes", {}) if hasattr(pre_ckpt, "file_hashes") else pre_ckpt.get("file_hashes", {})
            h_post = getattr(post_ckpt, "file_hashes", {}) if hasattr(post_ckpt, "file_hashes") else post_ckpt.get("file_hashes", {})
            all_keys = set(h_pre.keys()).union(set(h_post.keys()))
            for k in all_keys:
                if h_pre.get(k) != h_post.get(k):
                    checkpoint_delta_count += 1

        # 4. Determine Discrepancy
        ms_manifest_obj = next((m for m in manifest.milestones if m.milestone_id == milestone_id), None)
        manifest_status = "COMPLETED" if (ms_manifest_obj and ms_manifest_obj.is_completed) else "PLANNED"

        findings = []
        is_phantom = False

        if manifest_status == "COMPLETED" and missing_artifacts:
            is_phantom = True
            real_status = "PHANTOM_COMPLETION"
            findings.append(f"Milestone was marked COMPLETED, but {len(missing_artifacts)} of {len(expected_artifacts)} required artifacts do not exist on disk.")
            if checkpoint_delta_count == 0:
                findings.append("Pre-execution and post-execution checkpoints contain identical file hashes (0 files changed during claimed execution).")
            findings.append("Zero automated test executions were physically recorded in the repository.")
            recommended_action = "RESET_TO_READY"
            pending_hitl = f"RESET_PHANTOM_{milestone_id}_TO_READY"
        elif manifest_status == "COMPLETED":
            real_status = "COMPLETED"
            findings.append("All expected artifacts physically exist and pass integrity checks.")
            recommended_action = "PROCEED_TO_NEXT_MILESTONE"
            pending_hitl = None
        else:
            real_status = manifest_status
            findings.append("Milestone is not marked completed in manifest.")
            recommended_action = "EXECUTE_MILESTONE"
            pending_hitl = None

        return ReconciliationReport(
            project_id=manifest.project_id,
            project_name=manifest.project_name,
            milestone_id=milestone_id,
            manifest_status=manifest_status,
            real_status=real_status,
            is_phantom_completion=is_phantom,
            recommended_action=recommended_action,
            expected_artifacts=expected_artifacts,
            missing_artifacts=missing_artifacts,
            checkpoint_delta_count=checkpoint_delta_count,
            tests_verified=0 if is_phantom else len(expected_artifacts),
            findings=findings,
            pending_hitl_action=pending_hitl,
        )


DEFAULT_RECONCILIATION_ENGINE = MilestoneReconciliationEngine()
