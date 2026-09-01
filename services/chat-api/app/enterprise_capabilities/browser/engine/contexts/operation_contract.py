"""Authoritative execution boundary for one coarse browser capability.

The DSH tool argument selects the operation.  Natural-language objectives may
refine the evidence needed to complete that operation, but must never promote a
read/navigation call into a business mutation or demote a write operation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Set

from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask


_READ_ONLY = frozenset({"navigate", "read"})
_WRITES = frozenset({"submit", "modify", "delete", "file_transfer", "publish"})
_KNOWN = _READ_ONLY | _WRITES


@dataclass(frozen=True)
class BrowserOperationContract:
    operation: str
    capability_id: str

    @classmethod
    def from_node(cls, node: CapabilityTask) -> "BrowserOperationContract":
        raw = str((node.meta or {}).get("capability_id") or "").strip().lower()
        operation = raw.removeprefix("browser.")
        if operation == "navigate_and_extract":
            operation = "read"
        return cls(operation=operation, capability_id=raw)

    @property
    def known(self) -> bool:
        return self.operation in _KNOWN

    @property
    def read_only(self) -> bool:
        return self.operation in _READ_ONLY

    @property
    def requires_commit(self) -> bool:
        return self.operation in _WRITES

    def constrain_requirements(self, inferred: Iterable[str]) -> Set[str]:
        requirements = {str(item) for item in inferred if str(item)}
        requirements.add("navigate")
        if not self.known:
            # Legacy/untyped browser nodes retain their existing behaviour.
            return requirements
        if self.operation == "navigate":
            return {"navigate"}
        if self.read_only:
            requirements.discard("commit")
            return requirements
        requirements.add("commit")
        return requirements

    def read_only_action_blocker(
        self,
        *,
        tool: str,
        target: dict[str, Any] | None,
        search_interaction: bool,
        final_commit_control: bool,
    ) -> str:
        """Reject state-changing actions that could bypass Tool Gateway policy.

        Search fields and their submit controls remain available to read calls;
        form editing, uploads and final business controls do not.
        """
        if not self.read_only:
            return ""
        normalized = str(tool or "")
        if normalized in {"browser_upload_file", "browser_paste_image", "browser_select"}:
            return "read-only browser operation cannot change business data"
        if normalized in {"browser_fill", "browser_type_at"} and not search_interaction:
            return "read-only browser operation may fill only a confirmed search field"
        if normalized == "browser_press":
            key = str((target or {}).get("key") or "").strip().casefold()
            if key in {"enter", "return"} and not search_interaction:
                return "read-only browser operation may submit only a confirmed search query"
        if normalized in {"browser_click", "browser_click_at"} and final_commit_control:
            return "read-only browser operation cannot activate a business commit control"
        return ""


__all__ = ["BrowserOperationContract"]
