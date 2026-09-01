"""Single deterministic metrics core exposed through the DSH adapter."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from .record_calculations import compute_record_rows, field_reference, is_record_scoped


class MetricsEngine:
    @staticmethod
    def _field_variants(name: str) -> list[str]:
        raw = str(name or "").strip()
        if not raw:
            return []
        variants = [raw]
        if "_" in raw:
            parts = [part for part in raw.split("_") if part]
            if parts:
                variants.append(parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:]))
        else:
            variants.append(re.sub(r"(?<!^)(?=[A-Z])", "_", raw).lower())
        return list(dict.fromkeys(item for item in variants if item))

    @classmethod
    def get_path(cls, value: Any, path: str) -> Any:
        current = value
        for raw_part in [part for part in str(path or "").strip().split(".") if part]:
            if current is None:
                return None
            match = re.fullmatch(r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)(?:\[(?P<index>\d+)\])?", raw_part)
            if match:
                if not isinstance(current, dict):
                    return None
                found = next((key for key in cls._field_variants(match.group("key")) if key in current), None)
                if found is None:
                    return None
                current = current[found]
                if match.group("index") is not None:
                    index = int(match.group("index"))
                    if not isinstance(current, list) or not 0 <= index < len(current):
                        return None
                    current = current[index]
            elif isinstance(current, dict):
                current = current.get(raw_part)
            else:
                return None
        return current

    @staticmethod
    def _to_number(value: Any) -> float | None:
        if isinstance(value, bool) or value in ("", None):
            return None
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            return float(value)
        if isinstance(value, str):
            text = value.strip().replace(",", "").replace("%", "")
            try:
                number = float(text)
                return number / 100.0 if "%" in value else number
            except Exception:
                return None
        return None

    @classmethod
    def _numeric_values(cls, items: list[Any], field: str) -> list[float]:
        return [number for item in items if (number := cls._to_number(cls.get_path(item, field))) is not None]

    @classmethod
    def _matches_condition(cls, item: Any, condition: dict[str, Any]) -> bool:
        field = str(condition.get("field") or condition.get("path") or "").strip()
        op = str(condition.get("op") or condition.get("operator") or "eq").strip().lower()
        target = condition.get("value")
        actual = cls.get_path(item, field) if field else item
        actual_num, target_num = cls._to_number(actual), cls._to_number(target)
        if op in {"lt", "<"}: return actual_num is not None and target_num is not None and actual_num < target_num
        if op in {"lte", "<="}: return actual_num is not None and target_num is not None and actual_num <= target_num
        if op in {"gt", ">"}: return actual_num is not None and target_num is not None and actual_num > target_num
        if op in {"gte", ">="}: return actual_num is not None and target_num is not None and actual_num >= target_num
        if op in {"ne", "!=", "not_eq"}: return str(actual) != str(target)
        if op == "contains": return str(target or "") in str(actual or "")
        return str(actual) == str(target)

    @staticmethod
    def _condition(calculation: dict[str, Any]) -> dict[str, Any]:
        if isinstance(calculation.get("condition"), dict):
            return dict(calculation["condition"])
        for key in ("lt", "lte", "gt", "gte", "eq", "ne"):
            if key in calculation:
                return {"field": calculation.get("field"), "op": key, "value": calculation.get(key)}
        return {
            "field": calculation.get("field"),
            "op": calculation.get("operator") or calculation.get("condition_op") or calculation.get("compare") or "eq",
            "value": calculation.get("value"),
        }

    @classmethod
    def _basic_stats(cls, payload: dict[str, Any], source: Any) -> dict[str, Any]:
        text = json.dumps(payload, ensure_ascii=False, default=str)
        evidence_count = 0
        for key in ("results", "confirmed_facts", "source_material", "research_bundle", "tool_results"):
            value = payload.get(key)
            if isinstance(value, list):
                evidence_count += len(value)
            elif isinstance(value, dict) and isinstance(value.get("results"), list):
                evidence_count += len(value["results"])
        return {
            "record_count": len(source) if isinstance(source, list) else (1 if source not in (None, {}) else 0),
            "url_count": len(re.findall(r"https?://[^\s\"'<>）)]+", text)),
            "image_count": len(re.findall(r"\.(?:png|jpe?g|webp|gif|svg)(?:\?|#|\"|'|\s|$)", text, re.I)),
            "evidence_count": evidence_count,
        }

    @classmethod
    def _value_ref(cls, ref: Any, metrics: dict[str, Any], item: Any = None) -> Any:
        if isinstance(ref, (int, float)):
            return ref
        field = field_reference(ref)
        if field:
            return cls.get_path(item, field) if item is not None else None
        text = str(ref or "").strip()
        if text in metrics:
            return metrics[text]
        return cls.get_path(item, text) if item is not None and text else ref

    @classmethod
    def _compute_one(cls, calculation: dict[str, Any], source: Any, metrics: dict[str, Any]) -> tuple[str, Any, dict[str, Any] | None]:
        name = str(calculation.get("name") or calculation.get("key") or calculation.get("label") or "").strip()
        if not name:
            return "", None, {"reason": "missing_metric_name", "calculation": calculation}
        op = str(calculation.get("type") or calculation.get("op") or calculation.get("operation") or "").strip().lower()
        items = source if isinstance(source, list) else ([] if source in (None, {}) else [source])
        try:
            if op == "count": return name, len(items), None
            if op in {"sum", "avg", "min", "max"}:
                field = str(calculation.get("field") or "").strip()
                if not field: return name, None, {"reason": "missing_field", "calculation": calculation}
                values = cls._numeric_values(items, field)
                if not values: return name, None, {"reason": "no_numeric_values", "field": field}
                return name, {"sum": sum(values), "avg": sum(values) / len(values), "min": min(values), "max": max(values)}[op], None
            if op in {"count_where", "share_where"}:
                count = len([item for item in items if cls._matches_condition(item, cls._condition(calculation))])
                if op == "count_where": return name, count, None
                return name, (count / len(items) if items else None), (None if items else {"reason": "zero_denominator"})
            if op == "ratio":
                left = cls._to_number(cls._value_ref(calculation.get("numerator"), metrics))
                right = cls._to_number(cls._value_ref(calculation.get("denominator"), metrics))
                return (name, left / right, None) if left is not None and right not in (None, 0) else (name, None, {"reason": "invalid_ratio_operands", "calculation": calculation})
            if op == "subtract":
                left = cls._to_number(cls._value_ref(calculation.get("left"), metrics))
                right = cls._to_number(cls._value_ref(calculation.get("right"), metrics))
                return (name, left - right, None) if left is not None and right is not None else (name, None, {"reason": "invalid_subtract_operands", "calculation": calculation})
            if op == "rank":
                field = str(calculation.get("field") or "").strip()
                ranked = [{"item": item, "value": value} for item in items if (value := cls._to_number(cls.get_path(item, field))) is not None]
                ranked.sort(key=lambda row: row["value"], reverse=str(calculation.get("order") or "desc").lower() != "asc")
                limit = int(calculation.get("limit") or min(len(items), 20) or 20)
                return name, ranked[:limit], None
            return name, None, {"reason": "unsupported_operation", "op": op}
        except Exception as exc:
            return name, None, {"reason": "calculation_error", "error": str(exc), "calculation": calculation}

    @classmethod
    def compute(cls, arguments: dict[str, Any]) -> dict[str, Any]:
        records = list(arguments.get("records") or [])
        payload = dict(arguments.get("payload") or {"records": records})
        metrics = cls._basic_stats(payload, records)
        uncomputed: list[dict[str, Any]] = []
        calculations = [dict(item) for item in list(arguments.get("calculations") or []) if isinstance(item, dict)]
        record_scoped = [item for item in calculations if is_record_scoped(item)]
        for calculation in [item for item in calculations if not is_record_scoped(item)]:
            source = calculation.pop("__records", records)
            name, value, error = cls._compute_one(calculation, source, metrics)
            if name and error is None: metrics[name] = value
            elif name: uncomputed.append({"name": name, **dict(error or {})})
            elif error: uncomputed.append(error)
        per_item: dict[str, list[dict[str, Any]]] = {}
        explicit_per_item = [
            dict(item) for item in list(arguments.get("per_item_calculations") or []) if isinstance(item, dict)
        ]
        for calculation in [*record_scoped, *explicit_per_item]:
            name = str(calculation.get("name") or calculation.get("key") or calculation.get("label") or "").strip()
            op = str(calculation.get("type") or calculation.get("op") or calculation.get("operation") or "").lower()
            if not name:
                uncomputed.append({"reason": "missing_metric_name", "calculation": calculation})
                continue
            if op == "rank":
                field = str(calculation.get("field") or "").strip()
                ranked = [
                    (index, item, value)
                    for index, item in enumerate(records)
                    if (value := cls._to_number(cls.get_path(item, field))) is not None
                ]
                ranked.sort(key=lambda row: row[2], reverse=str(calculation.get("order") or "desc").lower() != "asc")
                ranks = {index: rank for rank, (index, _item, _value) in enumerate(ranked, 1)}
                per_item[name] = [
                    {"index": index, "source_item": item, name: ranks.get(index)}
                    for index, item in enumerate(records)
                ]
                continue
            if op not in {"subtract", "ratio"}:
                uncomputed.append({"name": name, "reason": "unsupported_per_item_operation", "op": op})
                continue
            per_item[name] = compute_record_rows(
                calculation,
                records,
                resolve=lambda ref, item: cls._value_ref(ref, {}, item),
                to_number=cls._to_number,
            )
        return {
            "success": True,
            "computed_metrics": metrics,
            "per_item_metrics": per_item,
            "uncomputed_metrics": uncomputed,
            "metric_table": {"metrics": metrics, "per_item_metrics": per_item, "uncomputed_metrics": uncomputed},
        }
