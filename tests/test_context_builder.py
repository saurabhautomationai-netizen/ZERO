"""Comprehensive Unit & Regression Tests for ProjectContextBuilder & SecretSanitizer."""

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path

import pytest
from zero_core.engineering.context_builder import (
    ContextBuilderConfig,
    ContextSecurityError,
    ProjectContextBuilder,
    SecretSanitizer,
)
from zero_core.engineering.manifest import PhaseEnum, ProjectManifest, TaskItem
from zero_core.engineering.workers.base import (
    ProjectContextPackage,
    WorkerCapability,
    WorkerType,
)
from zero_core.engineering.workers.native import CodingAgentWorker
from zero_core.engineering.workers.registry import WorkerSpec


@pytest.fixture
def temp_project(tmp_path):
    """Creates a temporary realistic project structure with code, docs, and test fixtures."""
    repo = tmp_path / "sample_repo"
    repo.mkdir()

    # Core source files
    src = repo / "src"
    src.mkdir()
    (src / "calculator.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n",
        encoding="utf-8",
    )
    (src / "database_service.py").write_text(
        "import os\nDATABASE_URL = 'postgresql://db_user:fake_password_123@db.internal:5432/app_db'\n",
        encoding="utf-8",
    )
    (src / "auth_service.py").write_text(
        "OPENAI_KEY = 'sk-proj-faketestsecretkey1234567890abcdef'\n"
        "GITHUB_TOKEN = 'ghp_faketestgithubtoken1234567890abcdef'\n"
        "TELEGRAM_BOT_TOKEN = '123456789:ABCdefGhIJKlmNoPQRstuVWXyz12345'\n"
        "BEARER_AUTH = 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.faketokenpayload.abcdef'\n"
        "password = 'fake_super_secret_password_here'\n"
        "api_key = 'fake_generic_secret_key_value'\n",
        encoding="utf-8",
    )

    # Docs
    docs = repo / "docs"
    docs.mkdir()
    (docs / "SRS.md").write_text("# SRS: Calculator App\n- Must calculate accurately.\n", encoding="utf-8")
    (docs / "ARCHITECTURE.md").write_text("# Architecture\n- Clean architecture layer.\n", encoding="utf-8")

    # Tests
    tests = repo / "tests"
    tests.mkdir()
    (tests / "test_calculator.py").write_text("def test_add():\n    assert True\n", encoding="utf-8")

    # Unrelated files (Trading, Voice, etc.)
    (src / "mt5_trading_runner.py").write_text("def run_mt5_live(): pass\n", encoding="utf-8")

    # Sensitive files that should be excluded
    (repo / ".env").write_text("DATABASE_PASSWORD=fake_env_password_xyz\n", encoding="utf-8")
    (repo / "credentials.json").write_text("{\"client_secret\": \"fake_oauth_secret_123\"}\n", encoding="utf-8")
    (repo / "server.key").write_text(
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0fakekeydata...\n-----END RSA PRIVATE KEY-----\n",
        encoding="utf-8",
    )

    # Binary files
    (repo / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRfakebinarycontent")
    (repo / "app.db").write_bytes(b"SQLite format 3\x00fakebinarydatabasecontent")

    return repo


def test_1_basic_context_generation(temp_project):
    builder = ProjectContextBuilder()
    task = TaskItem(
        task_id="t_calc_01",
        milestone_id="m_core",
        title="Add division to calculator",
        description="Implement division function with zero check in calculator",
        acceptance_criteria=["ZeroDivisionError handled"],
    )
    manifest = ProjectManifest(
        project_id="p_calc",
        project_name="Calculator Engine",
        description="Math calculator",
        repository_path=str(temp_project),
    )

    pkg = builder.build_context(manifest, task)
    assert isinstance(pkg, ProjectContextPackage)
    assert pkg.task_id == "t_calc_01"
    assert pkg.project_name == "Calculator Engine"
    assert pkg.current_phase == "PHASE_0_INTAKE"
    assert "src/calculator.py" in pkg.relevant_files


def test_2_relevant_file_inclusion(temp_project):
    builder = ProjectContextBuilder()
    task = TaskItem(
        task_id="t_calc_02",
        milestone_id="m_core",
        title="Calculator functions",
        description="Refactor calculator multiply and add methods",
    )
    files = builder.select_relevant_files(temp_project, task)
    file_names = [f.name for f in files]
    assert "calculator.py" in file_names


def test_3_irrelevant_file_exclusion(temp_project):
    builder = ProjectContextBuilder()
    task = TaskItem(
        task_id="t_calc_03",
        milestone_id="m_core",
        title="Calculator addition",
        description="Improve calculator arithmetic precision",
    )
    manifest = ProjectManifest(
        project_id="p_calc",
        project_name="Calculator",
        description="Test",
        repository_path=str(temp_project),
    )
    pkg = builder.build_context(manifest, task)
    assert "src/mt5_trading_runner.py" not in pkg.relevant_files


def test_4_env_file_exclusion(temp_project):
    builder = ProjectContextBuilder()
    denied, reason = builder.is_denied_file(temp_project / ".env")
    assert denied is True
    assert "Denied sensitive file" in reason

    task = TaskItem(task_id="t1", milestone_id="m1", title="Inspect env", description="Check .env")
    manifest = ProjectManifest(project_id="p1", project_name="Test", description="T", repository_path=str(temp_project))
    pkg = builder.build_context(manifest, task, target_files=[".env"])
    assert ".env" not in pkg.relevant_files


def test_5_openai_key_redaction():
    sanitizer = SecretSanitizer()
    text = "openai_key = 'sk-proj-faketestsecretkey1234567890abcdef'"
    sanitized, findings = sanitizer.sanitize(text)
    assert "sk-proj-faketestsecretkey1234567890abcdef" not in sanitized
    assert "[REDACTED_OPENAI_API_KEY]" in sanitized or "[REDACTED_CREDENTIAL]" in sanitized
    assert len(findings) >= 1


def test_6_generic_api_key_redaction():
    sanitizer = SecretSanitizer()
    text = "api_key = 'custom_secret_key_value_98765'"
    sanitized, findings = sanitizer.sanitize(text)
    assert "custom_secret_key_value_98765" not in sanitized
    assert "[REDACTED_CREDENTIAL]" in sanitized


def test_7_password_redaction():
    sanitizer = SecretSanitizer()
    text = "password = 'MySecretSuperPassword123!'"
    sanitized, findings = sanitizer.sanitize(text)
    assert "MySecretSuperPassword123!" not in sanitized
    assert "[REDACTED_CREDENTIAL]" in sanitized


def test_8_bearer_token_redaction():
    sanitizer = SecretSanitizer()
    text = "headers = {'Authorization': 'Bearer myfakelongtoken1234567890abcdef'}"
    sanitized, findings = sanitizer.sanitize(text)
    assert "myfakelongtoken1234567890abcdef" not in sanitized
    assert "[REDACTED_BEARER_TOKEN]" in sanitized


def test_9_database_url_redaction():
    sanitizer = SecretSanitizer()
    text = "DATABASE_URL = 'postgresql://admin:super_secret_pw@db.production.net:5432/main_db'"
    sanitized, findings = sanitizer.sanitize(text)
    assert "super_secret_pw" not in sanitized
    assert "admin:super_secret_pw" not in sanitized
    assert "db.production.net" in sanitized
    assert "main_db" in sanitized
    assert "[REDACTED_PASSWORD]" in sanitized


def test_10_private_key_exclusion_and_redaction(temp_project):
    builder = ProjectContextBuilder()
    denied, reason = builder.is_denied_file(temp_project / "server.key")
    assert denied is True

    sanitizer = SecretSanitizer()
    raw = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0fakekeydata...\n-----END RSA PRIVATE KEY-----"
    sanitized, findings = sanitizer.sanitize(raw)
    assert "fakekeydata" not in sanitized
    assert "[REDACTED_PRIVATE_KEY]" in sanitized


def test_11_github_token_redaction():
    sanitizer = SecretSanitizer()
    text = "token = 'ghp_faketestgithubtoken1234567890abcdef'"
    sanitized, findings = sanitizer.sanitize(text)
    assert "ghp_faketestgithubtoken1234567890abcdef" not in sanitized
    assert "[REDACTED_GITHUB_TOKEN]" in sanitized or "[REDACTED_CREDENTIAL]" in sanitized


def test_12_telegram_token_redaction():
    sanitizer = SecretSanitizer()
    text = "BOT_TOKEN = '123456789:ABCdefGhIJKlmNoPQRstuVWXyz12345'"
    sanitized, findings = sanitizer.sanitize(text)
    assert "123456789:ABCdefGhIJKlmNoPQRstuVWXyz12345" not in sanitized
    assert "[REDACTED_TELEGRAM_TOKEN]" in sanitized


def test_13_nested_configuration_secret_redaction(temp_project):
    config_file = temp_project / "config.yaml"
    config_file.write_text(
        "database:\n  host: 127.0.0.1\n  password: 'fake_nested_password_xyz'\n",
        encoding="utf-8",
    )
    builder = ProjectContextBuilder()
    task = TaskItem(task_id="t_cfg", milestone_id="m1", title="Database config", description="review db config")
    manifest = ProjectManifest(project_id="p1", project_name="T", description="T", repository_path=str(temp_project))
    pkg = builder.build_context(manifest, task, target_files=["config.yaml"])
    
    cfg_content = pkg.relevant_files["config.yaml"]
    assert "fake_nested_password_xyz" not in cfg_content
    assert "[REDACTED_CREDENTIAL]" in cfg_content


def test_14_large_file_handling(temp_project):
    large_file = temp_project / "large_data.txt"
    # Write 60 KB (threshold is 50 KB)
    large_file.write_text("line of text data here\n" * 2500, encoding="utf-8")
    
    builder = ProjectContextBuilder(ContextBuilderConfig(max_file_bytes=50_000))
    task = TaskItem(task_id="t_lg", milestone_id="m1", title="Large text data", description="read data")
    manifest = ProjectManifest(project_id="p1", project_name="T", description="T", repository_path=str(temp_project))
    
    pkg = builder.build_context(manifest, task, target_files=["large_data.txt"])
    assert "large_data.txt" in pkg.truncated_files
    assert pkg.truncated_files["large_data.txt"]["original_size"] > 50_000
    assert "[TRUNCATED:" in pkg.relevant_files["large_data.txt"]


def test_15_binary_file_handling(temp_project):
    builder = ProjectContextBuilder()
    assert builder.is_denied_file(temp_project / "logo.png")[0] is True
    assert builder.is_denied_file(temp_project / "app.db")[0] is True

    task = TaskItem(task_id="t_bin", milestone_id="m1", title="Check assets", description="inspect logo")
    manifest = ProjectManifest(project_id="p1", project_name="T", description="T", repository_path=str(temp_project))
    pkg = builder.build_context(manifest, task, target_files=["logo.png", "app.db"])
    assert "logo.png" not in pkg.relevant_files
    assert "app.db" not in pkg.relevant_files


def test_16_external_worker_policy(temp_project):
    builder = ProjectContextBuilder()
    task = TaskItem(task_id="t_ext", milestone_id="m1", title="External review", description="review calculator")
    manifest = ProjectManifest(project_id="p1", project_name="T", description="T", repository_path=str(temp_project))
    
    ext_spec = WorkerSpec(
        worker_id="chatgpt_reviewer",
        name="ChatGPT",
        worker_type=WorkerType.EXTERNAL_API,
        capabilities=["code_review"],
        transport="OPENAI_API",
    )
    pkg = builder.build_context(manifest, task, worker=ext_spec)
    assert pkg.security_level == "SENSITIVE_REDACTED"
    assert pkg.sanitization_report["security_level"] == "SENSITIVE_REDACTED"


def test_17_native_worker_policy(temp_project):
    builder = ProjectContextBuilder()
    task = TaskItem(task_id="t_nat", milestone_id="m1", title="Native coding", description="review calculator")
    manifest = ProjectManifest(project_id="p1", project_name="T", description="T", repository_path=str(temp_project))
    
    worker = CodingAgentWorker()
    pkg = builder.build_context(manifest, task, worker=worker)
    assert pkg.security_level == "PROJECT_INTERNAL"


def test_18_manual_transport_policy(temp_project):
    builder = ProjectContextBuilder()
    task = TaskItem(task_id="t_man", milestone_id="m1", title="Manual task", description="review calculator")
    manifest = ProjectManifest(project_id="p1", project_name="T", description="T", repository_path=str(temp_project))
    
    manual_spec = WorkerSpec(
        worker_id="manual_architect",
        name="Manual Worker",
        worker_type=WorkerType.MANUAL,
        capabilities=["architecture"],
        transport="MANUAL_TRANSPORT",
    )
    pkg = builder.build_context(manifest, task, worker=manual_spec)
    assert pkg.security_level == "SENSITIVE_REDACTED"


def test_19_provenance_metadata(temp_project):
    builder = ProjectContextBuilder()
    task = TaskItem(task_id="t_prov", milestone_id="m1", title="Calculator math", description="check calculator")
    manifest = ProjectManifest(project_id="p1", project_name="T", description="T", repository_path=str(temp_project))
    pkg = builder.build_context(manifest, task, target_files=["src/calculator.py"])
    
    assert "src/calculator.py" in pkg.source_provenance
    prov = pkg.source_provenance["src/calculator.py"]
    assert prov["source_type"] == "project_source_file"
    assert len(prov["sha256"]) == 12
    assert prov["line_count"] > 0


def test_20_context_size_limit_behavior(temp_project):
    # Set very small budget (200 bytes)
    builder = ProjectContextBuilder(ContextBuilderConfig(max_total_context_bytes=200))
    task = TaskItem(task_id="t_sz", milestone_id="m1", title="Multiple files", description="check files")
    manifest = ProjectManifest(project_id="p1", project_name="T", description="T", repository_path=str(temp_project))
    
    pkg = builder.build_context(manifest, task, target_files=["src/calculator.py", "docs/SRS.md"])
    # Total context budget should limit the number of files included
    assert pkg.sanitization_report["context_size_bytes"] <= 300


def test_21_safe_failure_behavior(temp_project):
    # When fail_on_prohibited_secret is enabled, attempting to force a denied file raises ContextSecurityError
    builder = ProjectContextBuilder(ContextBuilderConfig(fail_on_prohibited_secret=True))
    task = TaskItem(task_id="t_fail", milestone_id="m1", title="Read env", description="read .env")
    manifest = ProjectManifest(project_id="p1", project_name="T", description="T", repository_path=str(temp_project))
    
    with pytest.raises(ContextSecurityError) as exc_info:
        builder.build_context(manifest, task, target_files=[".env"])
    assert exc_info.value.reason == "CONTEXT_SECURITY_REVIEW_REQUIRED"


def test_22_no_secret_values_in_logs(caplog):
    caplog.set_level(logging.INFO)
    sanitizer = SecretSanitizer()
    fake_token = "ghp_faketestsupersecrettoken999888777"
    raw = f"GITHUB_PAT = '{fake_token}'"
    
    sanitized, findings = sanitizer.sanitize(raw, file_path="auth.py")
    assert fake_token not in sanitized
    
    # Assert secret was never printed in logs
    for record in caplog.records:
        assert fake_token not in record.message


def test_23_project_manifest_integration(temp_project):
    manifest = ProjectManifest(
        project_id="p_crm",
        project_name="CRM Portal",
        description="Lead tracker",
        repository_path=str(temp_project),
        current_phase=PhaseEnum.PHASE_3_ARCHITECTURE,
        feature_scope={"must_have": ["Lead intake", "CSV export"]},
    )
    manifest.record_decision("Architecture", "Postgres storage", "ACID compliance")
    
    builder = ProjectContextBuilder()
    task = TaskItem(task_id="t_crm", milestone_id="m1", title="Architecture check", description="inspect arch")
    pkg = builder.build_context(manifest, task)
    
    assert pkg.current_phase == "PHASE_3_ARCHITECTURE"
    assert any("Lead intake" in s for s in pkg.srs_excerpts)
    assert any("Postgres storage" in d.get("decision", "") for d in pkg.prior_decisions)


def test_24_worker_registry_integration(temp_project):
    builder = ProjectContextBuilder()
    task = TaskItem(task_id="t_reg", milestone_id="m1", title="Code review", description="review calculator")
    manifest = ProjectManifest(project_id="p1", project_name="T", description="T", repository_path=str(temp_project))
    
    # Pass worker spec directly
    spec = WorkerSpec(
        worker_id="worker_coding_agent",
        name="Coding Agent",
        worker_type=WorkerType.NATIVE,
        capabilities=["code_review"],
        transport="INTERNAL_CALL",
    )
    pkg = builder.build_context(manifest, task, worker=spec)
    assert pkg.security_level == "PROJECT_INTERNAL"


def test_mandatory_secret_leak_regression(temp_project, caplog):
    """MANDATORY SECRET LEAK REGRESSION TEST:
    Asserts that NONE of the original synthetic secrets appear in:
    ProjectContextPackage, logs, sanitization report, serialized output, or WorkerResult.
    """
    caplog.set_level(logging.DEBUG)
    builder = ProjectContextBuilder()
    
    fake_secrets = [
        "sk-proj-faketestsecretkey1234567890abcdef",
        "ghp_faketestgithubtoken1234567890abcdef",
        "123456789:ABCdefGhIJKlmNoPQRstuVWXyz12345",
        "fake_password_123",
        "fake_super_secret_password_here",
        "fake_generic_secret_key_value",
    ]
    
    task = TaskItem(
        task_id="t_leak_test",
        milestone_id="m_sec",
        title="Check auth service",
        description="review auth credentials",
    )
    manifest = ProjectManifest(
        project_id="p_sec",
        project_name="Security Test Repo",
        description="Audit",
        repository_path=str(temp_project),
    )
    
    pkg = builder.build_context(
        manifest,
        task,
        target_files=["src/auth_service.py", "src/database_service.py"],
    )
    
    # 1. Check ProjectContextPackage relevant_files
    for filepath, content in pkg.relevant_files.items():
        for secret in fake_secrets:
            assert secret not in content, f"Secret leaked in file {filepath}: {secret}"

    # 2. Check sanitization report
    report_str = json.dumps(pkg.sanitization_report)
    for secret in fake_secrets:
        assert secret not in report_str, f"Secret leaked in sanitization report: {secret}"

    # 3. Check serialized package
    serialized = json.dumps(pkg.to_dict())
    for secret in fake_secrets:
        assert secret not in serialized, f"Secret leaked in serialized context package: {secret}"

    # 4. Check logs
    for record in caplog.records:
        for secret in fake_secrets:
            assert secret not in record.message, f"Secret leaked in logging: {secret}"

    # 5. Check WorkerResult after processing package with CodingAgentWorker
    worker = CodingAgentWorker()
    result = worker.run_task(pkg)
    result_str = json.dumps(result.to_dict())
    for secret in fake_secrets:
        assert secret not in result_str, f"Secret leaked in WorkerResult: {secret}"
