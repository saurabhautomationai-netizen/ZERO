"""Engineering Project Store for ZERO.

Handles filesystem JSON persistence and in-memory indexing of all project manifests.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from zero_core.engineering.manifest import ProjectManifest

logger = logging.getLogger("zero.engineering.store")

DEFAULT_STORAGE_DIR = Path(__file__).resolve().parent.parent / "data" / "engineering_projects"


class EngineeringProjectStore:
    """Stores and retrieves persistent ProjectManifest instances."""

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or DEFAULT_STORAGE_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, ProjectManifest] = {}
        self.reload()

    def reload(self) -> None:
        """Loads all JSON manifests from the storage directory into memory cache."""
        self._cache.clear()
        for manifest_file in self.storage_dir.glob("*.json"):
            try:
                data = json.loads(manifest_file.read_text(encoding="utf-8"))
                manifest = ProjectManifest.model_validate(data)
                self._cache[manifest.project_id] = manifest
            except Exception as exc:
                logger.warning("Failed to load project manifest from %s: %s", manifest_file.name, exc)

    def save_project(self, manifest: ProjectManifest) -> None:
        """Persists a ProjectManifest to disk and updates cache."""
        self._cache[manifest.project_id] = manifest
        file_path = self.storage_dir / f"{manifest.project_id}.json"
        
        # Write atomic JSON
        file_path.write_text(
            manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )
        logger.info("Saved project manifest: %s (%s)", manifest.project_name, manifest.project_id)

    def get_project(self, project_id: str) -> Optional[ProjectManifest]:
        """Retrieves a ProjectManifest by project_id."""
        if project_id in self._cache:
            return self._cache[project_id]
        
        file_path = self.storage_dir / f"{project_id}.json"
        if file_path.exists():
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                manifest = ProjectManifest.model_validate(data)
                self._cache[manifest.project_id] = manifest
                return manifest
            except Exception as exc:
                logger.error("Failed to read project manifest %s: %s", project_id, exc)
        return None

    def find_by_name(self, name_or_query: str) -> Optional[ProjectManifest]:
        """Finds a project manifest by exact name, slug match, or token overlap."""
        if not name_or_query:
            return None
            
        q = name_or_query.lower().strip(" .?!:;\"'")
        
        # 1. Exact match
        for p in self._cache.values():
            if q == p.project_id.lower() or q == p.project_name.lower():
                return p
                
        # 2. Substring match
        for p in self._cache.values():
            if q in p.project_name.lower() or q in p.project_id.lower() or p.project_name.lower() in q:
                return p

        # 3. Clean token overlap (strip noise words)
        noise = {"the", "project", "assistant", "a", "an", "for", "with", "status", "of"}
        q_tokens = {w for w in q.replace("_", " ").replace("-", " ").split() if w not in noise}
        
        if q_tokens:
            best_match = None
            best_overlap = 0
            for p in self._cache.values():
                p_tokens = {w for w in p.project_name.lower().replace("_", " ").replace("-", " ").split() if w not in noise}
                overlap = len(q_tokens & p_tokens)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_match = p
            if best_match and best_overlap > 0:
                return best_match

        return None

    def list_projects(self) -> List[ProjectManifest]:
        """Returns all registered project manifests."""
        return list(self._cache.values())

    def delete_project(self, project_id: str) -> bool:
        """Deletes a project manifest from disk and cache."""
        if project_id in self._cache:
            del self._cache[project_id]
        
        file_path = self.storage_dir / f"{project_id}.json"
        if file_path.exists():
            try:
                file_path.unlink()
                return True
            except Exception as exc:
                logger.error("Failed to delete manifest %s: %s", project_id, exc)
                return False
        return False


DEFAULT_PROJECT_STORE = EngineeringProjectStore()
