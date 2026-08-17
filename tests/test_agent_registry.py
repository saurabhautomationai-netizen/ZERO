from __future__ import annotations

from pathlib import Path

from zero_core.agent_registry import AgencyAgentsAdapter, AgentRegistry
from zero_core.native_agents import ALL_NATIVE_AGENTS


def _adapter(fake_agency_root: Path) -> AgencyAgentsAdapter:
    return AgencyAgentsAdapter(
        root=fake_agency_root,
        divisions=["engineering", "finance"],
        inventory_snapshot=Path("/nonexistent"),  # force no snapshot enrichment
    )


def test_index_finds_only_valid_frontmatter_files(fake_agency_root):
    adapter = _adapter(fake_agency_root)
    specs = adapter.index()

    names = {s.name for s in specs}
    assert names == {"Fake Backend Architect", "Fake Financial Analyst"}
    # the malformed file must not appear, and must not have raised
    assert len(specs) == 2


def test_index_is_cached_until_forced(fake_agency_root):
    adapter = _adapter(fake_agency_root)
    first = adapter.index()

    # add a new file after first index; cached call should NOT see it
    (fake_agency_root / "finance" / "finance-new.md").write_text(
        "---\nname: New Agent\ndescription: x\ncolor: red\n---\nbody", encoding="utf-8"
    )
    assert adapter.index() == first
    assert len(adapter.index(force=True)) == 3


def test_by_division(fake_agency_root):
    adapter = _adapter(fake_agency_root)
    finance_specs = adapter.by_division("finance")
    assert len(finance_specs) == 1
    assert finance_specs[0].name == "Fake Financial Analyst"


def test_search_matches_description(fake_agency_root):
    adapter = _adapter(fake_agency_root)
    hits = adapter.search("forecasting")
    assert len(hits) == 1
    assert hits[0].name == "Fake Financial Analyst"


def test_get_by_slug(fake_agency_root):
    adapter = _adapter(fake_agency_root)
    spec = adapter.get("engineering/engineering-fake-backend-architect")
    assert spec is not None
    assert spec.name == "Fake Backend Architect"
    assert adapter.get("nonexistent/slug") is None


def test_load_persona_returns_full_markdown(fake_agency_root):
    adapter = _adapter(fake_agency_root)
    spec = adapter.get("finance/finance-fake-financial-analyst")
    content = adapter.load_persona(spec)
    assert "Fake Financial Analyst Agent" in content


def test_missing_root_degrades_to_empty_index(tmp_path):
    adapter = AgencyAgentsAdapter(root=tmp_path / "does-not-exist", divisions=["engineering"])
    assert adapter.index() == []


def test_registry_prefers_native_agent_for_finance_keyword(fake_agency_root):
    adapter = _adapter(fake_agency_root)
    registry = AgentRegistry(agency_adapter=adapter, native_agents=ALL_NATIVE_AGENTS)

    match = registry.resolve("What did I spend on subscriptions last month?")
    assert match.best is not None
    assert match.best.source == "native"
    assert match.best.slug == "native/finance-agent"


def test_registry_falls_back_to_agency_specialist(fake_agency_root):
    adapter = _adapter(fake_agency_root)
    registry = AgentRegistry(agency_adapter=adapter, native_agents=ALL_NATIVE_AGENTS)

    match = registry.resolve("I need help with database architecture scalability")
    assert match.best is not None
    assert match.best.source == "agency"
    assert match.best.name == "Fake Backend Architect"


def test_resolve_does_not_match_substring_inside_a_different_word(tmp_path):
    """Regression test for a real bug found on the full 269-agent index:
    plain substring search matched "design" inside "designing" and
    surfaced an Academic persona for an unrelated "design a threat model"
    task. Token-based scoring must not repeat that mistake, and must still
    correctly rank a genuinely relevant agent above it.
    """
    (tmp_path / "academic").mkdir()
    (tmp_path / "academic" / "academic-trap.md").write_text(
        "---\nname: Trap Agent\ndescription: Narrative theory.\ncolor: purple\n---\n"
        "Designing culturally coherent societies with internal logic.",
        encoding="utf-8",
    )
    (tmp_path / "security").mkdir()
    (tmp_path / "security" / "security-architect.md").write_text(
        "---\nname: Security Architect\ndescription: Threat modeling, secure-by-design, trust boundaries.\ncolor: red\n---\n"
        "System security models, architecture reviews.",
        encoding="utf-8",
    )

    adapter = AgencyAgentsAdapter(
        root=tmp_path, divisions=["academic", "security"], inventory_snapshot=Path("/nonexistent")
    )
    registry = AgentRegistry(agency_adapter=adapter, native_agents=[])

    match = registry.resolve("Design a threat model for the new API")
    names = [c.name for c in match.candidates]

    assert "Trap Agent" not in names, "substring 'design' inside 'Designing' must not match"
    assert match.best is not None
    assert match.best.name == "Security Architect"


def test_registry_get_checks_both_populations(fake_agency_root):
    adapter = _adapter(fake_agency_root)
    registry = AgentRegistry(agency_adapter=adapter, native_agents=ALL_NATIVE_AGENTS)

    assert registry.get("native/trading-agent") is not None
    assert registry.get("finance/finance-fake-financial-analyst") is not None
    assert registry.get("does/not-exist") is None
