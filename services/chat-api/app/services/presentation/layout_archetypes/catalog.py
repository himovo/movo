from __future__ import annotations

from .contracts import LayoutArchetypeSpec


CONTENT = frozenset({"content"})
SPECIAL_OR_CONTENT = frozenset({"cover", "agenda", "section_divider", "content", "thank_you"})


def _spec(
    archetype_id: str,
    family: str,
    *,
    intents: tuple[str, ...] = (),
    keywords: tuple[str, ...] = (),
    brief: str,
    must_do: tuple[str, ...],
    avoid: tuple[str, ...] = (),
    page_types: frozenset[str] = CONTENT,
    min_items: int = 0,
    max_items: int = 99,
    data: bool = False,
    comparison: bool = False,
    sequence: bool = False,
    image: bool = False,
) -> LayoutArchetypeSpec:
    return LayoutArchetypeSpec(
        archetype_id=archetype_id,
        family=family,
        page_types=page_types,
        page_intents=frozenset(intents),
        keywords=keywords,
        prompt_brief=brief,
        must_do=must_do,
        must_avoid=avoid,
        min_content_items=min_items,
        max_content_items=max_items,
        requires_data=data,
        requires_comparison=comparison,
        requires_sequence=sequence,
        requires_image=image,
    )


ARCHETYPE_CATALOG: tuple[LayoutArchetypeSpec, ...] = (
    _spec("dominant_panel", "editorial", intents=("introduce_topic", "ask_for_decision"), keywords=("主张", "结论", "决策", "thesis", "decision"), brief="One dominant message panel with restrained supporting evidence.", must_do=("Create one unmistakable primary anchor.", "Keep support content secondary."), page_types=SPECIAL_OR_CONTENT, max_items=4),
    _spec("asymmetric_split", "editorial", intents=("frame_problem", "explain_solution"), keywords=("问题", "方案", "背景", "洞察", "problem", "solution", "insight"), brief="An intentionally unequal two-region composition, with one side carrying the main argument.", must_do=("Use clearly unequal visual weights.", "Maintain one reading direction."), avoid=("Do not make two equal card columns.",), min_items=2, max_items=6),
    _spec("layered_band", "process_system", intents=("explain_solution", "show_architecture"), keywords=("分层", "层级", "治理", "layer", "tier"), brief="Substantial horizontal or vertical bands that express layers and responsibility boundaries.", must_do=("Make layer order explicit.", "Place labels inside solid bands."), sequence=True, min_items=3, max_items=7),
    _spec("structured_matrix", "comparison_data", intents=("compare_options", "show_metrics"), keywords=("矩阵", "四象限", "优先级", "matrix", "quadrant", "priority"), brief="A clear matrix with explicit axes or row/column meaning and concise cells.", must_do=("Expose the matrix logic.", "Keep cell copy concise."), avoid=("Do not turn cells into paragraphs.",), min_items=4, max_items=9),
    _spec("stacked_system", "process_system", intents=("show_architecture", "explain_solution"), keywords=("技术栈", "能力栈", "基础设施", "stack", "platform"), brief="A vertically stacked system showing dependency from foundation to experience.", must_do=("Show dependency order.", "Use 3-6 substantial stacked regions."), sequence=True, min_items=3, max_items=6),
    _spec("timeline_spine", "process_system", intents=("show_roadmap", "show_process"), keywords=("时间线", "里程碑", "年度", "timeline", "milestone", "roadmap"), brief="A single timeline spine with ordered milestones and concise annotations.", must_do=("Keep one chronological direction.", "Align milestones to one spine."), avoid=("Do not create disconnected mini timelines.",), sequence=True, min_items=3, max_items=8),
    _spec("card_grid", "structured", intents=("explain_solution", "show_case"), keywords=("能力清单", "功能", "模块", "features", "capabilities", "modules"), brief="A disciplined grid of peer items with consistent hierarchy and spacing.", must_do=("Use a real grid rhythm.", "Keep peer cards equal in hierarchy."), avoid=("Do not use this for sequential or causal content.",), min_items=3, max_items=8),
    _spec("left_right_comparison", "comparison_data", intents=("compare_options",), keywords=("对比", "优劣", "差异", "comparison", "versus", "vs"), brief="Two aligned sides with one-to-one comparison points.", must_do=("Keep comparison criteria aligned.", "Make both sides immediately distinguishable."), comparison=True, min_items=2, max_items=10),
    _spec("top_hero_bottom_detail", "editorial", intents=("introduce_topic", "explain_solution"), keywords=("概览", "核心", "总览", "overview", "core"), brief="A strong top hero statement followed by a compact detail zone.", must_do=("Reserve the top region for the main takeaway.", "Keep lower details subordinate."), min_items=2, max_items=6),
    _spec("full_bleed_visual", "editorial", intents=("introduce_topic",), keywords=("封面", "开场", "视觉", "cover", "opening"), brief="A full-canvas visual statement with minimal, high-impact text.", must_do=("Use the entire canvas as one composition.", "Keep copy minimal."), avoid=("Do not add a card grid.",), page_types=frozenset({"cover", "section_divider", "content"}), max_items=3),
    _spec("quote_spotlight", "editorial", intents=("introduce_topic", "ask_for_decision"), keywords=("引言", "金句", "观点", "引用", "quote", "statement"), brief="One prominent quotation or insight with attribution and generous whitespace.", must_do=("Make the quotation the visual center.", "Include attribution or context."), max_items=3),
    _spec("icon_feature_row", "structured", intents=("explain_solution",), keywords=("支柱", "能力", "特性", "pillars", "features"), brief="A single row of icon-led capability columns.", must_do=("Use 3-6 aligned feature columns.", "Give every column a meaningful icon and concise copy."), min_items=3, max_items=6),
    _spec("split_screen_dual", "comparison_data", intents=("compare_options", "frame_problem"), keywords=("之前", "之后", "现状", "目标", "before", "after", "old", "new"), brief="Two full-height contrasting worlds separated by a clear boundary.", must_do=("Use two distinct visual fields.", "Keep the contrast explicit."), comparison=True, min_items=2, max_items=8),
    _spec("data_dashboard", "comparison_data", intents=("show_metrics",), keywords=("指标", "仪表盘", "经营数据", "metrics", "dashboard", "performance"), brief="A KPI-led dashboard with one or two charts and a clear analytical hierarchy.", must_do=("Show visible metrics or charts.", "Prioritize one analytical conclusion."), data=True, min_items=3, max_items=8),
    _spec("numbered_list", "structured", intents=("show_process", "ask_for_decision"), keywords=("要点", "优先事项", "行动项", "清单", "priorities", "actions", "agenda"), brief="A vertical sequence of numbered, presentation-grade takeaways.", must_do=("Use clear ordinal markers.", "Keep row structure consistent."), min_items=3, max_items=6),
    _spec("image_text_split", "media", intents=("show_case", "introduce_topic"), keywords=("案例", "场景", "客户故事", "截图", "case", "scenario", "story"), brief="One substantial visual region paired with a focused narrative region.", must_do=("Include one real image block or generation prompt.", "Keep image and text in separate readable regions."), image=True, min_items=2, max_items=5),
    _spec("big_number_row", "comparison_data", intents=("show_metrics",), keywords=("增长", "降低", "提升", "节省", "growth", "reduction", "increase", "roi"), brief="Three or four large metrics in one row, with numbers as the first visual read.", must_do=("Use at least two prominent numeric values.", "Keep metric labels secondary."), data=True, min_items=2, max_items=5),
    _spec("accent_callout", "structured", intents=("ask_for_decision", "close_gratitude"), keywords=("建议", "决策", "风险", "行动", "recommendation", "decision", "cta"), brief="One bold callout carrying the decision or recommendation, supported by a few restrained points.", must_do=("Create one accent callout as the hero.", "Keep supporting content compact."), page_types=frozenset({"content", "thank_you"}), max_items=5),
    _spec("sidebar_toc", "structured", intents=("show_roadmap",), keywords=("目录", "章节", "议程", "toc", "agenda", "chapter"), brief="A persistent sidebar index paired with a focused content region.", must_do=("Make the active section visible.", "Keep navigation and content visually separate."), page_types=frozenset({"agenda", "section_divider", "content"}), min_items=3, max_items=7),
    _spec("hero_statement", "editorial", intents=("introduce_topic", "close_gratitude"), keywords=("使命", "愿景", "一句话", "命题", "mission", "vision", "thesis"), brief="One oversized statement with intentional whitespace and minimal support.", must_do=("Make one sentence dominate the page.", "Protect generous whitespace."), page_types=SPECIAL_OR_CONTENT, max_items=3),
    _spec("stats_plus_narrative", "comparison_data", intents=("show_metrics", "show_case"), keywords=("结果分析", "成效", "数据故事", "results", "outcome", "impact"), brief="A compact metric column paired with narrative explaining what the numbers mean.", must_do=("Include visible metrics.", "Use narrative to interpret rather than repeat them."), data=True, min_items=3, max_items=7),
    _spec("alternating_zigzag", "process_system", intents=("show_process", "show_case"), keywords=("旅程", "演进", "阶段故事", "journey", "evolution"), brief="Three or four alternating rows that create a visual journey across the page.", must_do=("Alternate visual and text emphasis by row.", "Preserve a clear top-to-bottom sequence."), sequence=True, min_items=3, max_items=5),
    _spec("progressive_arrow_chain", "process_system", intents=("show_roadmap", "show_process"), keywords=("成熟度", "升级", "递进", "演进路径", "maturity", "upgrade", "progression"), brief="A left-to-right progression of stages that visibly increase in maturity or impact.", must_do=("Show explicit progression.", "Use one directional chain."), sequence=True, min_items=3, max_items=6),
    _spec("architecture_blueprint", "process_system", intents=("show_architecture",), keywords=("系统架构", "技术架构", "模块分层", "architecture", "technology stack"), brief="A dense but readable architecture board organized into labeled system layers and modules.", must_do=("Show explicit layers and module boundaries.", "Use concise labels inside structured containers."), avoid=("Do not represent architecture with connector lines alone.",), min_items=4, max_items=30),
    _spec("radial_feature_ring", "process_system", intents=("explain_solution",), keywords=("生态", "核心能力", "中心", "围绕", "ecosystem", "core capability"), brief="One central concept surrounded by four or five supporting capabilities using safe rectangular regions.", must_do=("Keep one central anchor.", "Place 4-5 supporting regions around it."), min_items=4, max_items=6),
)


_BY_ID = {item.archetype_id: item for item in ARCHETYPE_CATALOG}
if len(_BY_ID) != 25 or len(_BY_ID) != len(ARCHETYPE_CATALOG):
    raise RuntimeError("presentation layout archetype catalog must contain 25 unique entries")


def archetype_by_id(archetype_id: str) -> LayoutArchetypeSpec:
    try:
        return _BY_ID[str(archetype_id or "").strip()]
    except KeyError as exc:
        raise ValueError(f"unknown presentation layout archetype: {archetype_id}") from exc


__all__ = ["ARCHETYPE_CATALOG", "archetype_by_id"]
