"""Session conversation memory for multi-turn interactions (Milestone M7)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class Message:
    """Represents a single conversational turn."""
    role: str  # 'user', 'assistant', 'system', 'tool'
    content: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SessionMemory:
    """Manages short-term conversation state for a specific session."""

    def __init__(self, session_id: str, max_messages: int = 50):
        self.session_id = session_id
        self.max_messages = max_messages
        self._messages: List[Message] = []

    def add_message(
        self,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Message:
        """Appends a new message turn to the session."""
        msg = Message(
            role=role,
            content=content,
            metadata=metadata or {},
        )
        self._messages.append(msg)
        if len(self._messages) > self.max_messages:
            # Drop oldest messages beyond max_messages
            self._messages = self._messages[-self.max_messages:]
        return msg

    def get_messages(self, limit: Optional[int] = None) -> List[Message]:
        """Returns messages up to the requested limit."""
        if limit is None or limit >= len(self._messages):
            return list(self._messages)
        return list(self._messages[-limit:])

    def get_formatted_history(self, limit: Optional[int] = None) -> str:
        """Returns readable history string formatted for LLM prompts."""
        msgs = self.get_messages(limit=limit)
        lines = []
        for m in msgs:
            lines.append(f"{m.role.capitalize()}: {m.content}")
        return "\n".join(lines)

    def clear(self) -> None:
        """Clears all session messages."""
        self._messages.clear()

    def count(self) -> int:
        return len(self._messages)

    def to_json(self) -> str:
        """Serializes session messages to JSON string."""
        return json.dumps([m.to_dict() for m in self._messages], indent=2)

    def load_json(self, json_str: str) -> None:
        """Loads session messages from a JSON string."""
        data = json.loads(json_str)
        self._messages = [
            Message(
                role=item["role"],
                content=item["content"],
                timestamp=item.get("timestamp", datetime.now(timezone.utc).isoformat()),
                metadata=item.get("metadata", {}),
            )
            for item in data
        ]
