from __future__ import annotations

from zero_core.agents.coding_agent import (
    DEFAULT_CODING_AGENT,
    CodeAnalysisResult,
    CodingAgent,
)
from zero_core.executors import execute
from zero_core.native_agents import CODING_AGENT


def test_coding_agent_analyze_python_code():
    agent = CodingAgent()
    sample_code = (
        "import os\n"
        "import sys\n\n"
        "class Calculator:\n"
        "    def add(self, a: int, b: int) -> int:\n"
        "        return a + b\n\n"
        "def main():\n"
        "    calc = Calculator()\n"
        "    print(calc.add(2, 3))\n"
    )

    res = agent.analyze_python_code("sample.py", sample_code)
    assert res.file_path == "sample.py"
    assert res.class_count == 1
    assert res.function_count == 2  # add + main
    assert res.import_count == 2
    assert len(res.detected_smells) == 0


def test_coding_agent_syntax_error_handling():
    agent = CodingAgent()
    invalid_code = "def bad_syntax(:"
    res = agent.analyze_python_code("bad.py", invalid_code)
    assert len(res.detected_smells) > 0
    assert "SyntaxError" in res.detected_smells[0]


def test_coding_agent_generate_unified_diff():
    agent = CodingAgent()
    orig = "def compute():\n    return 10\n"
    refactored = "def compute():\n    # optimized\n    return 20\n"
    diff = agent.generate_unified_diff("compute.py", orig, refactored)
    assert "--- a/compute.py" in diff
    assert "+++ b/compute.py" in diff
    assert "+    return 20" in diff


def test_coding_agent_executor_dispatch():
    res = execute(spec=CODING_AGENT, task="Review Orchestrator Architecture")
    assert res.spec.slug == "native/coding-agent"
    assert res.needs_llm is False
    assert "Coding Agent Overview" in res.answer
