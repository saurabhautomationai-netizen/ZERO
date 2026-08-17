# ADR-001: Native Agents in ZERO Repository

**Status**: Accepted  
**Date**: 2026-08-16  
**Deciders**: ZERO Core Team  

---

## Context
ZERO requires domain-specific agent definitions for personal capabilities such as Personal Finance, Live Trading, Trading Coach, Email, and Calendar. These agents interact with private databases (PostgreSQL), trading systems (MT5), external mail APIs, and personalized memory stores. Simultaneously, ZERO integrates `Agency-agents` (`msitarzewski/agency-agents`), an upstream open-source catalog of 269 general-purpose specialist personas tracked as an external git clone.

## Problem
Where should ZERO's custom, personal-data-bound agent definitions reside?
If native agents are placed inside the `Agency-agents` repository (e.g., in a custom `zero/` division), pulling upstream changes from `origin/main` risks merge conflicts. Furthermore, developers risk accidentally pushing private configurations, personalized prompts, or personal data schema bindings to a public fork.

## Decision
Native agent personas are defined directly within the ZERO repository under [`zero_core/native_agents.py`](file:///f:/AI%20Automation/Projects/Zero/zero_core/native_agents.py). They are represented as `AgentSpec` instances with `division="zero-native"` and `source="native"`.

## Why We Made the Decision
1. **Repository & Upstream Isolation**: Keeps the external `Agency-agents` clone completely unmodified, allowing seamless `git pull` updates without merge collisions or drift.
2. **Security & Privacy**: Ensures private schemas, internal database column names, and integration details are stored strictly inside the private ZERO repository.
3. **Architectural Ownership**: Allows ZERO to evolve its agent specification data model (adding fields such as `approval_required`, `tools`, and `memory_namespace`) without constraint from the upstream Agency-agents schema.

## Alternatives Considered
- **Scaffold a `zero/` division inside the Agency-agents fork**: Rejected due to merge conflict risks and potential data leakage during upstream synchronizations.
- **Symlink or Git Submodule integration**: Rejected because native agents require runtime integration notes, Python callables, and private configuration bindings that pure markdown files cannot provide.

## Consequences
- **Positive**: Clean separation of concerns; safe upstream pulling; full schema control.
- **Negative**: Native agent definitions mirror the structural attributes of `AgentSpec` without sharing frontmatter validation linters from the Agency-agents repository.
