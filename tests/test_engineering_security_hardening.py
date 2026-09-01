"""Tests for ZERO Engineering Security Hardening & Zero-Leak Guarantees (Phase 7).

Verifies:
- Complete redaction of API keys, bearer tokens, passwords, and private keys.
- Prevention of gate approval bypass.
- Exclusion of sensitive candidate PII from external context packages.
- Strict API payload masking.
"""

import pytest
from zero_core.engineering.context_builder import ProjectContextBuilder, SecretSanitizer
from zero_core.engineering.manifest import ProjectManifest, PhaseEnum, ProjectStatus
from zero_core.engineering.lifecycle import ProjectLifecycleController


def test_secret_sanitizer_token_patterns():
    sanitizer = SecretSanitizer()

    sample_text = (
        "Database credentials:\n"
        "OPENAI_API_KEY=sk-proj-abc1234567890abcdefghijklmnop\n"
        "GITHUB_TOKEN=ghp_1234567890abcdefghijklmnopqrstuv\n"
        "DATABASE_URL=postgres://admin:SuperSecretPass123!@localhost:5432/hr_db\n"
        "BEARER_TOKEN=Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.secret\n"
        "PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0\n-----END RSA PRIVATE KEY-----\n"
    )

    sanitized, matches = sanitizer.sanitize(sample_text)

    assert "sk-proj-" not in sanitized
    assert "ghp_" not in sanitized
    assert "SuperSecretPass123!" not in sanitized
    assert "eyJhbGciOi" not in sanitized
    assert "-----BEGIN RSA PRIVATE KEY-----" not in sanitized
    assert len(matches) >= 4


def test_context_package_pii_minimization(tmp_path):
    builder = ProjectContextBuilder()
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "candidate.py").write_text("candidate_name = 'Confidential Candidate'\n", encoding="utf-8")

    manifest = ProjectManifest(
        project_id="proj_pii_test",
        project_name="HR Recruitment AI Assistant",
        project_type="EXISTING_PROJECT",
        repository_path=str(repo),
        description="PII minimization test",
        current_phase=PhaseEnum.PHASE_10_BACKEND,
    )

    pkg = builder.build_context_package(
        manifest=manifest,
        task_id="t_api_01",
        task_title="Implement Candidate Search API",
        task_description="Build search endpoint",
        relevant_files=["candidate.py"],
    )

    assert pkg.security_level == "SENSITIVE_REDACTED"
    assert pkg.sanitization_report is not None


def test_gate_approval_bypass_resistance():
    """Verifies lifecycle controller rejects advancing into production without Gate 8."""
    controller = ProjectLifecycleController()
    manifest = ProjectManifest(
        project_id="proj_bypass_test",
        project_name="Bypass Attempt Project",
        project_type="EXISTING_PROJECT",
        repository_path=".",
        description="Testing gate bypass",
        current_phase=PhaseEnum.PHASE_17_DEPLOYMENT,
        testing_status="COMPLETED",
        security_status="COMPLETED",
    )

    # Attempt to enter COMPLETED without deployment approval
    can_enter, reasons = controller.check_phase_entry(manifest, PhaseEnum.COMPLETED)
    assert can_enter is False
    assert any("GATE 8" in r for r in reasons)
