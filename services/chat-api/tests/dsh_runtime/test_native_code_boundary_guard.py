from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_dsh_native_code_boundary.py"
SPEC = importlib.util.spec_from_file_location("check_dsh_native_code_boundary", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_clean_tree_has_no_occurrences(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "clean.py").write_text("print('native dsh')\n", encoding="utf-8")
    assert MODULE.scan_occurrences(tmp_path) == Counter()


def test_new_legacy_reference_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "bridge.py").write_text("code_task({})\n", encoding="utf-8")
    found = MODULE.scan_occurrences(tmp_path)
    assert MODULE.violations(found, Counter()) == [
        "src/bridge.py: 'code_task' occurs 1 time(s), allowed 0"
    ]


def test_allowance_is_a_counted_ceiling(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    target = source / "bridge.py"
    occurrence = MODULE.Occurrence("src/bridge.py", "code_task")
    allowance = Counter({occurrence: 1})
    target.write_text("code_task({})\n", encoding="utf-8")
    assert MODULE.violations(MODULE.scan_occurrences(tmp_path), allowance) == []
    target.write_text("code_task({})\ncode_task({})\n", encoding="utf-8")
    assert MODULE.violations(MODULE.scan_occurrences(tmp_path), allowance) == [
        "src/bridge.py: 'code_task' occurs 2 time(s), allowed 1"
    ]


def test_retired_boundary_rejects_restoring_a_baseline_allowance(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({
        "schema_version": "askai.dsh-native-code-retired.v2",
        "allowed_occurrences": [
            {"path": "src/bridge.py", "token": "code_task", "max_count": 1},
        ],
    }), encoding="utf-8")
    try:
        MODULE.load_allowance(baseline)
    except ValueError as error:
        assert "must remain empty" in str(error)
    else:
        raise AssertionError("retired boundary accepted a production allowance")
