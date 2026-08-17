"""Central configuration for ZERO Core.

Design note (why this file exists): the Agency-agents review flagged that
repo's config-driven pattern (divisions.json / tools.json as single sources
of truth, checked by CI) as worth copying. This module is ZERO's equivalent
single source of truth for "where things live" — no path should be
hardcoded anywhere else in zero_core.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Filesystem layout
# ---------------------------------------------------------------------------

# Root of the ZERO project (…/Projects/Zero)
ZERO_ROOT = Path(__file__).resolve().parent.parent


def load_env(env_path: Optional[Path] = None) -> None:
    """Lightweight .env parser that loads variables without third-party dependencies."""
    target = env_path or (ZERO_ROOT / ".env")
    if not target.is_file():
        return
    try:
        content = target.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            # Strip enclosing quotes if present
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            if k and k not in os.environ:
                os.environ[k] = v
    except OSError:
        pass


# Auto-load .env on import if available
load_env()

# Root of the *sibling* Agency-agents clone (…/Projects/Agency-agents).
# Overridable via env var so tests / other machines don't need the same
# folder layout. Default assumes Zero and Agency-agents are siblings under
# the same Projects/ directory, which matches your current disk layout.
AGENCY_AGENTS_PATH = Path(
    os.environ.get("AGENCY_AGENTS_PATH", str(ZERO_ROOT.parent / "Agency-agents"))
)

# Bundled snapshot of the Agency-agents roster (name/specialty/when-to-use),
# generated from the local clone's README on 2026-08-16. This enriches the
# live frontmatter scan with "when to use" text that individual agent files
# don't carry themselves (only the README roster table has it). The live
# filesystem scan is always the source of truth for *existence*; this file
# is only used to backfill descriptive text when available.
AGENCY_AGENTS_INVENTORY_SNAPSHOT = (
    Path(__file__).resolve().parent / "data" / "agency_agents_inventory.json"
)

# Divisions considered part of the specialist catalog (mirrors the source
# repo's divisions.json). Kept here — not imported from the Agency-agents
# repo — so ZERO doesn't break if you re-clone or update that dependency.
AGENCY_AGENTS_DIVISIONS = [
    "academic", "design", "engineering", "finance", "game-development",
    "gis", "healthcare", "marketing", "paid-media", "product",
    "project-management", "sales", "security", "spatial-computing",
    "specialized", "support", "testing",
]

# Read-only Postgres connection string for the Finance Tracker's
# `transactions`/`users` tables (see zero_core/finance_status.py). Must be a
# dedicated read-only role — never the same credentials the n8n workflow
# uses to write. Unset by default; FinanceStatusAdapter raises a clear
# error rather than silently returning empty data when this is missing.
FINANCE_DB_URL = os.environ.get("FINANCE_DB_URL")

# Sibling projects ZERO's native agents wrap rather than reimplement.
# These are real, independent projects on disk — ZERO calls into them,
# it does not absorb their code.
TRADING_BOT_PATH = ZERO_ROOT.parent / "Trading bot"
FINANCE_TRACKER_PATH = ZERO_ROOT.parent / "Smart Finance AI Tracker" / "Personal Finance Tracker"
DATA_DIR = ZERO_ROOT / "zero_core" / "data"

SIBLING_PROJECTS = {
    "trading_bot": TRADING_BOT_PATH,
    "personal_finance_tracker": FINANCE_TRACKER_PATH,
}
