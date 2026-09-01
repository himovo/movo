from __future__ import annotations

from app.services.presentation.contracts import FreeformBlock, FreeformPageBlueprint, PageBrief


def build_content_safe_page(page_brief: PageBrief) -> FreeformPageBlueprint:
    """Build a deterministic, editable page when repeated LLM layout attempts fail.

    This is deliberately small and content-preserving. It prevents one malformed
    page response from aborting an otherwise completed deck and causing the outer
    agent to regenerate every preceding page.
    """

    title = _first_text(page_brief.key_takeaway, page_brief.page_goal, page_brief.source_outline_section)
    subtitle = _first_distinct(
        title,
        page_brief.page_goal,
        page_brief.source_outline_section,
        page_brief.narrative_role,
    )
    details = _unique_texts(
        *list(page_brief.must_include or []),
        *list(page_brief.must_visualize or []),
    )
    if not details:
        details = [text for text in (subtitle, title) if text]

    blocks = [
        FreeformBlock(
            id="recovery_background",
            type="rectangle",
            role="background",
            x=0.0,
            y=0.0,
            w=1.0,
            h=1.0,
            z_index=0,
            style={"fill": "#F6F8FC", "stroke": "transparent"},
        ),
        FreeformBlock(
            id="recovery_accent",
            type="rectangle",
            role="decoration",
            x=0.0,
            y=0.0,
            w=0.025,
            h=1.0,
            z_index=1,
            style={"fill": "#2563EB", "stroke": "transparent"},
        ),
        FreeformBlock(
            id="recovery_title",
            type="text_box",
            role="title",
            x=0.07,
            y=0.08,
            w=0.86,
            h=0.14,
            content=title or "本页核心结论",
            z_index=5,
            style={"font_size": 34, "font_weight": 700, "color": "#0F172A", "text_align": "left"},
        ),
    ]
    if subtitle:
        blocks.append(
            FreeformBlock(
                id="recovery_subtitle",
                type="text_box",
                role="subtitle",
                x=0.07,
                y=0.235,
                w=0.86,
                h=0.09,
                content=subtitle,
                z_index=5,
                style={"font_size": 20, "font_weight": 400, "color": "#475569", "text_align": "left"},
            )
        )

    body = "\n".join(f"• {item}" for item in details[:6])
    blocks.extend(
        [
            FreeformBlock(
                id="recovery_panel",
                type="rectangle",
                role="surface",
                x=0.07,
                y=0.37,
                w=0.86,
                h=0.48,
                z_index=2,
                style={"fill": "#FFFFFF", "stroke": "#D7E0EE", "border_radius": 16},
            ),
            FreeformBlock(
                id="recovery_body",
                type="text_box",
                role="body",
                container_id="recovery_panel",
                x=0.11,
                y=0.43,
                w=0.78,
                h=0.36,
                content=body,
                z_index=5,
                style={"font_size": 22, "font_weight": 400, "color": "#1E293B", "text_align": "left"},
            ),
        ]
    )
    return FreeformPageBlueprint(
        page_id=str(page_brief.page_id or "").strip() or "recovered_page",
        page_title=title,
        page_subtitle=subtitle,
        layout_type="dominant_panel",
        design_intent="content_safe_recovery_after_repeated_layout_failure",
        blocks=blocks,
    )


def _first_text(*values: str) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _first_distinct(primary: str, *values: str) -> str:
    for value in values:
        text = str(value or "").strip()
        if text and text != primary:
            return text
    return ""


def _unique_texts(*values: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


__all__ = ["build_content_safe_page"]
