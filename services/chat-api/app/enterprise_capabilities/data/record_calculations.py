"""Record-scoped arithmetic accepted by the DSH metrics contract."""

from __future__ import annotations

from typing import Any, Callable


def field_reference(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("field") or value.get("path") or "").strip()
    return ""


def is_record_scoped(calculation: dict[str, Any]) -> bool:
    op = str(calculation.get("type") or calculation.get("op") or "").lower()
    refs = (
        (calculation.get("left"), calculation.get("right"))
        if op == "subtract"
        else (calculation.get("numerator"), calculation.get("denominator"))
    )
    return op in {"subtract", "ratio"} and any(field_reference(ref) for ref in refs)


def compute_record_rows(
    calculation: dict[str, Any],
    records: list[Any],
    *,
    resolve: Callable[[Any, Any], Any],
    to_number: Callable[[Any], float | None],
) -> list[dict[str, Any]]:
    name = str(calculation.get("name") or calculation.get("key") or calculation.get("label") or "").strip()
    op = str(calculation.get("type") or calculation.get("op") or "").lower()
    left_key, right_key = ("left", "right") if op == "subtract" else ("numerator", "denominator")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(records):
        left = to_number(resolve(calculation.get(left_key), item))
        right = to_number(resolve(calculation.get(right_key), item))
        error = ""
        value: float | None = None
        if left is None or right is None:
            error = f"invalid_{op}_operands"
        elif op == "ratio" and right == 0:
            error = "zero_denominator"
        else:
            value = left - right if op == "subtract" else left / right
        row = {"index": index, "source_item": item, name: value}
        if error:
            row["_calculation_error"] = error
        rows.append(row)
    return rows
