# ADR-002: Agency-agents Live Filesystem Index

**Status**: Accepted  
**Date**: 2026-08-16  
**Deciders**: ZERO Core Team  

---

## Context
`Agency-agents` contains 269 specialist persona markdown files organized across 17 functional divisions. These personas receive continuous updates and additions from the open-source community. ZERO needs to expose these specialists to the user and route appropriate analytical tasks to them.

## Problem
How should ZERO ingest and maintain access to the external `Agency-agents` personas without introducing data duplication, file sync lag, or operational maintenance overhead?

## Decision
[`AgencyAgentsAdapter`](file:///f:/AI%20Automation/Projects/Zero/zero_core/agent_registry.py) indexes the local `Agency-agents` filesystem directly at runtime. It scans the division directories on disk, parses YAML-like frontmatter metadata on demand, and caches the resulting `AgentSpec` objects in memory. A force-refresh method (`index(force=True)`) allows instant cache invalidation.

## Why We Made the Decision
1. **Always Current**: Pulling upstream changes in `Agency-agents` (`git pull`) immediately updates ZERO's specialist index without requiring code changes, database migrations, or export scripts.
2. **Zero Redundancy**: Persona markdown files remain in their primary repository. ZERO does not duplicate or store duplicate copies of 269 markdown files.
3. **Graceful Enrichment**: The adapter loads live existence from disk while enriching persona descriptions with "when to use" guidance using the bundled snapshot ([`agency_agents_inventory.json`](file:///f:/AI%20Automation/Projects/Zero/zero_core/data/agency_agents_inventory.json)).

## Alternatives Considered
- **Copy/Mirror markdown files into ZERO repo**: Rejected because mirroring guarantees stale documentation, git history bloat, and manual synchronization toil.
- **Background Cron / Database Sync**: Rejected as unnecessarily complex for local personal execution where filesystem read latency is $< 500\text{ ms}$.

## Consequences
- **Positive**: Zero data duplication; dynamic discovery of newly added agents; lightweight indexing.
- **Negative**: Requires the `Agency-agents` folder to be present on the local machine (addressed via synthetic directory fixtures in unit tests).
