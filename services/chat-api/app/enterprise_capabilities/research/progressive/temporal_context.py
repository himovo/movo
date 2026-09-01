from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


DEFAULT_RESEARCH_TIMEZONE = "Asia/Shanghai"


@dataclass(frozen=True)
class ResearchTemporalContext:
    current_date: str
    current_year: int
    freshness_days: int
    timezone: str


def build_research_temporal_context(
    *,
    freshness_days: int = 30,
    timezone_name: str = DEFAULT_RESEARCH_TIMEZONE,
    now: datetime | None = None,
) -> ResearchTemporalContext:
    zone = ZoneInfo(timezone_name)
    current = now or datetime.now(zone)
    if current.tzinfo is None:
        current = current.replace(tzinfo=zone)
    else:
        current = current.astimezone(zone)
    bounded_days = max(1, min(3650, int(freshness_days or 30)))
    return ResearchTemporalContext(
        current_date=current.date().isoformat(),
        current_year=current.year,
        freshness_days=bounded_days,
        timezone=timezone_name,
    )


def resolve_research_freshness_days(output_spec: dict[str, Any] | None, *, default: int = 30) -> int:
    spec = output_spec if isinstance(output_spec, dict) else {}
    research_contract = spec.get("research_contract") if isinstance(spec.get("research_contract"), dict) else {}
    effective_policy = spec.get("effective_policy") if isinstance(spec.get("effective_policy"), dict) else {}
    research_policy = (
        effective_policy.get("research_policy")
        if isinstance(effective_policy.get("research_policy"), dict)
        else {}
    )
    raw_value = research_contract.get("freshness_days") or research_policy.get("freshness_days") or default
    try:
        return max(1, min(3650, int(raw_value)))
    except (TypeError, ValueError):
        return max(1, min(3650, int(default)))


def query_planning_temporal_guidance(context: ResearchTemporalContext) -> str:
    return (
        f"Current date: {context.current_date} ({context.timezone}).\n"
        f"Current year: {context.current_year}. Freshness target: within the latest "
        f"{context.freshness_days} days when the topic is time-sensitive.\n"
        "For requests involving latest, current, recent, trends, prices, policies, products, "
        "market conditions, or other changing facts, prioritize current-year and recent sources. "
        "Include at least one query containing the current year. Do not rely only on the previous "
        "year or on model memory. Older sources may be searched only for durable background or "
        "explicit historical comparison."
    )


def evidence_judging_temporal_guidance(context: ResearchTemporalContext) -> str:
    return (
        f"Current date: {context.current_date} ({context.timezone}); current year: "
        f"{context.current_year}; freshness target: {context.freshness_days} days.\n"
        "Judge evidence on relevance, source reliability, and temporal freshness. For claims that "
        "change over time, prefer current-year or freshness-window evidence. Accept older evidence "
        "only when it is authoritative and durable, or when it is explicitly used as historical "
        "background; explain that choice in rationale. Never present old evidence as the latest "
        "state. If recent evidence is insufficient, set done=false and generate follow-up queries "
        "using the current year, recent month or quarter, and authoritative sources."
    )
