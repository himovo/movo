from __future__ import annotations

from typing import Any


class SkillHubError(ValueError):
    """A stable, model-readable failure from the governed install flow."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = {
            key: value for key, value in details.items() if value is not None and value != ""
        }

    def result(self) -> dict[str, Any]:
        return {
            "success": False,
            "installed": False,
            "message": self.message,
            "error": {"code": self.code, "message": self.message, **self.details},
        }
