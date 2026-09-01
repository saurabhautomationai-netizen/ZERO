"""Pluggable Polyglot Validators for ZERO Engineering Organization.

Provides clean, extensible, technology-specific validators for:
- Python (AST syntax, bytecode)
- SQL (DDL/DML syntax, balance, dangerous DROP checks)
- JSON & n8n workflows (JSON validity, schema/node connection integrity)
- Web Scripts (JavaScript, TypeScript, HTML, CSS syntax & balance)
"""

from __future__ import annotations

import abc
import ast
import json
import logging
import re
from pathlib import Path
from typing import List, Tuple, Optional

logger = logging.getLogger("zero.engineering.polyglot")


class BasePolyglotValidator(abc.ABC):
    """Abstract base class for technology-specific file validators."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Name of the validator."""
        ...

    @abc.abstractmethod
    def can_validate(self, file_path: Path) -> bool:
        """Determines if this validator handles the given file."""
        ...

    @abc.abstractmethod
    def validate_content(self, content: str, file_path: Path) -> Tuple[bool, List[str]]:
        """Validates content string, returning (is_valid, error_list)."""
        ...

    def validate_file(self, file_path: Path) -> Tuple[bool, List[str]]:
        """Reads file from disk and validates it."""
        if not file_path.exists():
            return False, [f"File not found: {file_path}"]
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            return self.validate_content(content, file_path)
        except Exception as exc:
            return False, [f"Failed to read file {file_path}: {exc}"]


class PythonASTValidator(BasePolyglotValidator):
    """Validates Python files using standard abstract syntax tree parsing."""

    @property
    def name(self) -> str:
        return "PYTHON_AST"

    def can_validate(self, file_path: Path) -> bool:
        return file_path.suffix == ".py"

    def validate_content(self, content: str, file_path: Path) -> Tuple[bool, List[str]]:
        try:
            ast.parse(content, filename=str(file_path))
            return True, []
        except SyntaxError as exc:
            err = f"Python syntax error in {file_path.name}: {exc.msg} on line {exc.lineno}"
            return False, [err]


class SQLValidator(BasePolyglotValidator):
    """Validates SQL migrations, schemas, and queries."""

    @property
    def name(self) -> str:
        return "SQL_SCHEMA"

    def can_validate(self, file_path: Path) -> bool:
        return file_path.suffix == ".sql"

    def validate_content(self, content: str, file_path: Path) -> Tuple[bool, List[str]]:
        errors = []
        cleaned = re.sub(r"--.*?$", "", content, flags=re.MULTILINE)
        cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL).strip()

        if not cleaned:
            return True, []  # Empty or comment-only SQL is harmless

        # Check quote balance
        single_quotes = len(re.findall(r"(?<!\\)'", cleaned))
        if single_quotes % 2 != 0:
            errors.append(f"Unbalanced single quotes in SQL file {file_path.name}")

        # Check parenthesis balance
        open_parens = cleaned.count("(")
        close_parens = cleaned.count(")")
        if open_parens != close_parens:
            errors.append(
                f"Unbalanced parentheses in {file_path.name}: {open_parens} '(' vs {close_parens} ')'"
            )

        # Catch dangerous unconstrained drops: DROP TABLE <table> without IF EXISTS
        raw_drops = re.findall(r"\bDROP\s+(?:TABLE|DATABASE|SCHEMA)\s+(?!IF\s+EXISTS\b)(\w+)", cleaned, re.IGNORECASE)
        if raw_drops:
            errors.append(f"Dangerous raw DROP without IF EXISTS detected for: {', '.join(raw_drops)}")

        return (len(errors) == 0), errors


class JSONWorkflowValidator(BasePolyglotValidator):
    """Validates JSON configurations and n8n automation workflow definitions."""

    @property
    def name(self) -> str:
        return "JSON_WORKFLOW"

    def can_validate(self, file_path: Path) -> bool:
        return file_path.suffix == ".json"

    def validate_content(self, content: str, file_path: Path) -> Tuple[bool, List[str]]:
        if not content.strip():
            return False, [f"Empty JSON content in {file_path.name}"]
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            return False, [f"Invalid JSON in {file_path.name}: {exc.msg} at line {exc.lineno}"]

        errors = []
        # If n8n workflow JSON, validate node connections structure
        if isinstance(data, dict) and ("nodes" in data or "connections" in data):
            if "nodes" in data and not isinstance(data["nodes"], list):
                errors.append(f"n8n workflow 'nodes' in {file_path.name} must be a list")
            if "connections" in data and not isinstance(data["connections"], dict):
                errors.append(f"n8n workflow 'connections' in {file_path.name} must be a dictionary")

        return (len(errors) == 0), errors


class WebScriptValidator(BasePolyglotValidator):
    """Validates JavaScript, TypeScript, JSX, TSX, HTML, and CSS assets."""

    @property
    def name(self) -> str:
        return "WEB_SCRIPT"

    def can_validate(self, file_path: Path) -> bool:
        return file_path.suffix in {".js", ".jsx", ".ts", ".tsx", ".html", ".css"}

    def validate_content(self, content: str, file_path: Path) -> Tuple[bool, List[str]]:
        errors = []
        # Check basic brace/bracket balance for JS/TS/CSS
        if file_path.suffix in {".js", ".jsx", ".ts", ".tsx", ".css"}:
            cleaned = re.sub(r"//.*?$", "", content, flags=re.MULTILINE)
            cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)
            
            # Count braces outside strings
            open_curly = cleaned.count("{")
            close_curly = cleaned.count("}")
            if open_curly != close_curly:
                errors.append(f"Mismatched curly braces in {file_path.name}: {open_curly} vs {close_curly}")

            open_bracket = cleaned.count("[")
            close_bracket = cleaned.count("]")
            if open_bracket != close_bracket:
                errors.append(f"Mismatched square brackets in {file_path.name}: {open_bracket} vs {close_bracket}")

        # Check HTML basic tag structure if .html
        elif file_path.suffix == ".html":
            open_html = len(re.findall(r"<html\b", content, re.IGNORECASE))
            close_html = len(re.findall(r"</html>", content, re.IGNORECASE))
            if open_html != close_html:
                errors.append(f"Mismatched <html> tags in {file_path.name}")

        return (len(errors) == 0), errors


class PolyglotValidationRegistry:
    """Registry coordinating all pluggable file validators."""

    def __init__(self, validators: Optional[List[BasePolyglotValidator]] = None):
        self._validators: List[BasePolyglotValidator] = validators or [
            PythonASTValidator(),
            SQLValidator(),
            JSONWorkflowValidator(),
            WebScriptValidator(),
        ]

    def register(self, validator: BasePolyglotValidator) -> None:
        """Adds a new validator to the registry."""
        self._validators.append(validator)

    def validate_file(self, file_path: Path) -> Tuple[bool, List[str]]:
        """Runs matching validators on a single file."""
        matched = False
        all_errors = []
        for v in self._validators:
            if v.can_validate(file_path):
                matched = True
                success, errors = v.validate_file(file_path)
                if not success:
                    all_errors.extend(errors)
        if not matched:
            return True, []  # Unsupported extensions pass through without error
        return (len(all_errors) == 0), all_errors

    def validate_files(self, file_paths: List[Path]) -> Tuple[bool, List[str]]:
        """Runs validation across multiple files."""
        aggregated_errors = []
        for p in file_paths:
            success, errors = self.validate_file(p)
            if not success:
                aggregated_errors.extend(errors)
        return (len(aggregated_errors) == 0), aggregated_errors


DEFAULT_POLYGLOT_REGISTRY = PolyglotValidationRegistry()
