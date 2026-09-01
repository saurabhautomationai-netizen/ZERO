"""Worker abstraction and adapters package for ZERO Engineering Organization."""

from zero_core.engineering.workers.base import (
    EngineeringWorker,
    ProjectContextPackage,
    WorkerCapability,
    WorkerResult,
    WorkerStatus,
    WorkerType,
)
from zero_core.engineering.workers.external import (
    AntigravityWorker,
    ChatGPTWorker,
    ExternalEngineeringWorker,
)
from zero_core.engineering.workers.registry import (
    DEFAULT_WORKER_REGISTRY,
    WorkerRegistry,
    WorkerSpec,
    bootstrap_native_workers,
)
from zero_core.engineering.workers.transport import (
    ManualTaskPackage,
    ManualTransportManager,
    TransportConfig,
    TransportType,
)

__all__ = [
    "EngineeringWorker",
    "ProjectContextPackage",
    "WorkerCapability",
    "WorkerResult",
    "WorkerStatus",
    "WorkerType",
    "ExternalEngineeringWorker",
    "ChatGPTWorker",
    "AntigravityWorker",
    "TransportType",
    "TransportConfig",
    "ManualTaskPackage",
    "ManualTransportManager",
    "WorkerRegistry",
    "WorkerSpec",
    "DEFAULT_WORKER_REGISTRY",
    "bootstrap_native_workers",
]
