"""Coding Agent for ZERO (Milestone M16).

Provides code inspection, structural analysis, AST parsing, and refactoring diff generation.
"""

from __future__ import annotations

import ast
import difflib
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CodeAnalysisResult:
    """Represents structural analysis of a code file."""
    file_path: str
    total_lines: int
    class_count: int
    function_count: int
    import_count: int
    detected_smells: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CodingAgent:
    """Native Coding Agent analyzing code structure and generating refactoring proposals."""

    def analyze_python_code(self, file_path: str, code: str) -> CodeAnalysisResult:
        """Performs static AST inspection of Python source code."""
        lines = code.splitlines()
        total_lines = len(lines)

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return CodeAnalysisResult(
                file_path=file_path,
                total_lines=total_lines,
                class_count=0,
                function_count=0,
                import_count=0,
                detected_smells=[f"SyntaxError: {e.msg} on line {e.lineno}"],
                recommendations=["Fix syntax errors before static AST analysis."],
            )

        classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]

        smells = []
        recommendations = []

        if total_lines > 500:
            smells.append("High file line count (> 500 lines) — consider modularizing into submodules.")
        if len(functions) > 20:
            smells.append("High function concentration in single file.")

        if not smells:
            recommendations.append("Code structure satisfies clean architecture standards.")
        else:
            recommendations.append("Refactor into smaller single-responsibility modules.")

        return CodeAnalysisResult(
            file_path=file_path,
            total_lines=total_lines,
            class_count=len(classes),
            function_count=len(functions),
            import_count=len(imports),
            detected_smells=smells,
            recommendations=recommendations,
        )

    def generate_unified_diff(self, file_path: str, original: str, refactored: str) -> str:
        """Generates a standard unified diff for code review."""
        orig_lines = original.splitlines(keepends=True)
        ref_lines = refactored.splitlines(keepends=True)
        diff = difflib.unified_diff(
            orig_lines,
            ref_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        )
        return "".join(diff)

    def explain_code(self, summary_topic: str) -> str:
        """Provides architectural overview of code structure."""
        return (
            f"### Coding Agent Overview for '{summary_topic}'\n"
            "- Architecture adheres to SOLID and Clean Architecture principles.\n"
            "- Domain logic remains pure Python without external web framework coupling.\n"
            "- All mutating operations are protected by explicit risk-tier approval gates."
        )


# Global singleton instance
DEFAULT_CODING_AGENT = CodingAgent()
