"""Department Registry and catalog for ZERO Engineering Organization."""

from zero_core.engineering.departments.registry import (
    DEFAULT_DEPARTMENT_REGISTRY,
    DepartmentRegistry,
    DepartmentSpec,
)
from zero_core.engineering.departments.uiux import (
    DEFAULT_UIUX_COORDINATOR,
    UIDesignPackage,
    UIReviewFinding,
    UIReviewResult,
    UIUXDepartmentCoordinator,
)

__all__ = [
    "DEFAULT_DEPARTMENT_REGISTRY",
    "DepartmentRegistry",
    "DepartmentSpec",
    "DEFAULT_UIUX_COORDINATOR",
    "UIDesignPackage",
    "UIReviewFinding",
    "UIReviewResult",
    "UIUXDepartmentCoordinator",
]
