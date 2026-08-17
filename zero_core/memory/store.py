"""Long-term entity and user preference store for ZERO (Milestone M7)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class EntityStore:
    """Manages long-term facts, entities, user preferences, and configuration memories."""

    def __init__(self, persistence_file: Optional[Path] = None):
        self._persistence_file = persistence_file
        self._store: Dict[str, Dict[str, Any]] = {}
        if self._persistence_file and self._persistence_file.exists():
            self._load()

    def set(self, namespace: str, key: str, value: Any) -> None:
        """Sets a value under a specific memory namespace (e.g. 'user_prefs', 'trading_rules')."""
        if namespace not in self._store:
            self._store[namespace] = {}
        self._store[namespace][key] = value
        self._save()

    def get(self, namespace: str, key: str, default: Any = None) -> Any:
        """Retrieves a value by namespace and key."""
        return self._store.get(namespace, {}).get(key, default)

    def delete(self, namespace: str, key: str) -> bool:
        """Deletes a key from a namespace."""
        if namespace in self._store and key in self._store[namespace]:
            del self._store[namespace][key]
            self._save()
            return True
        return False

    def list_keys(self, namespace: str) -> List[str]:
        """Lists all keys under a given namespace."""
        return list(self._store.get(namespace, {}).keys())

    def get_namespace(self, namespace: str) -> Dict[str, Any]:
        """Returns all key-values for a namespace."""
        return dict(self._store.get(namespace, {}))

    def clear(self, namespace: Optional[str] = None) -> None:
        """Clears a specific namespace, or entire store if namespace is None."""
        if namespace is not None:
            self._store.pop(namespace, None)
        else:
            self._store.clear()
        self._save()

    def _save(self) -> None:
        if self._persistence_file:
            self._persistence_file.parent.mkdir(parents=True, exist_ok=True)
            self._persistence_file.write_text(
                json.dumps(self._store, indent=2), encoding="utf-8"
            )

    def _load(self) -> None:
        if self._persistence_file and self._persistence_file.exists():
            try:
                data = json.loads(self._persistence_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._store = data
            except Exception:
                self._store = {}
