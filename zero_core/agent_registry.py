"""Agent Registry + Agency-agents Adapter.

This is the piece your architecture review called out as the actual thing
to build: "an Agent Registry / Agency-agents Adapter... ZERO can ask 'which
specialist can help with this?' and the registry can answer."

Two agent populations feed the registry:

  1. ZERO-native agents   (zero_core.native_agents)  — your Finance/Trading/
     Email/Calendar agents, defined and owned inside THIS repo.
  2. Agency-agents specialists — read-only, indexed live from the sibling
     clone at config.AGENCY_AGENTS_PATH. ZERO never copies or embeds those
     files; it reads them at query time so the adapter always reflects
     whatever is actually on disk in that clone.

Why frontmatter parsing is hand-rolled instead of using PyYAML: the
frontmatter block in these files is a flat `key: value` list (see
scripts/lint-agents.sh in Agency-agents — it requires exactly name/
description/color), so a tiny line-based parser is enough and keeps this
module dependency-free. If the frontmatter ever grows nested structures,
swap this for `yaml.safe_load`.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from zero_core import config

logger = logging.getLogger("zero_core.agent_registry")

# Words too common to carry routing signal. Deliberately short — Phase 1
# scoring is exact-token overlap, not stemming, so over-filtering costs more
# than it saves (see AgentRegistry.resolve docstring for why this is
# intentionally simple).
_STOPWORDS = {
    "this", "that", "with", "from", "into", "your", "need", "want", "have",
    "what", "when", "where", "which", "about", "help", "please", "does",
    "will", "should", "could", "would", "there", "their",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentSpec:
    """A single addressable specialist, native or from Agency-agents."""

    name: str
    slug: str
    source: str            # "agency" | "native"
    division: str
    description: str = ""
    when_to_use: str = ""
    color: Optional[str] = None
    path: Optional[Path] = None   # absolute path to the .md persona file (agency only)
    keywords: tuple[str, ...] = ()  # native agents only: cheap Phase-1 routing hints


@dataclass
class RegistryMatch:
    task: str
    candidates: list[AgentSpec] = field(default_factory=list)

    @property
    def best(self) -> Optional[AgentSpec]:
        return self.candidates[0] if self.candidates else None


# ---------------------------------------------------------------------------
# Agency-agents adapter
# ---------------------------------------------------------------------------

def _slugify(division: str, filename: str) -> str:
    return f"{division}/{Path(filename).stem}"


def _parse_frontmatter(text: str) -> Optional[dict]:
    """Parse the `---\\nkey: value\\n---` block required by lint-agents.sh.

    Returns None if the file doesn't open with a frontmatter block (mirrors
    the ERROR case in the source repo's own linter) rather than raising —
    a single malformed file should never take down indexing of the other
    268.
    """
    if not text.startswith("---"):
        return None
    lines = text.split("\n")
    fm_lines: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        fm_lines.append(line)
    else:
        return None  # no closing '---' found

    data: dict = {}
    for line in fm_lines:
        if not line.strip() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        data[key.strip()] = value.strip()
    return data


class AgencyAgentsAdapter:
    """Read-only index over a local Agency-agents-style clone."""

    def __init__(
        self,
        root: Path = config.AGENCY_AGENTS_PATH,
        divisions: list[str] = None,
        inventory_snapshot: Path = config.AGENCY_AGENTS_INVENTORY_SNAPSHOT,
    ):
        self.root = Path(root)
        self.divisions = divisions or config.AGENCY_AGENTS_DIVISIONS
        self._snapshot = self._load_snapshot(inventory_snapshot)
        self._index: Optional[list[AgentSpec]] = None

    @staticmethod
    def _load_snapshot(path: Path) -> dict:
        """Load the bundled when-to-use enrichment data, keyed by path."""
        if not path.exists():
            return {}
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load inventory snapshot %s: %s", path, exc)
            return {}
        return {row["path"]: row for row in rows}

    def index(self, force: bool = False) -> list[AgentSpec]:
        """Scan the clone on disk and return every valid AgentSpec found.

        Cached after first call; pass force=True to re-scan (e.g. after
        `git pull` on the Agency-agents clone).
        """
        if self._index is not None and not force:
            return self._index

        if not self.root.exists():
            logger.warning(
                "Agency-agents path %s does not exist — registry will only "
                "serve ZERO-native agents until this is fixed (check "
                "AGENCY_AGENTS_PATH).",
                self.root,
            )
            self._index = []
            return self._index

        specs: list[AgentSpec] = []
        for division in self.divisions:
            div_dir = self.root / division
            if not div_dir.is_dir():
                continue
            for md_file in sorted(div_dir.rglob("*.md")):
                spec = self._parse_agent_file(division, md_file)
                if spec is not None:
                    specs.append(spec)

        self._index = specs
        logger.info("Indexed %d Agency-agents specialists from %s", len(specs), self.root)
        return specs

    def _parse_agent_file(self, division: str, md_file: Path) -> Optional[AgentSpec]:
        try:
            text = md_file.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not read %s: %s", md_file, exc)
            return None

        frontmatter = _parse_frontmatter(text)
        if frontmatter is None or "name" not in frontmatter:
            logger.debug("Skipping %s — missing/invalid frontmatter", md_file)
            return None

        rel_path = md_file.relative_to(self.root).as_posix()
        snapshot_row = self._snapshot.get(rel_path, {})

        return AgentSpec(
            name=frontmatter.get("name", md_file.stem),
            slug=_slugify(division, md_file.name),
            source="agency",
            division=division,
            description=frontmatter.get("description", snapshot_row.get("specialty", "")),
            when_to_use=snapshot_row.get("when", ""),
            color=frontmatter.get("color"),
            path=md_file,
        )

    def search(self, keyword: str) -> list[AgentSpec]:
        """Case-insensitive substring match across name/description/when/division."""
        kw = keyword.lower()
        return [
            s for s in self.index()
            if kw in s.name.lower()
            or kw in s.description.lower()
            or kw in s.when_to_use.lower()
            or kw in s.division.lower()
        ]

    def by_division(self, division: str) -> list[AgentSpec]:
        return [s for s in self.index() if s.division == division]

    def get(self, slug: str) -> Optional[AgentSpec]:
        return next((s for s in self.index() if s.slug == slug), None)

    def load_persona(self, spec: AgentSpec) -> str:
        """Return the full persona markdown (the actual system-prompt body).

        This is what you'd inject when ZERO decides to literally "become"
        that specialist for a task, as opposed to just knowing it exists.
        """
        if spec.source != "agency" or spec.path is None:
            raise ValueError(f"{spec.slug} is not an Agency-agents persona")
        return spec.path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Unified registry (native + agency)
# ---------------------------------------------------------------------------

class AgentRegistry:
    """The single thing ZERO's Orchestrator talks to.

    Phase 1 routing is deliberately simple keyword matching — good enough to
    prove the registry contract end-to-end. Swap `resolve()`'s internals for
    embedding-based routing against Memory/RAG in Phase 2 without touching
    any caller.
    """

    def __init__(self, agency_adapter: AgencyAgentsAdapter, native_agents: list[AgentSpec]):
        self.agency = agency_adapter
        self._native = {a.slug: a for a in native_agents}

    def list_native(self) -> list[AgentSpec]:
        return list(self._native.values())

    def list_agency(self, division: Optional[str] = None) -> list[AgentSpec]:
        return self.agency.by_division(division) if division else self.agency.index()

    def get(self, slug: str) -> Optional[AgentSpec]:
        return self._native.get(slug) or self.agency.get(slug)

    def resolve(self, task: str, top_k: int = 3) -> RegistryMatch:
        """Explicit @agent mentions get top absolute priority, followed by native
        agents for domain keywords, and Agency-agents specialists for deep tasks."""
        clean_task = task.strip(" \"'")
        # 1. Direct explicit mention check (@Agent Name: or @slug: or @A, @B, and @C:)
        mention_match = re.match(r"^@([^:]+?):", clean_task)
        if mention_match:
            raw_str = mention_match.group(1)
            targets = [t.strip().lstrip("@").strip().lower() for t in re.split(r"[,&]|\band\b", raw_str) if t.strip()]
            for target in targets:
                for spec in list(self._native.values()) + list(self.agency.index()):
                    if (
                        spec.name.lower() == target
                        or spec.slug.lower() == target
                        or spec.slug.split("/")[-1].lower() == target.replace(" ", "-")
                    ):
                        return RegistryMatch(task=clean_task, candidates=[spec])

        task_lower = task.lower()
        native_candidates: list[tuple[int, int, AgentSpec]] = []

        engineering_directives = (
            "continue development", "continue my", "continue the project", "continue project",
            "resume development", "resume project", "resume the",
            "inspect project", "inspect the existing", "read-only discovery", "discovery mode",
            "recover project state", "recover its last checkpoint", "recover last checkpoint",
            "continuation hitl gate", "hitl gate", "engineering lifecycle",
            "build me a complete", "build a complete", "create a new saas",
            "approve feature scope", "approve ui/ux", "approve security", "approve deployment",
            "engineering cockpit", "engineering status"
        )
        is_engineering_task = any(d in task_lower for d in engineering_directives)

        for native in self._native.values():
            matched_kws = [k for k in native.keywords if k in task_lower]
            if matched_kws:
                score = len(matched_kws)
                max_len = max(len(k) for k in matched_kws)
                # If an explicit engineering lifecycle directive is present, strongly prioritize Loop Engineering Agent
                if is_engineering_task and native.slug == "native/loop-engineering-agent":
                    score += 100
                native_candidates.append((score, max_len, native))
            elif is_engineering_task and native.slug == "native/loop-engineering-agent":
                # Ensure Loop Engineering Agent is included even if individual keywords had slightly different phrasing
                native_candidates.append((100, 20, native))

        # Sort by match count, then longest matched keyword phrase descending
        native_candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        candidates: list[AgentSpec] = [spec for _, _, spec in native_candidates]

        remaining = top_k - len(candidates)
        if remaining > 0:
            task_tokens = {w for w in _tokenize(task) if w not in _STOPWORDS and len(w) >= 3}
            scored: list[tuple[int, AgentSpec]] = []
            for spec in self.agency.index():
                spec_tokens = _tokenize(
                    f"{spec.name} {spec.description} {spec.when_to_use} {spec.division}"
                )
                score = len(task_tokens & spec_tokens)
                if score > 0:
                    scored.append((score, spec))
            scored.sort(key=lambda pair: pair[0], reverse=True)
            candidates.extend(spec for _, spec in scored[:remaining])

        return RegistryMatch(task=task, candidates=candidates[:top_k])
