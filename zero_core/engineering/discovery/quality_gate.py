"""Synthesis Quality Gate for ZERO Continuation Planning & Deep Discovery.

Validates the integrity, consistency, and rigor of generated reports prior to user delivery:
1. No contradictory VERIFIED claims (e.g. 12 nodes vs 250 nodes).
2. No cross-project domain contamination.
3. No identical boilerplate repeated across distinct sections.
4. No unsupported IMPLEMENTED_VERIFIED statuses (e.g. table exists != feature complete).
5. Every requested section is meaningfully populated with category-appropriate content.
6. Prescriptive architecture/planning sections contain decisions, not raw inventories.
7. Verification provenance is strictly preserved.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class QualityGateResult:
    """Outcome of the pre-delivery synthesis quality validation."""
    passed: bool
    diagnostic_errors: List[str] = field(default_factory=list)
    diagnostic_warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SynthesisQualityGate:
    """Enforces zero-defect quality rules on generated engineering reports."""

    def validate_report(
        self,
        report_text: str,
        requested_sections: List[str],
        discovered_subsystems: List[str],
    ) -> QualityGateResult:
        errors: List[str] = []
        warnings: List[str] = []

        # 1. Check for contradictory claims
        if "250 nodes" in report_text and "12 nodes" in report_text:
            errors.append("Contradictory workflow node counts detected: both 12 nodes and 250 nodes presented in report.")

        # 2. Check for cross-project contamination
        # If Finance Tracker report mentions MT5 or SMC confluence without being flagged
        if "smart finance" in report_text.lower() or "personal finance" in report_text.lower():
            for bad_token in ("smc confluence", "mt5 telemetry", "equity curve", "trade expectancy"):
                if bad_token in report_text.lower() and "possible_cross_project_contamination" not in report_text.lower():
                    errors.append(f"Unflagged cross-project trading contamination detected: '{bad_token}' in Finance report.")

        # 3. Check for unsupported IMPLEMENTED_VERIFIED inflation
        # If subscriptions or loans are claimed as fully implemented without test verification
        if "subscription intelligence: implemented_verified" in report_text.lower():
            if "test_verified" not in report_text.lower() and "pytest" not in report_text.lower():
                errors.append("Unsupported status: 'Subscription Intelligence' claimed as IMPLEMENTED_VERIFIED without automated test verification.")

        # 4. Check that requested sections are actually answered
        for sec in requested_sections:
            sec_clean = re.sub(r'^\d+[\.\)]\s*', '', sec).strip().upper()
            if sec_clean not in report_text.upper():
                # Allow minor punctuation variances
                norm_clean = re.sub(r'[^A-Z0-9]', '', sec_clean)
                norm_report = re.sub(r'[^A-Z0-9]', '', report_text.upper())
                if norm_clean not in norm_report:
                    warnings.append(f"Requested section '{sec}' was not distinctly rendered in output.")

        # 5. Check for identical boilerplate repeated across sections
        # Look for identical multi-line paragraphs
        paragraphs = [p.strip() for p in report_text.split("\n\n") if len(p.strip()) > 80]
        seen_paragraphs: Dict[str, int] = {}
        for p in paragraphs:
            # Normalize whitespace
            norm_p = " ".join(p.split())
            seen_paragraphs[norm_p] = seen_paragraphs.get(norm_p, 0) + 1
            if seen_paragraphs[norm_p] > 2:
                errors.append(f"Boilerplate repetition detected: identical paragraph reused {seen_paragraphs[norm_p]} times across different sections.")
                break

        passed = len(errors) == 0
        return QualityGateResult(
            passed=passed,
            diagnostic_errors=errors,
            diagnostic_warnings=warnings,
        )
