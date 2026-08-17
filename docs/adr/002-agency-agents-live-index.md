# ADR-002: Agency-agents Indexed Live at Query Time (No Copy)

**Date**: 2026-08-16  
**Status**: Accepted  
**Deciders**: ZERO Core Team  

---

## Context

Agency-agents is a separate repository (269 markdown files with YAML frontmatter) that receives upstream updates. ZERO needs to route tasks to these specialists.

## Decision

**`AgencyAgentsAdapter` reads the local Agency-agents clone at query time** — it walks the filesystem, parses frontmatter, and builds an in-memory index. The index is cached after first scan; `index(force=True)` forces a re-scan (e.g., after `git pull`).

No files are copied, embedded, or snapshotted into ZERO's codebase. The only bundled artifact is `data/agency_agents_inventory.json` — a README-derived snapshot of "when to use" descriptions for enrichment only.

## Consequences

### Positive
- **Always current** — `git pull` in Agency-agents → `registry.agency.index(force=True)` → new agents immediately available
- **Zero sync logic** — no background jobs, no change detection, no drift
- **Minimal coupling** — ZERO only depends on filesystem layout and frontmatter contract

### Negative
- **Cold-start latency** — first request scans 269 files (~200-500ms)
- **No offline mode** — requires Agency-agents clone on disk (mitigated: tests use synthetic fixture)

## Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| Copy/mirror agents into ZERO repo | Drift guarantee; 269 files to maintain |
| Periodic background sync | Added complexity (scheduler, change detection) for no benefit |
| Embed as git submodule | Still needs indexing; doesn't solve "live read" requirement |

## Implementation Notes
- `AgencyAgentsAdapter.index()` — scans divisions from `config.AGENCY_AGENTS_DIVISIONS`
- `_parse_frontmatter()` — hand-rolled line parser (flat `key: value`, no nested YAML)
- `inventory_snapshot` — enriches with "when to use" from bundled JSON (optional)

## References
- `zero_core/agent_registry.py:AgencyAgentsAdapter`
- `zero_core/config.py:AGENCY_AGENTS_PATH`, `AGENCY_AGENTS_DIVISIONS`
- `ARCHITECTURE.md` — "Key Architectural Decisions #2"