import ast
import logging
from pathlib import Path


_RESERVED_LOG_RECORD_FIELDS = frozenset(
    logging.makeLogRecord({}).__dict__
) | {"message", "asctime"}


def test_browser_executor_structured_log_extra_avoids_reserved_fields() -> None:
    source_path = (
        Path(__file__).parents[3]
        / "app/enterprise_capabilities/browser/engine/desktop_agent_executor.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    conflicts: list[tuple[int, str]] = []

    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        extra = next((item.value for item in call.keywords if item.arg == "extra"), None)
        if not isinstance(extra, ast.Dict):
            continue
        for key in extra.keys:
            if isinstance(key, ast.Constant) and key.value in _RESERVED_LOG_RECORD_FIELDS:
                conflicts.append((key.lineno, str(key.value)))

    assert conflicts == []
