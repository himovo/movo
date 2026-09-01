from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Mapping


def has_browser_result(artifacts: Mapping[str, Any] | None) -> bool:
    return any(True for _ in iter_browser_results(artifacts))


def build_browser_answer_context(artifacts: Mapping[str, Any] | None) -> Dict[str, list[Dict[str, Any]]]:
    control_facts: list[Dict[str, Any]] = []
    business_evidence: list[Dict[str, Any]] = []
    terminal_results: list[Dict[str, Any]] = []
    for node_id, result in iter_browser_results(artifacts):
        operation = result.get("operation") if isinstance(result.get("operation"), dict) else {}
        fact = {
            "type": "browser_result",
            "node_id": node_id,
            "kind": str(result.get("kind") or "observation"),
            "status": str(result.get("status") or "unknown"),
            "objective": _compact(result.get("objective"), 1200),
            "summary": _compact(result.get("summary"), 1600),
        }
        if operation:
            fact["operation"] = {
                key: _compact(operation.get(key), 1600)
                for key in (
                    "status", "action_name", "operation_family", "entity", "confidence",
                    "reason", "fingerprint", "verification_boundary",
                )
                if operation.get(key) not in (None, "", [], {})
            }
            fact["verification_boundary"] = _compact(result.get("verification_boundary"), 1000)
        control_facts.append(fact)

        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        evidence = {
            "node_id": node_id,
            "role": "browser_observation" if not operation else "browser_operation_evidence",
            "data": _compact(data, 5000),
        }
        if operation:
            evidence["evidence"] = _compact(operation.get("evidence"), 4000)
        business_evidence.append(evidence)
        terminal_results.append({"node_id": node_id, "kind": "browser_result", "result": _compact(result, 6000)})
    return {
        "control_facts": control_facts,
        "business_evidence": business_evidence,
        "terminal_results": terminal_results,
    }


def iter_browser_results(
    artifacts: Mapping[str, Any] | None,
) -> Iterable[tuple[str, Dict[str, Any]]]:
    for node_id, artifact in dict(artifacts or {}).items():
        if not isinstance(artifact, dict):
            continue
        result = artifact.get("browser_result")
        if isinstance(result, dict) and result:
            yield str(node_id or "").strip(), dict(result)


def _compact(value: Any, limit: int) -> Any:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "...[truncated]"
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    return value if len(text) <= limit else text[:limit] + "...[truncated]"

