"""Shared fixtures.

We test AgencyAgentsAdapter against a *synthetic* fake clone (a couple of
temp .md files with valid/invalid frontmatter) rather than the real
Agency-agents repo. This keeps the test suite self-contained — it should
pass on any machine, with or without the real clone checked out next to
Zero/ — while still exercising the exact parsing rules
(scripts/lint-agents.sh's frontmatter contract) that the real repo enforces.
"""

from __future__ import annotations

import pytest


VALID_AGENT = """---
name: Fake Backend Architect
description: API design, database architecture, scalability.
color: blue
---

# Fake Backend Architect Agent

Body content is irrelevant to indexing/search, only frontmatter + filename matter here.
"""

VALID_AGENT_2 = """---
name: Fake Financial Analyst
description: Financial modeling, forecasting, scenario analysis.
color: green
---

# Fake Financial Analyst Agent
"""

MALFORMED_AGENT = """This file has no frontmatter at all and should be skipped, not crash the indexer.
"""


@pytest.fixture
def fake_agency_root(tmp_path):
    """Build a minimal fake clone: engineering/ + finance/ divisions."""
    (tmp_path / "engineering").mkdir()
    (tmp_path / "finance").mkdir()

    (tmp_path / "engineering" / "engineering-fake-backend-architect.md").write_text(
        VALID_AGENT, encoding="utf-8"
    )
    (tmp_path / "engineering" / "engineering-malformed.md").write_text(
        MALFORMED_AGENT, encoding="utf-8"
    )
    (tmp_path / "finance" / "finance-fake-financial-analyst.md").write_text(
        VALID_AGENT_2, encoding="utf-8"
    )
    return tmp_path
