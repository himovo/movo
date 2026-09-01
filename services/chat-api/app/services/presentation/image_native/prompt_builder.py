from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from app.services.presentation.contracts import DeckBrief, PageBrief


IMAGE_RECONSTRUCTION_GUARDRAILS = (
    "Reconstruction-friendly visual constraints: avoid dense node-link diagrams, "
    "complex flowcharts, intricate geometric topology, spiderweb connectors, "
    "particle meshes, and many crossing lines. Prefer simple cards, icon rows, "
    "short timelines, clean tables, simple 2-4 step flows, and lightly illustrated "
    "modules that can be rebuilt with editable rectangles, text, icons, and a few "
    "straight lines. If a technical concept needs a diagram, use a simplified "
    "schematic with clearly separated blocks and minimal connectors."
)


def constrain_full_slide_prompt(prompt: str) -> str:
    raw = str(prompt or "").strip()
    if not raw:
        return IMAGE_RECONSTRUCTION_GUARDRAILS
    if "Reconstruction-friendly visual constraints" in raw:
        return raw
    return f"{raw}\n\n{IMAGE_RECONSTRUCTION_GUARDRAILS}"


def _looks_like_cover_time_range(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    if re.search(r"(19|20)\d{2}", raw):
        return True
    lowered = raw.lower()
    return any(token in lowered for token in ("至今", "today", "present", "now", "以来", "年代"))


def _looks_like_cover_meta(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    lowered = raw.lower().replace("：", ":")
    return any(
        token in lowered
        for token in (
            "演讲者",
            "讲者",
            "汇报人",
            "presenter",
            "speaker",
            "课堂",
            "分享",
            "内部分享",
            "seminar",
            "lecture",
        )
    )


def _is_sentence_like(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    if any(mark in raw for mark in ("。", "！", "？", ".", "!", "?")):
        return True
    return len(raw) > 24 and any(token in raw for token in ("是", "将", "通过", "帮助", "说明", "展示", "介绍"))


def _cover_known_texts(page_brief: PageBrief) -> List[Dict[str, Any]]:
    texts: List[Dict[str, Any]] = []
    title = str(page_brief.key_takeaway or "").strip()
    if title:
        texts.append({"id": "title", "role": "title", "text": title, "priority": 10})

    subtitle_candidates: List[str] = []
    for item in list(page_brief.must_visualize or []) + list(page_brief.must_include or []):
        raw = str(item or "").strip()
        if not raw or raw in subtitle_candidates:
            continue
        if _looks_like_cover_time_range(raw) or raw.startswith(("副标题", "subtitle", "时间", "时段")):
            subtitle_candidates.append(raw)

    page_goal = str(page_brief.page_goal or "").strip()
    if page_goal and not _is_sentence_like(page_goal):
        subtitle_candidates.append(page_goal)

    outline = str(page_brief.source_outline_section or "").strip()
    if outline and outline not in subtitle_candidates and not _is_sentence_like(outline):
        subtitle_candidates.append(outline)

    if subtitle_candidates:
        texts.append({"id": "subtitle", "role": "subtitle", "text": subtitle_candidates[0], "priority": 8})

    meta_candidates: List[str] = []
    for item in list(page_brief.must_visualize or []) + list(page_brief.must_include or []):
        raw = str(item or "").strip()
        if raw and _looks_like_cover_meta(raw) and raw not in meta_candidates:
            meta_candidates.append(raw)
    if meta_candidates:
        texts.append({"id": "tag", "role": "label", "text": meta_candidates[0], "priority": 5})
    return texts


def planned_texts_from_page(page_brief: PageBrief) -> List[Dict[str, Any]]:
    if str(page_brief.page_type or "").strip().lower() == "cover":
        return _cover_known_texts(page_brief)

    texts: List[Dict[str, Any]] = []
    candidates = [
        ("title", page_brief.key_takeaway, 10),
        ("subtitle", page_brief.page_goal, 8),
        ("visual_intent", page_brief.visual_intent, 5),
    ]
    for role, text, priority in candidates:
        raw = str(text or "").strip()
        if raw:
            texts.append({"id": role, "role": role, "text": raw, "priority": priority})
    for idx, item in enumerate(list(page_brief.must_include or [])[:8], start=1):
        raw = str(item or "").strip()
        if raw and raw not in {str(t.get("text")) for t in texts}:
            texts.append({"id": f"must_{idx}", "role": "body", "text": raw, "priority": 6})
    return texts


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
        "known_texts": planned_texts_from_page(page_brief),
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
        "Your job is to design the prompt contract for gpt-image-2, which will create a COMPLETE 16:9 PPT page visual.\n"
        "The generated image is the visual source of truth for composition, hierarchy, visual rhythm, and illustration style.\n"
        "Known text/content is already planned upstream. Preserve it as the semantic source of truth.\n\n"
        "Rules:\n"
        "- The full_slide_prompt must ask for a finished premium PPT page, not a background-only image.\n"
        "- Include the planned text strings as intended slide text/design references so the visual model can express real hierarchy.\n"
        "- Do not invent facts, company names, numbers, labels, or claims outside known_texts and page brief.\n"
        "- The page must have strong complete visual expression: background, panels, illustrations, icons, depth, and hierarchy.\n"
        "- Keep the generated visual reconstruction-friendly: avoid dense node-link diagrams, complex flowcharts, intricate geometric topology, spiderweb connectors, particle meshes, and many crossing lines.\n"
        "- Prefer layouts made from clean cards, simple icon rows, short timelines, small tables, simple 2-4 step flows, and lightly illustrated modules that can be rebuilt as editable shapes/text/icons.\n"
        "- If a technical concept needs a diagram, request a simplified schematic with clearly separated blocks and minimal connectors, not a dense topology.\n"
        "- Add reconstruction_rules for what should later become editable text/shape/chart blocks.\n"
        "- If the page is cover or closing, allow a large integrated hero visual; later reconstruction may keep the hero/background as an image asset.\n"
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
        "\"reconstruction_rules\":[\"\"]"
        "}\n\n"
        f"Deck/page payload:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def build_visual_region_analysis_prompt(*, page_plan: Dict[str, Any]) -> str:
    page_type = str((page_plan or {}).get("page_type") or "").strip().lower()
    content_page_rules = ""
    if page_type == "content":
        content_page_rules = (
            "- This is a content page. First classify regions by reconstruction difficulty before deciding element granularity.\n"
            "- Use complexity=simple for icons, simple timelines, simple cards, and basic flow diagrams that can be rebuilt with a small number of editable primitives.\n"
            "- Use complexity=complex for structured diagrams that need skeletal rebuilding: keep main columns, main connectors, key nodes, and labels only.\n"
            "- Use complexity=dense_topology for neural-network-style dense node-link diagrams, particle meshes, and other visuals whose value is the overall structure rather than every tiny node or line.\n"
            "- analysis_strategy must be one of: atomic, skeletal, abstract.\n"
            "- simple => atomic, complex => skeletal, dense_topology => skeletal or abstract.\n"
            "- For labeled technical schematics such as MLP, CNN/RNN, transformer blocks, topology diagrams, or node-link architectures with clear layers/roles, prefer dense_topology + skeletal, not abstract.\n"
            "- Use abstract only when a dense region is mainly atmospheric/decorative and cannot contribute meaningful editable structure.\n"
        )
    return (
        "You are doing stage 1 coarse visual planning for editable PPT reconstruction.\n"
        "Return strict JSON only matching VisualRegionAnalysis.\n\n"
        "Goal:\n"
        "- Understand the whole slide at region level before any fine-grained decomposition.\n"
        "- Identify the major visual regions, their semantic role, their complexity, and the right reconstruction strategy.\n"
        "- Do NOT explode the page into many low-level elements in this stage.\n\n"
        "Rules:\n"
        "- Regions should cover the meaningful visual modules of the page: header, left diagram, card list, timeline, chart, support icon row, etc.\n"
        "- Prefer 4-12 regions for a typical content page.\n"
        "- Decide each region's complexity based on information density, connector density, and structural regularity.\n"
        "- If a region contains many repeated nodes and many thin links, it is likely dense_topology and should not be atomized later.\n"
        "- expected_element_types should describe the intended rebuild vocabulary for that region, such as text/icon/line/rectangle/circle.\n"
        f"{content_page_rules}"
        "- Keep coordinates normalized 0..1.\n\n"
        "Output JSON shape:\n"
        "{"
        "\"page_id\":\"\","
        "\"canvas\":{\"w\":1600,\"h\":900,\"aspect\":\"16:9\"},"
        "\"style\":{\"theme\":\"\",\"mood\":\"\",\"palette\":[\"#000000\"],\"typography\":{},\"background_language\":\"\"},"
        "\"layout\":{\"visual_flow\":\"\",\"safe_margins\":{\"left\":0.05,\"top\":0.05,\"right\":0.05,\"bottom\":0.05}},"
        "\"regions\":[{\"id\":\"\",\"region_type\":\"header|panel|card_list|timeline|diagram|chart|icon_row|background|mixed\","
        "\"semantic_role\":\"\",\"bbox\":{\"x\":0,\"y\":0,\"w\":0.2,\"h\":0.2},"
        "\"complexity\":\"simple|complex|dense_topology\","
        "\"analysis_strategy\":\"atomic|skeletal|abstract\","
        "\"expected_element_types\":[\"text\",\"icon\",\"line\"],"
        "\"related_group_ids\":[\"\"],"
        "\"notes\":\"\"}],"
        "\"reconstruction_notes\":[\"\"],"
        "\"risks\":[\"\"]"
        "}\n\n"
        f"Known page plan:\n{json.dumps(page_plan, ensure_ascii=False)}"
    )


def build_visual_detail_analysis_prompt(
    *,
    page_plan: Dict[str, Any],
    coarse_region_analysis: Dict[str, Any] | None = None,
    focus_region: Dict[str, Any] | None = None,
) -> str:
    page_type = str((page_plan or {}).get("page_type") or "").strip().lower()
    content_page_rules = ""
    if page_type == "content":
        content_page_rules = (
            "- This is a content page. Prioritize editable reconstruction via text_box, line, rectangle, circle, group, chart, and icon blocks.\n"
            "- Do NOT use a full-slide screenshot or broad illustration region as a shortcut for the page body.\n"
            "- For content pages, prefer SVG/shape reconstruction for icons, timelines, card modules, node-link diagrams, and technology schematics.\n"
            "- Only mark a region as image_asset when it is truly non-textual and too visually complex to express as editable SVG/shape structure.\n"
            "- Follow the supplied coarse region plan. Do not ignore region complexity or analysis_strategy.\n"
            "- The analysis should capture semantic anchors and generation cues, not pixel-perfect micro-detail.\n"
        )
    coarse_json = json.dumps(coarse_region_analysis or {}, ensure_ascii=False)
    focus_region_json = json.dumps(focus_region or {}, ensure_ascii=False)
    region_focus_rules = ""
    if focus_region:
        region_focus_rules = (
            "- Focus only on the supplied focus_region.\n"
            "- Emit only the local elements, text, groups, and relationships needed for that region.\n"
            "- Do not duplicate unrelated whole-page modules, background, or other regions.\n"
            "- Keep coordinates normalized relative to the full slide, not the local region crop.\n"
        )
    return (
        "You are doing stage 2 detailed visual reconstruction planning for editable PPT reconstruction.\n"
        "Analyze the provided generated slide image and return strict JSON only matching VisualSemanticAnalysis.\n\n"
        "Important intent:\n"
        "- The image is a COMPLETE visual design generated from the known page plan.\n"
        "- A coarse region plan has already classified the page into regions and complexity levels. Honor that plan.\n"
        "- Do NOT rely on OCR as the source of factual content. Known text in page_plan is authoritative.\n"
        "- Still extract every visible text region into text_elements[]. If the text is legible, include the exact text from the image; if it matches page_plan planned_texts, set text_ref_id.\n"
        "- Use the image to infer semantic regions, bbox, z-order, style, hierarchy, visual assets, and what can be rebuilt as editable elements.\n"
        "- Express not only visible elements, but also their grouping, structural role, and relationships.\n"
        "- Describe every major visible element semantically. Do not output HTML.\n\n"
        "Reconstruction strategy rules:\n"
        "- Your job is to identify the semantic anchors required to regenerate a finished editable design, not to reproduce every pixel or every tiny decorative detail.\n"
        "- Text-like regions should reference planned_texts via text_ref_id when possible.\n"
        "- Simple panels/cards/lines/basic shapes should be render_strategy=freeform_block.\n"
        "- Charts should be render_strategy=chart_block only if the chart meaning is clear from page_plan; otherwise use freeform_block or image_asset.\n"
        "- Complex illustration, cinematic background, hero art, photoreal/3D/vector-rich motif should be render_strategy=image_asset with a no-text asset_prompt.\n"
        "- SVG/shape reconstruction is strongly preferred for icons, timeline nodes, arrows, node-link diagrams, process schematics, chips, database glyphs, and other geometric motifs.\n"
        "- For content pages, prefer editable reconstruction: panels, icons, lines, labels, cards, diagrams, and charts should be represented as editable elements rather than one full-slide image.\n"
        "- For content pages, do not collapse visible sub-elements into a parent panel description. If a card contains badge, icon, divider, title, and body text, list each as its own element/text_element.\n"
        "- Respect region complexity. simple/atomic regions may be decomposed in detail. complex/skeletal regions should keep only the major structure. dense_topology regions must never be atomized into every tiny node and line.\n"
        "- For dense_topology or skeletal regions, preserve the overall logic using only the main columns, main connectors, representative key nodes, and labels. Do not enumerate every repeated neuron, particle, or micro-connector.\n"
        "- For labeled technical diagrams such as MLP/CNN/RNN/transformer/network schematics, output enough editable structure to regenerate a finished diagram: main layer containers, a limited set of representative circle nodes per layer, and several principal connector lines between layers.\n"
        "- Do not collapse a meaningful technical diagram into one generic diagram region plus one connector bundle if the visible structure clearly shows layers, nodes, and directional connectivity.\n"
        "- For complex or dense_topology regions, include enough structure/style cues so a later generator can produce a polished final module rather than a bare skeleton.\n"
        "- Budget guidance: atomic regions usually <= 12 visual elements; skeletal regions usually <= 16 visual elements; dense_topology regions usually <= 18 visual elements plus labels.\n"
        "- Every visible icon, pictogram, logo-like mark, timeline marker, and small diagram glyph must be listed as a separate type='icon' element with bbox, semantic_role, structural_role, content_hint, nearby_text, visual_description, and style.\n"
        "- Simple diagrams such as nodes connected by lines should be decomposed into shape/circle/line/icon/text elements where possible. Dense topology diagrams should instead be described by a compact skeletal set of elements.\n"
        "- If multiple elements belong to one repeated module, such as a timeline node or information card, put them in groups[] and set each element's group_id.\n"
        "- groups[] is relational context only; elements[] is the executable reconstruction list. If a group.child_ids entry names icon_*, dot_*, badge_*, divider_*, or diagram parts, those child ids must also appear as concrete elements[] entries with matching ids.\n"
        "- Never leave icon-like child ids only inside groups[]. Every support card icon, timeline icon, and small schematic glyph must exist as a real type='icon' element in elements[].\n"
        "- Never leave a diagram region as only one parent box when visible internal structure is clear. Dense_topology regions still need explicit internal structure such as representative circle nodes, layer containers, and principal connector lines.\n"
        "- Before finishing, self-check: every repeated card and every timeline node should have its visual children present in elements[], not only mentioned in groups[] or notes.\n"
        "- Distinguish structural lines from decorative lines: e.g. timeline axis vs connector edge vs underline accent.\n"
        "- For icons and diagram parts, describe the concrete geometry, not just abstract meaning. Example: 'hexagon mesh icon with six outer nodes and center link', 'CNN grid feeding arrow into RNN node chain', 'GPU chip rectangle with pins and small node links'.\n"
        "- Use visual_description, geometry_hint, and style to describe the intended finished look of the module, including symmetry, density, glow language, spacing rhythm, and emphasis hierarchy when relevant.\n"
        "- Every visible text string, including numbers in badges, chart labels, timeline dates, small captions, and labels inside panels, must appear in text_elements[].\n"
        f"{content_page_rules}"
        f"{region_focus_rules}"
        "- Keep coordinates normalized 0..1 relative to the full slide.\n"
        "- Provide z_index where lower is behind higher.\n\n"
        "Output JSON shape:\n"
        "{"
        "\"page_id\":\"\","
        "\"canvas\":{\"w\":1600,\"h\":900,\"aspect\":\"16:9\"},"
        "\"style\":{\"theme\":\"\",\"mood\":\"\",\"palette\":[\"#000000\"],\"typography\":{},\"background_language\":\"\"},"
        "\"layout\":{\"visual_flow\":\"\",\"safe_margins\":{\"left\":0.05,\"top\":0.05,\"right\":0.05,\"bottom\":0.05}},"
        "\"elements\":[{\"id\":\"\",\"type\":\"background|illustration|panel|shape|circle|line|icon|diagram|chart|text|table|decorative\","
        "\"semantic_role\":\"\",\"bbox\":{\"x\":0,\"y\":0,\"w\":0.1,\"h\":0.1},\"z_index\":1,"
        "\"render_strategy\":\"freeform_block|image_asset|svg_shape|chart_block|ignore\","
        "\"style\":{\"fill\":\"\",\"stroke\":\"\",\"radius\":0,\"opacity\":1,\"shadow\":\"\",\"color\":\"\"},"
        "\"content_hint\":\"\",\"text\":\"\",\"role\":\"title|subtitle|body|label\",\"align\":\"left|center|right\","
        "\"font\":{\"size_px\":24,\"weight\":400,\"family_hint\":\"sans\",\"color\":\"#111111\",\"line_height\":1.2,\"letter_spacing\":0},"
        "\"asset_prompt\":\"\",\"text_ref_id\":\"\",\"confidence\":0.8,"
        "\"group_id\":\"\",\"parent_group_id\":\"\",\"structural_role\":\"\",\"context_type\":\"\","
        "\"visual_description\":\"\",\"geometry_hint\":\"\",\"nearby_text\":\"\","
        "\"relation_tags\":[\"\"],\"preserve_mode\":\"editable|svg|asset\",\"editable_priority\":\"high|medium|low\"}],"
        "\"text_elements\":[{\"id\":\"\",\"bbox\":{\"x\":0,\"y\":0,\"w\":0.1,\"h\":0.1},\"z_index\":1,"
        "\"text\":\"\",\"role\":\"title|subtitle|body|label\",\"align\":\"left|center|right\","
        "\"font\":{\"size_px\":24,\"weight\":400,\"family_hint\":\"sans\",\"color\":\"#111111\",\"line_height\":1.2,\"letter_spacing\":0},"
        "\"text_ref_id\":\"\",\"confidence\":0.8,\"group_id\":\"\",\"structural_role\":\"\",\"nearby_visual_id\":\"\",\"source\":\"planned|ocr|hybrid\"}],"
        "\"groups\":[{\"id\":\"\",\"group_type\":\"card|timeline_node|timeline|diagram_region|panel_cluster|icon_row\",\"semantic_role\":\"\","
        "\"bbox\":{\"x\":0,\"y\":0,\"w\":0.2,\"h\":0.2},\"child_ids\":[\"\"],\"parent_group_id\":\"\",\"layout_pattern\":\"\",\"importance\":\"primary|secondary\",\"preserve_mode\":\"editable|svg|asset\",\"notes\":\"\"}],"
        "\"relationships\":[{\"source_id\":\"\",\"target_id\":\"\",\"relation_type\":\"belongs_to|connected_to|axis_for|label_for|part_of|parallel_to|active_node_of\",\"description\":\"\",\"importance\":\"primary|secondary\"}],"
        "\"image_assets\":[{\"id\":\"\",\"purpose\":\"background|illustration|hero_visual\",\"bbox\":{\"x\":0,\"y\":0,\"w\":1,\"h\":1},\"prompt\":\"no-text prompt\",\"size\":\"1536x864\"}],"
        "\"reconstruction_notes\":[\"\"],\"risks\":[\"\"]"
        "}\n\n"
        f"Coarse region plan:\n{coarse_json}\n\n"
        f"Known page plan:\n{json.dumps(page_plan, ensure_ascii=False)}\n\n"
        f"Focus region:\n{focus_region_json}"
    )


def build_visual_analysis_prompt(*, page_plan: Dict[str, Any]) -> str:
    return build_visual_detail_analysis_prompt(page_plan=page_plan, coarse_region_analysis={})


def build_visual_analysis_repair_prompt(*, page_plan: Dict[str, Any], prior_analysis: Dict[str, Any], issues: List[str]) -> str:
    return (
        "You are repairing an incomplete VisualSemanticAnalysis JSON for editable PPT reconstruction.\n"
        "Return strict JSON only matching VisualSemanticAnalysis.\n\n"
        "The prior analysis was structurally incomplete.\n"
        "Repair goals:\n"
        "- Preserve correct regions/text already identified, but fix missing executable visual elements.\n"
        "- Any icon-like child ids referenced by groups[] must also exist as concrete type='icon' elements in elements[].\n"
        "- Any timeline node should include its icon/marker children as real elements[].\n"
        "- Any diagram_region that is intended to be editable/svg must include basic internal structure such as circle/line/icon elements when visible.\n"
        "- Do not return placeholder ids in groups[] without matching elements[].\n"
        "- Keep coordinates normalized 0..1 and preserve real page structure.\n\n"
        f"Detected issues:\n{json.dumps(issues, ensure_ascii=False)}\n\n"
        f"Known page plan:\n{json.dumps(page_plan, ensure_ascii=False)}\n\n"
        f"Prior incomplete analysis:\n{json.dumps(prior_analysis, ensure_ascii=False)}"
    )


def build_blueprint_compose_prompt(
    *,
    deck_brief: Dict[str, Any],
    page_plan: Dict[str, Any],
    visual_analysis: Dict[str, Any],
    image_asset_map: Dict[str, str],
    source_slide_image_url: str,
    icon_svg_map: Dict[str, Dict[str, str]] | None = None,
    focus_region: Dict[str, Any] | None = None,
) -> str:
    payload = {
        "deck_brief": deck_brief,
        "page_plan": page_plan,
        "visual_analysis": visual_analysis,
        "image_asset_map": image_asset_map,
        "icon_svg_map": icon_svg_map or {},
        "source_slide_image_url": source_slide_image_url,
        "focus_region": focus_region or {},
    }
    focus_rules = ""
    if focus_region:
        focus_rules = (
            "- Focus only on the supplied focus_region and produce blocks only for that region.\n"
            "- Do not duplicate whole-page blocks, unrelated modules, or text that belongs to other regions.\n"
            "- Block ids must stay stable and region-specific so partial pages can be merged safely.\n"
            "- The output for this region must be a finished, presentation-ready module, not a rough scaffold or debug skeleton.\n"
        )
    return (
        "You are rebuilding an image-native PPT page into editable FreeformPageBlueprint JSON.\n"
        "Return strict JSON only matching ComposerPageBlueprint.\n\n"
        "Core idea:\n"
        "- gpt-image-2 created a complete slide visual. GPT-5.4 analyzed its semantic visual structure.\n"
        "- Recreate the design as editable blocks for the existing frontend editor and PPTX compiler.\n"
        "- The result must be a finished presentation page/module that looks intentional and complete, not a wireframe, not a placeholder, and not a half-finished scaffold.\n"
        "- Known page_plan text is authoritative. Use it for text_box content; do not OCR or invent text.\n"
        "- Also preserve every visual_analysis.text_elements item as an editable text_box. If text_ref_id maps to page_plan planned_texts, use the planned text; otherwise use the text extracted in text_elements.\n"
        "- Use visual_analysis for bbox, hierarchy, style, semantic grouping, and element relationships.\n\n"
        "Block rules:\n"
        "- Use only existing block types: group, rectangle, circle, line, icon, chart, image, text_box.\n"
        "- When a block corresponds to a visual_analysis element, text_element, or group, reuse that source id exactly instead of inventing a new id.\n"
        "- Complex background/hero/illustration must be image blocks using image_asset_map URLs when present.\n"
        "- If no regenerated asset exists for a major image_asset, you may use source_slide_image_url only as a last-resort background reference for cover/closing pages. For content pages, prefer editable shapes/SVG and do not use a full-slide screenshot as the page body.\n"
        "- Simple panels/cards/dividers should be editable rectangle/group/line blocks.\n"
        "- Preserve decomposed child elements from visual_analysis. Do not replace a content-page card, diagram, or icon row with a single generic panel if the analysis lists its internal parts.\n"
        "- You may add reasonable finishing detail that is semantically consistent with visual_analysis, such as additional connector lines, repeated nodes, balanced spacing, decorative dividers, or refined grouping, when needed to make the result feel complete.\n"
        "- Do not aim for pixel-perfect restoration. Aim for semantic fidelity, visual completeness, and strong editorial polish.\n"
        "- All planned_texts should appear as editable text_box blocks, positioned according to the analyzed visual text/semantic areas.\n"
        "- All visual text from text_elements must appear as editable text_box blocks unless it exactly duplicates an existing planned_text text_box.\n"
        "- Icons should be icon blocks. Use icon_svg_map when supplied for precise inline SVG, and preserve group context such as timeline node icon vs card icon.\n"
        "- Prefer circle + line + icon + text composition for timeline/process/diagram structures when the analysis provides groups/relationships for them.\n"
        "- For dense_topology or schematic diagrams, generate a polished editable diagram that expresses the same semantic structure and visual intent, even if the exact micro-geometry differs from the source image.\n"
        "- For content pages, avoid introducing illustration/image blocks unless the analysis explicitly marks a region preserve_mode=asset and it contains no text.\n"
        "- Avoid duplicating text baked into image blocks when possible: prefer no-text regenerated assets for image blocks.\n"
        "- Every block needs stable id, x,y,w,h normalized 0..1, z_index, and style.\n"
        "- Use coordinate_space='parent' for children inside groups.\n"
        "- Shapes should use CSS-compatible style keys already supported by renderer/editor: background, border_color, border_radius, box_shadow, color, font_size, font_weight, text_align, line_height, opacity.\n"
        "- Before finishing, self-check that the region/page would look complete to an end user without any further manual beautification.\n\n"
        f"{focus_rules}"
        f"Payload:\n{json.dumps(payload, ensure_ascii=False)}"
    )
