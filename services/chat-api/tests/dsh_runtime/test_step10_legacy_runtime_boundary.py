from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_dsh_legacy_runtime_boundary.py"
SPEC = importlib.util.spec_from_file_location("check_dsh_legacy_runtime_boundary", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _app(tmp_path: Path) -> Path:
    root = tmp_path / "app"
    root.mkdir()
    (root / "main.py").write_text("app.include_router(dsh_chat.router)\n", encoding="utf-8")
    return root


def test_clean_dsh_application_passes(tmp_path: Path) -> None:
    root = _app(tmp_path)
    (root / "feature.py").write_text("from app.dsh_runtime import application\n", encoding="utf-8")
    assert MODULE.violations(root) == []


def test_restored_legacy_root_is_rejected(tmp_path: Path) -> None:
    root = _app(tmp_path)
    (root / "runtime").mkdir()
    assert MODULE.violations(root) == ["retired path exists: app/runtime"]


def test_importing_retired_namespace_is_rejected(tmp_path: Path) -> None:
    root = _app(tmp_path)
    (root / "feature.py").write_text("from app.pipeline.planner import graph\n", encoding="utf-8")
    assert MODULE.violations(root) == [
        "feature.py:1: imports retired namespace app.pipeline.planner"
    ]


def test_legacy_chat_registration_is_rejected(tmp_path: Path) -> None:
    root = _app(tmp_path)
    (root / "main.py").write_text(
        "app.include_router(dsh_chat.router)\napp.include_router(chat.router)\n",
        encoding="utf-8",
    )
    assert MODULE.violations(root) == ["app/main.py registers the retired chat router"]
