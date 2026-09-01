"""Project Checkpoint Engine for ZERO.

Creates and restores immutable point-in-time snapshots of project engineering state,
file hashes, and milestone progress.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from zero_core.engineering.manifest import Checkpoint, PhaseEnum, ProjectManifest

logger = logging.getLogger("zero.engineering.checkpoints")

DEFAULT_CHECKPOINT_DIR = Path(__file__).resolve().parent.parent / "data" / "checkpoints"


class CheckpointIsolationError(Exception):
    """Raised when a checkpoint's project_id does not match the requested project_id."""
    pass


class CheckpointManager:
    """Manages project checkpoint creation, persistence, and restoration."""

    def __init__(self, checkpoint_dir: Optional[Path] = None):
        self.checkpoint_dir = checkpoint_dir or DEFAULT_CHECKPOINT_DIR
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def _compute_file_hashes(self, repo_path: str) -> Dict[str, str]:
        """Calculates SHA256 hashes for all project source files instantly."""
        import os
        root = Path(repo_path)
        if not root.exists():
            return {}

        ignore_dirs = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache", ".agents", ".claude"}
        hashes = {}
        
        for dirpath, dirnames, filenames in os.walk(str(root)):
            # Prune ignored directories in-place so os.walk does NOT descend into them
            dirnames[:] = [d for d in dirnames if d not in ignore_dirs and not d.startswith(".")]
            
            for fname in filenames:
                if fname.startswith("."):
                    continue
                p = Path(dirpath) / fname
                try:
                    rel = str(p.relative_to(root))
                    # Only hash source/text files under 5MB to remain instantaneous
                    if p.stat().st_size < 5 * 1024 * 1024:
                        h = hashlib.sha256(p.read_bytes()).hexdigest()
                        hashes[rel] = h
                except Exception:
                    pass
        return hashes

    def create_checkpoint(
        self,
        manifest: ProjectManifest,
        description: str,
    ) -> Checkpoint:
        """Creates an immutable checkpoint for a project."""
        ckpt_id = f"ckpt_{uuid.uuid4().hex[:10]}"
        file_hashes = self._compute_file_hashes(manifest.repository_path)
        
        ckpt = Checkpoint(
            checkpoint_id=ckpt_id,
            project_id=manifest.project_id,
            phase=manifest.current_phase,
            milestone=manifest.current_milestone,
            description=description,
            timestamp=datetime.now(timezone.utc).isoformat(),
            manifest_snapshot=manifest.model_dump(),
            file_hashes=file_hashes,
        )

        project_dir = self.checkpoint_dir / manifest.project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        ckpt_file = project_dir / f"{ckpt_id}.json"
        
        ckpt_file.write_text(
            ckpt.model_dump_json(indent=2),
            encoding="utf-8",
        )

        manifest.last_checkpoint = ckpt_id
        manifest.last_successful_phase = manifest.current_phase
        logger.info("Created checkpoint %s for project %s (%s)", ckpt_id, manifest.project_name, description)
        return ckpt

    def get_checkpoint(self, project_id: str, checkpoint_id: str) -> Optional[Checkpoint]:
        """Retrieves a specific checkpoint snapshot with strict project isolation."""
        ckpt_file = self.checkpoint_dir / project_id / f"{checkpoint_id}.json"
        if not ckpt_file.exists():
            # Check if this checkpoint exists under any other project (cross-project probe attempt)
            for other_file in self.checkpoint_dir.glob(f"*/{checkpoint_id}.json"):
                raise CheckpointIsolationError(
                    f"CHECKPOINT_ISOLATION_ERROR: Checkpoint '{checkpoint_id}' belongs to another project "
                    f"('{other_file.parent.name}'), not requested project '{project_id}'."
                )
            return None

        try:
            data = json.loads(ckpt_file.read_text(encoding="utf-8"))
            ckpt = Checkpoint.model_validate(data)
            if ckpt.project_id != project_id:
                raise CheckpointIsolationError(
                    f"CHECKPOINT_ISOLATION_ERROR: Checkpoint '{checkpoint_id}' belongs to project "
                    f"'{ckpt.project_id}', not requested project '{project_id}'."
                )
            return ckpt
        except CheckpointIsolationError:
            raise
        except Exception as exc:
            logger.error("Failed to read checkpoint %s: %s", checkpoint_id, exc)
            return None

    def list_checkpoints(self, project_id: str) -> List[Checkpoint]:
        """Lists all checkpoints for a project sorted chronologically."""
        project_dir = self.checkpoint_dir / project_id
        if not project_dir.exists():
            return []

        checkpoints = []
        for f in project_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                checkpoints.append(Checkpoint.model_validate(data))
            except Exception:
                pass

        checkpoints.sort(key=lambda c: c.timestamp)
        return checkpoints

    def restore_manifest_from_checkpoint(
        self,
        project_id: str,
        checkpoint_id: str,
    ) -> Optional[ProjectManifest]:
        """Restores a ProjectManifest from a saved checkpoint."""
        ckpt = self.get_checkpoint(project_id, checkpoint_id)
        if not ckpt:
            return None

        manifest = ProjectManifest.model_validate(ckpt.manifest_snapshot)
        if manifest.project_id != project_id:
            raise CheckpointIsolationError(
                f"CHECKPOINT_ISOLATION_ERROR: Restored manifest has project_id '{manifest.project_id}', "
                f"expected '{project_id}'."
            )
        logger.info("Restored project %s from checkpoint %s (Phase: %s)", project_id, checkpoint_id, ckpt.phase)
        return manifest


DEFAULT_CHECKPOINT_MANAGER = CheckpointManager()
