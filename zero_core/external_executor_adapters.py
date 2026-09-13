"""Replaceable stateless CLI planners; no live execution enabled by G2A."""

from dataclasses import dataclass
import json

from zero_core.engineering_contracts import TaskPacket
from zero_core.engineering_execution import ProcessInvocation, TrustedAdapterConfiguration


@dataclass(frozen=True)
class CodexAdapter:
    configuration: TrustedAdapterConfiguration
    cli_version: str = "0.154.0"
    authentication_requirement: str = "isolated-codex-home-broker-deferred"
    executor_id: str = "codex"

    def preview(self, packet: TaskPacket) -> ProcessInvocation:
        """Flags verified against local 0.154.0 exec help; not runnable approval."""
        config = self.configuration
        if self.cli_version != "0.154.0" or self.authentication_requirement != "isolated-codex-home-broker-deferred":
            raise ValueError("unsupported version/configuration")
        if "CODEX_HOME" not in config.environment:
            raise ValueError("isolated trusted CODEX_HOME required")
        if (packet.project_id, packet.repository_root) != (config.project_id, config.repository_root):
            raise ValueError("trusted workspace mismatch")
        # No free-form context, prose, credentials or command arguments are copied
        # into prompts. Command-profile semantic enforcement is deferred.
        if any(op.action != "READ_FILE" for op in packet.operations):
            raise ValueError("only read-file planning supported")
        instructions = json.dumps({"instruction": "Read only the listed repository files. Report observations.",
                                   "files": [op.target for op in packet.operations]},
                                  ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
        return ProcessInvocation(
            argv=(config.executable, "exec", "--ignore-user-config", "--strict-config",
                  "--ephemeral", "--json", "--color", "never", "--sandbox", "read-only",
                  "-c", 'model_provider="openai"', "-C", config.repository_root, "-"),
            stdin=instructions, cwd=config.repository_root, environment=config.environment,
        )

    def plan(self, packet: TaskPacket) -> ProcessInvocation:
        self.preview(packet)
        # Local help documents JSONL, but not its versioned event grammar or
        # complete project-config/MCP/hook isolation. Never guess either.
        raise ValueError("Codex output schema and extension isolation unproven")

    def parse(self, output: str) -> bool:
        # No locally established exec-event schema is currently supported.
        raise ValueError("unsupported Codex output schema for " + self.cli_version)


@dataclass(frozen=True)
class GooseAdapter:
    configuration: TrustedAdapterConfiguration
    executor_id: str = "goose"

    def plan(self, packet: TaskPacket) -> ProcessInvocation:
        raise ValueError("goose run stdin/no-session/no-profile/isolation flags unproven")

    def parse(self, output: str) -> bool:
        raise ValueError("no locally documented Goose structured schema")
