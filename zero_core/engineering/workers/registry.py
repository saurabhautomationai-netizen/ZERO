"""Worker Registry for ZERO Engineering Organization.

Maintains the catalog of all available engineering workers, their capabilities,
transports, risk tiers, and live health status.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from zero_core.engineering.workers.base import (
    EngineeringWorker,
    WorkerCapability,
    WorkerStatus,
    WorkerType,
)

logger = logging.getLogger("zero.engineering.workers.registry")


@dataclass
class WorkerSpec:
    """Descriptor and operational metadata for an EngineeringWorker."""
    worker_id: str
    name: str
    worker_type: WorkerType
    capabilities: List[str]
    transport: str
    availability: WorkerStatus = WorkerStatus.AVAILABLE
    risk_level: str = "LOW"
    cost_metadata: Dict[str, Any] = field(default_factory=dict)
    context_capacity: int = 128000
    config_status: str = "CONFIGURED"
    health_status: str = "HEALTHY"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WorkerRegistry:
    """Central registry managing worker instances and capabilities."""

    def __init__(self):
        self._workers: Dict[str, EngineeringWorker] = {}
        self._specs: Dict[str, WorkerSpec] = {}

    def register(
        self,
        worker: EngineeringWorker,
        spec: Optional[WorkerSpec] = None,
    ) -> None:
        """Registers an EngineeringWorker instance."""
        self._workers[worker.worker_id] = worker
        
        capabilities_str = [
            c.value if isinstance(c, WorkerCapability) else str(c)
            for c in worker.capabilities
        ]
        
        self._specs[worker.worker_id] = spec or WorkerSpec(
            worker_id=worker.worker_id,
            name=worker.name,
            worker_type=worker.worker_type,
            capabilities=capabilities_str,
            transport=worker.transport,
            availability=worker.status,
            risk_level=worker.risk_level,
        )
        logger.info("Registered engineering worker: %s (%s)", worker.name, worker.worker_id)

    def unregister(self, worker_id: str) -> Optional[EngineeringWorker]:
        """Removes a worker from the registry."""
        self._specs.pop(worker_id, None)
        return self._workers.pop(worker_id, None)

    def get(self, worker_id: str) -> Optional[EngineeringWorker]:
        """Retrieves a worker instance by worker_id."""
        return self._workers.get(worker_id)

    def get_spec(self, worker_id: str) -> Optional[WorkerSpec]:
        """Retrieves worker metadata spec by worker_id."""
        return self._specs.get(worker_id)

    def list_workers(self) -> List[EngineeringWorker]:
        """Returns all registered worker instances."""
        return list(self._workers.values())

    def list_specs(self) -> List[WorkerSpec]:
        """Returns all registered worker specs."""
        return list(self._specs.values())

    def find_by_capability(self, capability: WorkerCapability | str) -> List[EngineeringWorker]:
        """Finds all workers possessing a given capability."""
        cap_val = capability.value if isinstance(capability, WorkerCapability) else capability
        return [w for w in self._workers.values() if w.has_capability(cap_val)]

    def get_best_worker_for_task(
        self,
        required_capabilities: List[WorkerCapability | str],
        preferred_worker_id: Optional[str] = None,
    ) -> Optional[EngineeringWorker]:
        """Finds the optimal available worker satisfying the requested capabilities."""
        if preferred_worker_id and preferred_worker_id in self._workers:
            candidate = self._workers[preferred_worker_id]
            if candidate.status in (WorkerStatus.AVAILABLE, WorkerStatus.MANUAL_TRANSPORT):
                return candidate

        # Capability matching
        candidates = []
        for worker in self._workers.values():
            if worker.status not in (WorkerStatus.AVAILABLE, WorkerStatus.MANUAL_TRANSPORT):
                continue
            matched_count = sum(1 for req in required_capabilities if worker.has_capability(req))
            if matched_count > 0:
                candidates.append((matched_count, worker))

        if not candidates:
            return None

        # Sort by match score descending
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    def health_check_all(self) -> Dict[str, WorkerStatus]:
        """Executes health checks across all registered workers."""
        results = {}
        for wid, worker in self._workers.items():
            status = worker.health_check()
            results[wid] = status
            if wid in self._specs:
                self._specs[wid].availability = status
        return results


# Global singleton instance
DEFAULT_WORKER_REGISTRY = WorkerRegistry()


def bootstrap_native_workers(registry: Optional[WorkerRegistry] = None) -> WorkerRegistry:
    """Instantiates and registers native ZERO engineering workers."""
    reg = registry or DEFAULT_WORKER_REGISTRY
    from zero_core.engineering.departments.uiux import DEFAULT_UIUX_COORDINATOR
    from zero_core.engineering.workers.native import (
        CodingAgentWorker,
        ProjectBuilderWorker,
        ResearchWorker,
    )
    reg.register(ProjectBuilderWorker())
    reg.register(CodingAgentWorker())
    reg.register(ResearchWorker())
    reg.register(DEFAULT_UIUX_COORDINATOR)
    return reg


def bootstrap_external_workers(registry: Optional[WorkerRegistry] = None) -> WorkerRegistry:
    """Instantiates and registers external workers (ChatGPT, Google Antigravity)."""
    reg = registry or DEFAULT_WORKER_REGISTRY
    from zero_core.engineering.workers.external import AntigravityWorker, ChatGPTWorker
    reg.register(ChatGPTWorker())
    reg.register(AntigravityWorker())
    return reg


def bootstrap_all_workers(registry: Optional[WorkerRegistry] = None) -> WorkerRegistry:
    """Bootstraps both native and external workers into the registry."""
    reg = registry or DEFAULT_WORKER_REGISTRY
    bootstrap_native_workers(reg)
    bootstrap_external_workers(reg)
    return reg
