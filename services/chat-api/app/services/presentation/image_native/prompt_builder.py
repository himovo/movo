from __future__ import annotations

import json
from typing import Any, Dict, List

from app.services.presentation.contracts import DeckBrief, PageBrief
from app.services.presentation.image_native.page_copy import source_texts_from_page


IMAGE_ONLY_GUARDRAILS = (
    "Image-only finished-slide constraints: render the entire final 16:9 presentation "
    "page as one coherent image, including all supplied text and visuals. Use a restrained, "
    "professional editorial presentation style with purposeful whitespace and one dominant "
    "visual idea. Use no more than four supporting information groups. Avoid neon glow, "
    "sci-fi HUD styling, glassmorphism, excessive gradients, decorative circuitry, dense "
    "dashboard grids, ornamental clutter, and oversized empty panels. Never draw blank "
    "placeholder cards or fake/pseudo text."
)


def constrain_full_slide_prompt(prompt: str, *, final_texts: List[Dict[str, Any]] | None = None) -> str:
    raw = str(prompt or "").strip()
    copy_payload = [
        {"role": str(item.get("role") or "body"), "text": str(item.get("text") or "").strip()}
        for item in list(final_texts or [])
        if str(item.get("text") or "").strip()
    ]
    copy_rules = (
        "Render every text value in FINAL COPY exactly once, verbatim and fully legible. "
        "The role fields are layout metadata and must not be printed. "
        "Do not translate, paraphrase, shorten, duplicate, or invent any wording, names, "
        "figures, labels, citations, or dates. Integrate the typography into the artwork; "
        "there will be no later text overlay or reconstruction.\n"
        f"FINAL COPY:\n{json.dumps(copy_payload, ensure_ascii=False)}"
    )
    return "\n\n".join(part for part in (raw, IMAGE_ONLY_GUARDRAILS, copy_rules) if part)


def build_page_plan_prompt(
    *,
    deck_brief: DeckBrief,
    page_brief: PageBrief,
    deck_creative_brief: str,
    page_creative_brief: str,
    theme_reference: str = "",
) -> str:
    page_type = str(page_brief.page_type or "").strip().lower()
    payload = {
        "deck_creative_brief": deck_creative_brief,
        "page_creative_brief": page_creative_brief,
        "theme_reference": theme_reference,
        "source_content": source_texts_from_page(page_brief),
    }
    cover_rules = ""
    if page_type == "cover":
        cover_rules = (
            "- Cover pages have a strict low-density content budget: one main title, one short subtitle or time range, and at most one small metadata tag.\n"
            "- Do NOT turn cover into an agenda, roadmap, timeline, process page, comparison page, dashboard, or body-content slide.\n"
            "- Do NOT render stage nodes, step bars, multi-card grids, charts, KPI modules, or explanatory paragraphs on cover.\n"
            "- If upstream hints mention phases, structure, outline, or evolution path, compress them into abstract hero cues only, not explicit content modules.\n"
        )
    return (
        "You are the image-native presentation art director.\n"
        "Return strict JSON matching ImageNativePagePlan.\n"
        "Your job is to design the prompt contract for the configured image model, which will create a COMPLETE 16:9 PPT page visual.\n"
        "The generated image is the visual source of truth for composition, hierarchy, visual rhythm, and illustration style.\n"
        "Source content is already grounded upstream. Turn it into concise final slide copy without changing facts.\n\n"
        "Rules:\n"
        "- The full_slide_prompt must ask for a publication-ready, restrained business PPT page, not a background-only image.\n"
        "- planned_texts is the exact audience-facing copy that the image model must render into the final image.\n"
        "- Keep planned_texts concise: title plus at most five supporting items and no more than 260 characters total.\n"
        "- Do not expose page_goal, visual_intent, design instructions, or presenter notes as slide copy.\n"
        "- Do not invent facts, company names, numbers, labels, or claims outside source_content and the page brief.\n"
        "- Default to restrained professional editorial design, not a futuristic dashboard or decorative technology poster.\n"
        "- Use one dominant visual idea and no more than four supporting information groups.\n"
        "- Never request blank placeholders or reserve areas for later reconstruction; the image is the final deliverable.\n"
        "- Cover and closing pages may use one integrated hero visual with low text density.\n"
        f"{cover_rules}"
        "- full_slide_prompt should be concise enough for image generation but specific about composition, style, colors, and content hierarchy.\n\n"
        "Output JSON shape:\n"
        "{"
        "\"page_id\":\"\", \"page_index\":1, \"page_type\":\"cover|agenda|content|thank_you\","
        "\"page_goal\":\"\", \"key_takeaway\":\"\", \"visual_intent\":\"\", \"composition_intent\":\"\","
        "\"planned_texts\":[{\"id\":\"title\",\"role\":\"title\",\"text\":\"\",\"priority\":10}],"
        "\"planned_data\":[],"
        "\"full_slide_prompt\":\"\","
        "\"visual_must_haves\":[\"\"],"
        "\"delivery_notes\":[\"\"]"
        "}\n\n"
        f"Deck/page payload:\n{json.dumps(payload, ensure_ascii=False)}"
    )
