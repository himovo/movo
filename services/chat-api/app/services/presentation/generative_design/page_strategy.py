from __future__ import annotations

from typing import List

from app.services.presentation.contracts import PageBrief
from app.services.presentation.layout_archetypes import archetype_by_id


def build_page_strategy_brief(page: PageBrief) -> str:
    assigned_id = str(page.layout_archetype_id or "").strip()
    if not assigned_id:
        raise ValueError(f"page {page.page_id} has no MOVO layout assignment")
    spec = archetype_by_id(assigned_id)
    profile = str(page.validation_profile or "").strip().lower()
    intent = str(page.composition_intent or page.visual_intent or "").strip().lower()
    guidance: List[str] = [
        f"Use archetype '{spec.archetype_id}' in family '{spec.family}' as a grammar, never as a fixed template.",
        spec.prompt_brief,
        "Required structure: " + " | ".join(spec.must_do),
        "Avoid: " + (" | ".join(spec.must_avoid) if spec.must_avoid else "generic UI composition"),
        "Budget: at most 2 primary regions, 6 supporting regions, and 10 text boxes; headline width at least 70%.",
        "Establish the semantic visual anchor before placing support copy or decoration.",
        "Keep important copy out of edge strips and narrow micro-columns; simplify before shrinking.",
    ]
    if profile in {"introduce_topic", "ask_for_decision", "close_gratitude"}:
        guidance.append("Use one hero-scale visual or statement and make every secondary element support it.")
    if profile in {"show_architecture", "show_roadmap", "process_diagram"} or any(
        token in intent for token in ("架构", "路线", "流程", "阶段", "roadmap", "architecture", "process", "timeline")
    ):
        guidance.append("Build one integrated system or path; connectors alone cannot carry the page.")
    if profile in {"frame_problem", "show_metrics", "introduce_topic"} or any(
        token in intent for token in ("矩阵", "框架", "总结", "治理", "决策", "matrix", "framework", "summary", "governance")
    ):
        guidance.append("Consolidate abstract logic into one or two strong visual regions, not detached boxes.")
    return " ".join(guidance)


__all__ = ["build_page_strategy_brief"]
