"""Read-Only Execution Policy and Guardrails for ZERO Engineering Organization.

Enforces strict prohibitions during discovery, audit, and diagnostic operations.
Prevents unintended file modifications, destructive commands, database migrations,
n8n webhook triggers, and automated HITL gate approvals.
"""

from __future__ import annotations

import enum
import logging
from typing import Optional, Set, Tuple

logger = logging.getLogger("zero.engineering.discovery.policy")


class ExecutionMode(str, enum.Enum):
    """Operational execution mode for engineering agents and workers."""
    READ_ONLY = "READ_ONLY"
    MUTATION_PERMITTED = "MUTATION_PERMITTED"
    DRY_RUN = "DRY_RUN"


class ProhibitedOperationError(PermissionError):
    """Raised when an operation violates the active execution policy."""
    def __init__(self, action: str, reason: str):
        super().__init__(f"PROHIBITED_OPERATION: '{action}' is blocked. {reason}")
        self.action = action
        self.reason = reason


# Explicitly forbidden action keywords in read-only mode
FORBIDDEN_MUTATING_ACTIONS: Set[str] = {
    "write_file",
    "edit_file",
    "replace_file",
    "delete_file",
    "remove_file",
    "rename_file",
    "mkdir",
    "create_directory",
    "execute_migration",
    "db_insert",
    "db_update",
    "db_delete",
    "db_drop",
    "db_alter",
    "git_commit",
    "git_push",
    "git_checkout_b",
    "n8n_activate",
    "n8n_deactivate",
    "n8n_save",
    "n8n_delete",
    "webhook_trigger",
    "trigger_webhook",
    "approve_gate",
    "auto_approve",
    "deploy",
}

# Explicitly permitted read-only shell commands
SAFE_READONLY_COMMANDS: Set[str] = {
    "git status",
    "git branch",
    "git log",
    "git rev-parse",
    "pytest --collect-only",
    "python --version",
}


class ReadOnlyPolicyEnforcer:
    """Enforces strict read-only constraints across workers during discovery."""

    def __init__(self, mode: ExecutionMode = ExecutionMode.READ_ONLY):
        self.mode = mode

    @property
    def is_read_only(self) -> bool:
        return self.mode == ExecutionMode.READ_ONLY

    def verify_action_allowed(self, action: str) -> None:
        """Raises ProhibitedOperationError if action mutates state in READ_ONLY mode."""
        if not self.is_read_only:
            return

        act_clean = action.strip().lower()
        if act_clean in FORBIDDEN_MUTATING_ACTIONS:
            msg = f"Cannot execute mutating action '{action}' while in {self.mode.value} mode."
            logger.warning("[POLICY_VIOLATION_BLOCKED] %s", msg)
            raise ProhibitedOperationError(action, msg)

        # Catch-all substring checks
        for forbidden in ("write", "delete", "drop", "truncate", "modify", "deploy", "commit"):
            if forbidden in act_clean and "read" not in act_clean:
                msg = f"Action '{action}' contains forbidden mutation token '{forbidden}'."
                logger.warning("[POLICY_VIOLATION_BLOCKED] %s", msg)
                raise ProhibitedOperationError(action, msg)

    def is_command_safe(self, cmd: str) -> Tuple[bool, str]:
        """Validates whether a shell command is safe to execute in READ_ONLY mode."""
        if not self.is_read_only:
            return True, "Mutation permitted"

        c_clean = cmd.strip().lower()
        for safe in SAFE_READONLY_COMMANDS:
            if c_clean.startswith(safe):
                return True, f"Command '{cmd}' is whitelisted read-only"

        # Block any destructive command tokens
        destructive_tokens = ("rm ", "del ", "rmdir", "drop", "update", "delete", "insert", "git commit", "git push", "curl -x post", "curl -x put")
        for token in destructive_tokens:
            if token in c_clean:
                return False, f"Command '{cmd}' contains destructive token '{token}'"

        return False, f"Command '{cmd}' is not in safe read-only whitelist"
