from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest
import yaml


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_dsh_upgrade_contract.py"
SPEC = importlib.util.spec_from_file_location("check_dsh_upgrade_contract", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
MATRIX = yaml.safe_load(MODULE.MATRIX_PATH.read_text(encoding="utf-8"))


def test_repository_and_current_bundled_release_are_admitted() -> None:
    MODULE.validate_repository()


def test_candidate_missing_an_official_code_capability_is_rejected() -> None:
    candidate = copy.deepcopy(MODULE.current_candidate())
    candidate["code_capabilities"].remove("bash")
    with pytest.raises(ValueError, match="missing required code_capabilities"):
        MODULE.validate_candidate(candidate, MATRIX)


def test_candidate_protocol_drift_is_rejected_before_packaging() -> None:
    candidate = copy.deepcopy(MODULE.current_candidate())
    candidate["host_protocol"] = "askai.dsh-host.v2-unreviewed"
    with pytest.raises(ValueError, match="not admitted"):
        MODULE.validate_candidate(candidate, MATRIX)


def test_candidate_node_runtime_drift_is_rejected() -> None:
    candidate = copy.deepcopy(MODULE.current_candidate())
    candidate["node_runtime"] = ">=20"
    with pytest.raises(ValueError, match="node_runtime changed"):
        MODULE.validate_candidate(candidate, MATRIX)


def test_candidate_must_resume_an_old_persisted_session() -> None:
    candidate = copy.deepcopy(MODULE.current_candidate())
    candidate["old_session_resume_verified"] = False
    with pytest.raises(ValueError, match="old Session resume probe"):
        MODULE.validate_candidate(candidate, MATRIX)
