"""Tests for Polyglot Validation Architecture (Phase 7).

Verifies validation for:
- Python AST syntax checking
- SQL schema / migration validation
- JSON and n8n workflow graph integrity
- Web script brace / bracket balance (JS/TS/CSS/HTML)
"""

import pytest
from pathlib import Path
from zero_core.engineering.polyglot_validators import (
    PythonASTValidator,
    SQLValidator,
    JSONWorkflowValidator,
    WebScriptValidator,
    PolyglotValidationRegistry,
    DEFAULT_POLYGLOT_REGISTRY,
)


def test_python_ast_validator(tmp_path):
    validator = PythonASTValidator()

    # Valid Python
    valid_file = tmp_path / "valid.py"
    valid_file.write_text("def hello(name: str) -> str:\n    return f'Hello, {name}'\n", encoding="utf-8")
    ok, errs = validator.validate_file(valid_file)
    assert ok is True
    assert len(errs) == 0

    # Invalid Python
    invalid_file = tmp_path / "invalid.py"
    invalid_file.write_text("def broken(x):\n    return x + \n", encoding="utf-8")
    ok, errs = validator.validate_file(invalid_file)
    assert ok is False
    assert len(errs) > 0
    assert any("syntax error" in e.lower() for e in errs)


def test_sql_validator(tmp_path):
    validator = SQLValidator()

    # Valid SQL
    valid_sql = tmp_path / "migration.sql"
    valid_sql.write_text(
        "CREATE TABLE IF NOT EXISTS candidates (id UUID PRIMARY KEY, name TEXT NOT NULL);\n"
        "DROP TABLE IF EXISTS old_table;\n",
        encoding="utf-8",
    )
    ok, errs = validator.validate_file(valid_sql)
    assert ok is True
    assert len(errs) == 0

    # Dangerous raw drop without IF EXISTS
    dangerous_sql = tmp_path / "danger.sql"
    dangerous_sql.write_text("DROP TABLE production_candidates;\n", encoding="utf-8")
    ok, errs = validator.validate_file(dangerous_sql)
    assert ok is False
    assert any("dangerous raw drop" in e.lower() for e in errs)

    # Unbalanced parenthesis
    unbalanced_sql = tmp_path / "unbalanced.sql"
    unbalanced_sql.write_text("CREATE TABLE test (id INT, name TEXT;\n", encoding="utf-8")
    ok, errs = validator.validate_file(unbalanced_sql)
    assert ok is False
    assert any("unbalanced parentheses" in e.lower() for e in errs)


def test_json_workflow_validator(tmp_path):
    validator = JSONWorkflowValidator()

    # Valid n8n workflow
    valid_wf = tmp_path / "n8n_flow.json"
    valid_wf.write_text(
        '{"name": "HR Ingest", "nodes": [{"id": "1", "type": "webhook"}], "connections": {"1": {}}}',
        encoding="utf-8",
    )
    ok, errs = validator.validate_file(valid_wf)
    assert ok is True

    # Invalid JSON syntax
    broken_json = tmp_path / "broken.json"
    broken_json.write_text('{"name": "broken", "nodes": [}', encoding="utf-8")
    ok, errs = validator.validate_file(broken_json)
    assert ok is False
    assert any("invalid json" in e.lower() for e in errs)

    # Invalid n8n nodes format
    bad_nodes = tmp_path / "bad_nodes.json"
    bad_nodes.write_text('{"nodes": "not-a-list"}', encoding="utf-8")
    ok, errs = validator.validate_file(bad_nodes)
    assert ok is False
    assert any("must be a list" in e for e in errs)


def test_web_script_validator(tmp_path):
    validator = WebScriptValidator()

    # Valid JS / CSS
    valid_js = tmp_path / "component.js"
    valid_js.write_text("function render() { const arr = [1, 2, 3]; return arr; }", encoding="utf-8")
    ok, errs = validator.validate_file(valid_js)
    assert ok is True

    # Mismatched braces
    broken_js = tmp_path / "broken.js"
    broken_js.write_text("function bad() { const x = 1;", encoding="utf-8")
    ok, errs = validator.validate_file(broken_js)
    assert ok is False
    assert any("curly braces" in e.lower() for e in errs)


def test_polyglot_registry_multi_file_validation(tmp_path):
    f1 = tmp_path / "model.py"
    f1.write_text("x = 1\n", encoding="utf-8")

    f2 = tmp_path / "schema.sql"
    f2.write_text("SELECT * FROM users;\n", encoding="utf-8")

    f3 = tmp_path / "config.json"
    f3.write_text('{"status": "active"}\n', encoding="utf-8")

    ok, errors = DEFAULT_POLYGLOT_REGISTRY.validate_files([f1, f2, f3])
    assert ok is True
    assert len(errors) == 0
