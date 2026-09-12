"""Contradiction Detector for ZERO Deep Discovery.

Validates discovered artifacts and evidence claims across workers and subsystems to identify
conflicting quantitative metrics (e.g. workflow node counts), divergent table schemas,
and incompatible implementation statuses.

Rule: ZERO must never present contradictory quantitative evidence as verified.
If a contradiction exists, it flags CONFLICTING_EVIDENCE and downgrades confidence.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from zero_core.engineering.discovery.evidence import (
    CanonicalArtifact,
    EvidenceLedger,
    EvidenceStatus,
    FeatureEvidence,
)

logger = logging.getLogger(__name__)


@dataclass
class ContradictionRecord:
    """Represents an identified contradiction between evidence sources."""
    artifact_name: str
    contradiction_type: str  # "NODE_COUNT_MISMATCH", "STATUS_CONFLICT", "METADATA_MISMATCH"
    source_a: str
    source_b: str
    claim_a: Any
    claim_b: Any
    details: str
    action_taken: str = "FLAG_CONFLICTING_EVIDENCE"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ContradictionDetector:
    """Scans artifacts and evidence claims for logical, quantitative, and status contradictions."""

    def detect_artifact_contradictions(
        self,
        artifacts: List[CanonicalArtifact],
        raw_worker_outputs: Optional[List[Dict[str, Any]]] = None,
    ) -> List[ContradictionRecord]:
        """Detects contradictions within canonical artifacts and between worker outputs."""
        contradictions: List[ContradictionRecord] = []
        artifacts_by_name: Dict[str, List[CanonicalArtifact]] = {}

        for art in artifacts:
            norm_name = art.name.lower().strip()
            artifacts_by_name.setdefault(norm_name, []).append(art)

        # Check across multiple artifacts with the same name
        for name, group in artifacts_by_name.items():
            if len(group) > 1:
                base = group[0]
                for other in group[1:]:
                    if base.node_count is not None and other.node_count is not None:
                        if base.node_count != other.node_count:
                            contradictions.append(
                                ContradictionRecord(
                                    artifact_name=base.name,
                                    contradiction_type="NODE_COUNT_MISMATCH",
                                    source_a=f"{base.source_worker} ({base.relative_path})",
                                    source_b=f"{other.source_worker} ({other.relative_path})",
                                    claim_a=base.node_count,
                                    claim_b=other.node_count,
                                    details=f"Workflow {base.name} reported with {base.node_count} nodes by {base.source_worker} vs {other.node_count} nodes by {other.source_worker}.",
                                )
                            )

        # Check raw worker outputs for contradictory claims regarding known files
        if raw_worker_outputs:
            for art in artifacts:
                if art.node_count is not None:
                    fname = art.name.lower()
                    for out in raw_worker_outputs:
                        analysis_text = str(out.get("analysis", "")).lower()
                        if fname in analysis_text:
                            # Look for patterns like "250 nodes" or "X nodes"
                            import re
                            matches = re.findall(rf'{re.escape(fname)}[^\.\n]*?(\d+)\s+nodes', analysis_text)
                            for m in matches:
                                try:
                                    cnt = int(m)
                                    if cnt != art.node_count:
                                        contradictions.append(
                                            ContradictionRecord(
                                                artifact_name=art.name,
                                                contradiction_type="NODE_COUNT_MISMATCH",
                                                source_a=f"Canonical Parser ({art.relative_path})",
                                                source_b=f"Worker Text ({out.get('worker_id', 'unknown')})",
                                                claim_a=art.node_count,
                                                claim_b=cnt,
                                                details=f"Workflow '{art.name}' canonically contains {art.node_count} nodes, but worker text asserts {cnt} nodes.",
                                            )
                                        )
                                except ValueError:
                                    pass

        return contradictions

    def detect_evidence_contradictions(
        self,
        evidence_list: List[FeatureEvidence],
    ) -> List[ContradictionRecord]:
        """Detects conflicting feature statuses across evidence entries."""
        contradictions: List[ContradictionRecord] = []
        by_feature: Dict[str, List[FeatureEvidence]] = {}

        for ev in evidence_list:
            feat_key = ev.feature.lower().strip()
            by_feature.setdefault(feat_key, []).append(ev)

        for feat_name, group in by_feature.items():
            statuses = {e.status for e in group}
            # Contradiction: One source says IMPLEMENTED_VERIFIED while another says NOT_FOUND
            if EvidenceStatus.IMPLEMENTED_VERIFIED in statuses and EvidenceStatus.NOT_FOUND in statuses:
                impl_ev = next(e for e in group if e.status == EvidenceStatus.IMPLEMENTED_VERIFIED)
                nf_ev = next(e for e in group if e.status == EvidenceStatus.NOT_FOUND)
                contradictions.append(
                    ContradictionRecord(
                        artifact_name=feat_name,
                        contradiction_type="STATUS_CONFLICT",
                        source_a=f"{impl_ev.source_file}:{impl_ev.location}",
                        source_b=f"{nf_ev.source_file}:{nf_ev.location}",
                        claim_a=impl_ev.status.value,
                        claim_b=nf_ev.status.value,
                        details=f"Feature '{feat_name}' is claimed as IMPLEMENTED_VERIFIED in {impl_ev.source_file} but NOT_FOUND in {nf_ev.source_file}.",
                    )
                )

        return contradictions

    def reconcile_ledger(
        self,
        ledger: EvidenceLedger,
        contradictions: List[ContradictionRecord],
    ) -> None:
        """Applies contradiction penalties to the evidence ledger, downgrading conflicted statuses."""
        conflicted_artifacts = {c.artifact_name.lower() for c in contradictions}
        for ev in ledger.list_entries():
            if ev.feature.lower() in conflicted_artifacts or ev.source_file.lower() in conflicted_artifacts:
                ev.status = EvidenceStatus.CONFLICTING_EVIDENCE
                ev.confidence = min(ev.confidence, 0.4)
                ev.verification_notes += f" [FLAGGED CONFLICTING_EVIDENCE: Discrepancy detected across sources]"
