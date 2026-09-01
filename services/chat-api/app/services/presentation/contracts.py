from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field, model_validator

from app.services.presentation.layout_protocol import normalize_line_route


def _split_to_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, tuple):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if not text:
        return []
    parts = re.split(r"[|\n,，;；]+", text)
    return [p.strip() for p in parts if p.strip()]


def _to_int_like(value: Any, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return default
    match = re.search(r"-?\d+", text)
    if not match:
        return default
    try:
        return int(match.group(0))
    except Exception:
        return default


def _extract_text_like(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        parts = [str(v).strip() for v in value if str(v).strip()]
        return "\n".join(parts)
    if isinstance(value, dict):
        for key in (
            "text",
            "content",
            "title",
            "subtitle",
            "label",
            "name",
            "value",
            "caption",
            "description",
            "desc",
            "body",
        ):
            candidate = value.get(key)
            if candidate is not None and str(candidate).strip():
                return str(candidate)
        return ""
    text = str(value).strip()
    return text


class FreeformTheme(BaseModel):
    page_background: str = "#ffffff"
    page_border_color: str = "rgba(0, 0, 0, 0.08)"
    surface_background: str = "transparent"
    surface_border_color: str = "transparent"
    surface_shadow: str = "none"
    accent_color: str = "#2563eb"
    accent_soft_color: str = "transparent"
    title_color: str = "#111111"
    body_color: str = "#222222"
    muted_color: str = "#666666"
    font_family: str = "'PingFang SC', 'Microsoft YaHei', sans-serif"
    document_style: Dict[str, Any] = Field(default_factory=dict)
    deck_style: Dict[str, Any] = Field(default_factory=dict)
    page_style: Dict[str, Any] = Field(default_factory=dict)
    surface_style: Dict[str, Any] = Field(default_factory=dict)
    role_styles: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    custom_css: str = ""


class DesignTokens(BaseModel):
    primary_color: str = "#2563eb"
    secondary_color: str = "#0f172a"
    accent_color: str = "#38bdf8"
    page_background: str = "#ffffff"
    surface_background: str = "#ffffff"
    title_color: str = "#111111"
    body_color: str = "#222222"
    muted_color: str = "#666666"
    title_font_size: int = 48
    subtitle_font_size: int = 28
    body_font_size: int = 22
    card_border_radius: int = 14
    border_width: int = 1
    line_weight: int = 2
    shadow_style: str = "subtle"
    font_family: str = "'PingFang SC', 'Microsoft YaHei', sans-serif"
    layout_density: str = "medium"

    @model_validator(mode="before")
    @classmethod
    def _normalize_numeric_tokens(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        int_fields = {
            "title_font_size": 48,
            "subtitle_font_size": 28,
            "body_font_size": 22,
            "card_border_radius": 14,
            "border_width": 1,
            "line_weight": 2,
        }
        for key, default in int_fields.items():
            if key in normalized:
                normalized[key] = _to_int_like(normalized.get(key), default)
        return normalized


class FreeformBlock(BaseModel):
    id: str = ""
    type: str = "text_box"
    role: str = ""
    container_id: str = ""
    coordinate_space: str = "page"
    x: float = 0.0
    y: float = 0.0
    x2: float | None = None
    y2: float | None = None
    w: float = 0.0
    h: float = 0.0
    max_w: float | None = None
    max_h: float | None = None
    min_w: float | None = None
    min_h: float | None = None
    padding: float | None = None
    auto_fit: bool = False
    content: str = ""
    style: Dict[str, Any] = Field(default_factory=dict)
    children: List["FreeformBlock"] = Field(default_factory=list)
    # Tabler icon name (e.g. "sparkles", "chart-line"). Set when type="icon".
    icon: str = ""
    # Resolved inline SVG markup — populated by normalizer, consumed by renderer.
    icon_svg: str = ""
    # Image generation prompt — set when type="image" and no URL is available.
    # Describes the desired image for downstream text-to-image generation.
    image_prompt: str = ""
    # Layer order: lower z_index renders behind higher z_index. Default 0.
    z_index: int = 0
    # "llm" = LLM provided explicit w/h; "inferred" = normalizer calculated from heuristics
    geometry_source: str = ""
    # Chart type for type="chart": one of "line", "bar", "pie".
    chart_type: str = ""
    # Structured chart payload consumed by SVG renderers and downstream PPT compilers.
    chart_data: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        block_id = str(
            normalized.get("id")
            or normalized.get("block_id")
            or normalized.get("key")
            or ""
        ).strip()
        block_type = str(
            normalized.get("type")
            or normalized.get("role")
            or "text_box"
        ).strip()
        if not block_id:
            coord_key = f"{normalized.get('x', 0)}_{normalized.get('y', 0)}"
            block_id = f"shape_{abs(hash(coord_key)) % 1000000}"
        normalized["id"] = block_id
        normalized["type"] = block_type
        normalized["role"] = str(
            normalized.get("role")
            or normalized.get("semantic_role")
            or normalized.get("layout_role")
            or ""
        ).strip()
        normalized["container_id"] = str(
            normalized.get("container_id")
            or normalized.get("parent_id")
            or normalized.get("panel_id")
            or normalized.get("card_id")
            or ""
        ).strip()
        coordinate_space = str(
            normalized.get("coordinate_space")
            or normalized.get("coords")
            or normalized.get("coordinateSpace")
            or "page"
        ).strip().lower()
        normalized["coordinate_space"] = "parent" if coordinate_space == "parent" else "page"
        if normalized.get("x2") is None:
            endpoint_x = normalized.get("end_x", normalized.get("x_end"))
            if endpoint_x is not None:
                normalized["x2"] = endpoint_x
        if normalized.get("y2") is None:
            endpoint_y = normalized.get("end_y", normalized.get("y_end"))
            if endpoint_y is not None:
                normalized["y2"] = endpoint_y
        for source_key, target_key in (
            ("max_width", "max_w"),
            ("maxWidth", "max_w"),
            ("max_height", "max_h"),
            ("maxHeight", "max_h"),
            ("min_width", "min_w"),
            ("minWidth", "min_w"),
            ("min_height", "min_h"),
            ("minHeight", "min_h"),
        ):
            if normalized.get(target_key) is None and normalized.get(source_key) is not None:
                normalized[target_key] = normalized.get(source_key)
        if normalized.get("padding") is None and normalized.get("inner_padding") is not None:
            normalized["padding"] = normalized.get("inner_padding")
        if normalized.get("auto_fit") is None:
            normalized["auto_fit"] = bool(normalized.get("autofit") or normalized.get("autoFit") or False)

        style_dict = dict(normalized.get("style") or {}) if isinstance(normalized.get("style"), dict) else {}

        content = normalized.get("content")
        if content in (None, ""):
            for key in (
                "text",
                "text_content",
                "label",
                "title",
                "subtitle",
                "name",
                "value",
                "caption",
                "description",
                "desc",
                "body",
            ):
                candidate = normalized.get(key)
                if candidate is not None and str(candidate).strip():
                    content = candidate
                    break
        if content in (None, "") and style_dict:
            for key in ("text", "label", "title", "subtitle", "content", "value"):
                candidate = style_dict.get(key)
                if candidate is not None and str(candidate).strip():
                    content = candidate
                    break

        chart_data_raw: Dict[str, Any] = {}
        if isinstance(content, dict):
            chart_data_raw = dict(content)
        normalized["content"] = _extract_text_like(content)

        # Normalize icon field — LLM may use icon_name, icon_id, etc.
        icon_raw = str(
            normalized.get("icon")
            or normalized.get("icon_name")
            or normalized.get("icon_id")
            or ""
        ).strip()
        # For type="icon", content often carries the icon name
        if str(normalized.get("type") or "").strip().lower() == "icon" and not icon_raw:
            icon_raw = str(normalized.get("content") or "").strip()
        normalized["icon"] = icon_raw

        chart_type_raw = str(
            normalized.get("chart_type")
            or normalized.get("chart_kind")
            or style_dict.get("chart_type")
            or style_dict.get("chart_kind")
            or chart_data_raw.get("chart_type")
            or chart_data_raw.get("chart_kind")
            or ""
        ).strip().lower()
        chart_alias = {
            "line_chart": "line",
            "line-chart": "line",
            "linechart": "line",
            "bar_chart": "bar",
            "bar-chart": "bar",
            "barchart": "bar",
            "pie_chart": "pie",
            "pie-chart": "pie",
            "piechart": "pie",
        }
        chart_type = chart_alias.get(chart_type_raw, chart_type_raw)
        if chart_type not in {"line", "bar", "pie"}:
            chart_type = ""
        normalized["chart_type"] = chart_type

        chart_data = {}
        if isinstance(normalized.get("chart_data"), dict):
            chart_data = dict(normalized.get("chart_data") or {})
        elif isinstance(style_dict.get("chart_data"), dict):
            chart_data = dict(style_dict.get("chart_data") or {})
        elif chart_data_raw:
            chart_data = chart_data_raw
        else:
            maybe_json = str(normalized.get("content") or "").strip()
            if maybe_json.startswith("{") and maybe_json.endswith("}"):
                try:
                    parsed = json.loads(maybe_json)
                    if isinstance(parsed, dict):
                        chart_data = parsed
                except Exception:
                    chart_data = {}
        if not chart_data and style_dict:
            style = dict(style_dict)
            lifted_keys = (
                "title",
                "subtitle",
                "categories",
                "series",
                "y_axis_label",
                "x_axis_label",
            )
            for key in lifted_keys:
                if key in style:
                    chart_data[key] = style.get(key)
        normalized["chart_data"] = chart_data

        normalized["style"] = style_dict
        return normalized

    @model_validator(mode="after")
    def _normalize_line_protocol(self) -> "FreeformBlock":
        if str(self.type or "").strip().lower() != "line":
            if self.min_w is not None and self.max_w is not None and self.min_w > self.max_w:
                self.min_w, self.max_w = self.max_w, self.min_w
            if self.min_h is not None and self.max_h is not None and self.min_h > self.max_h:
                self.min_h, self.max_h = self.max_h, self.min_h
            return self
        style = dict(self.style or {})
        if self.x2 is None:
            end_x = style.get("end_x", style.get("to_x"))
            if end_x is not None:
                try:
                    self.x2 = float(end_x)
                except Exception:
                    self.x2 = None
        if self.y2 is None:
            end_y = style.get("end_y", style.get("to_y"))
            if end_y is not None:
                try:
                    self.y2 = float(end_y)
                except Exception:
                    self.y2 = None
        style["route"] = normalize_line_route(str(style.get("route") or style.get("router") or style.get("path") or "auto"))
        self.style = style
        if self.min_w is not None and self.max_w is not None and self.min_w > self.max_w:
            self.min_w, self.max_w = self.max_w, self.min_w
        if self.min_h is not None and self.max_h is not None and self.min_h > self.max_h:
            self.min_h, self.max_h = self.max_h, self.min_h
        return self


class FreeformPageBlueprint(BaseModel):
    page_id: str
    page_title: str = ""
    page_subtitle: str = ""
    layout_type: str = "single_column"
    design_intent: str = ""
    style: Dict[str, Any] = Field(default_factory=dict)
    blocks: List[FreeformBlock] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        page_id = str(
            normalized.get("page_id")
            or normalized.get("id")
            or ""
        ).strip()
        if page_id:
            normalized["page_id"] = page_id
        if "page_title" not in normalized:
            normalized["page_title"] = str(
                normalized.get("title")
                or normalized.get("headline")
                or ""
            ).strip()
        if "page_subtitle" not in normalized:
            normalized["page_subtitle"] = str(
                normalized.get("subtitle")
                or normalized.get("subheadline")
                or ""
            ).strip()
        if "layout_type" not in normalized:
            default_layout = "" if cls.__name__ == "ComposerPageBlueprint" else "single_column"
            normalized["layout_type"] = str(
                normalized.get("layout")
                or normalized.get("layout_family")
                or default_layout
            ).strip()
        if "blocks" not in normalized:
            for alias in ("sections", "items", "zones"):
                if isinstance(normalized.get(alias), list):
                    normalized["blocks"] = normalized.get(alias)
                    break
        return normalized


class FreeformDeckBlueprint(BaseModel):
    deck_id: str
    deck_goal: str = ""
    target_audience: str = ""
    theme: FreeformTheme = Field(default_factory=FreeformTheme)
    pages: List[FreeformPageBlueprint] = Field(default_factory=list)
    runtime: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        if "deck_id" not in normalized:
            normalized["deck_id"] = str(
                normalized.get("id")
                or normalized.get("presentation_id")
                or "presentation"
            ).strip() or "presentation"
        if "deck_goal" not in normalized:
            normalized["deck_goal"] = str(
                normalized.get("goal")
                or normalized.get("title")
                or ""
            ).strip()
        if "target_audience" not in normalized:
            normalized["target_audience"] = str(
                normalized.get("audience")
                or ""
            ).strip()
        return normalized


class PageBrief(BaseModel):
    # page_id defaults to empty — downstream normalizer fills it from
    # page_index when the LLM truncates or omits the field under pressure.
    page_id: str = ""
    page_index: int = 0
    page_type: str = "content"
    page_goal: str = ""
    key_takeaway: str = ""
    visual_intent: str = ""
    composition_intent: str = ""
    narrative_role: str = ""
    source_outline_section: str = ""
    source_user_intent: str = ""
    relation_to_previous: str = ""
    relation_to_next: str = ""
    must_include: List[str] = Field(default_factory=list)
    must_avoid: List[str] = Field(default_factory=list)
    continuity_notes: List[str] = Field(default_factory=list)
    visual_center: str = ""
    dominant_move: str = ""
    must_visualize: List[str] = Field(default_factory=list)
    validation_profile: str = "presentation_page"
    layout_archetype_id: str = ""
    layout_family: str = ""
    layout_rationale: str = ""
    layout_constraints: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_list_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        for key in ("must_include", "must_avoid", "continuity_notes", "must_visualize"):
            normalized[key] = _split_to_list(normalized.get(key))
        # Coerce validation_profile — the LLM sometimes returns a structured
        # dict (e.g. ``{"hierarchy_clear": True, "weight_balance": "centered"}``)
        # instead of a short label. Schema expects a plain string for
        # downstream ``.lower()`` checks, so we stringify dicts defensively.
        vp = normalized.get("validation_profile")
        if isinstance(vp, dict):
            # Pick the most descriptive textual value, else fall back to default.
            text_values = [str(v).strip() for v in vp.values() if isinstance(v, str) and str(v).strip()]
            normalized["validation_profile"] = text_values[0] if text_values else "presentation_page"
        elif isinstance(vp, (list, tuple)):
            text_items = [str(v).strip() for v in vp if str(v).strip()]
            normalized["validation_profile"] = text_items[0] if text_items else "presentation_page"
        elif vp is None:
            normalized["validation_profile"] = "presentation_page"
        else:
            normalized["validation_profile"] = str(vp)
        return normalized


class DeckBrief(BaseModel):
    deck_id: str
    deck_goal: str = ""
    target_audience: str = ""
    presentation_context: str = ""
    language: str = "zh-CN"
    narrative_arc: List[str] = Field(default_factory=list)
    user_outline: str = ""
    user_generation_guidance: str = ""
    continuity_rules: List[str] = Field(default_factory=list)
    visual_direction: List[str] = Field(default_factory=list)
    design_tokens: DesignTokens = Field(default_factory=DesignTokens)
    page_briefs: List[PageBrief] = Field(default_factory=list)
    theme_factory_name: str = ""
    theme_factory_rationale: str = ""
    theme_factory_colors: Dict[str, Any] = Field(default_factory=dict)
    theme_factory_typography: Dict[str, Any] = Field(default_factory=dict)
    layout_distribution: Dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_list_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        for key in ("narrative_arc", "continuity_rules", "visual_direction"):
            normalized[key] = _split_to_list(normalized.get(key))
        if isinstance(normalized.get("page_briefs"), list):
            normalized["page_briefs"] = [
                item if isinstance(item, dict) else {}
                for item in list(normalized.get("page_briefs") or [])
            ]
        return normalized


class SkillConstraint(BaseModel):
    source: str = "runtime"
    skill_name: str = ""
    intent_rules: List[str] = Field(default_factory=list)
    style_guidance: List[str] = Field(default_factory=list)
    layout_preferences: List[str] = Field(default_factory=list)
    anti_patterns: List[str] = Field(default_factory=list)
    qa_checks: List[str] = Field(default_factory=list)
    priority: int = 50


class ConstraintBundle(BaseModel):
    user_outline: str = ""
    user_generation_guidance: str = ""
    user_message_context: str = ""
    base_rules: List[str] = Field(default_factory=list)
    deck_guidance: List[str] = Field(default_factory=list)
    page_guidance: List[str] = Field(default_factory=list)
    anti_patterns: List[str] = Field(default_factory=list)
    qa_checks: List[str] = Field(default_factory=list)
    skill_constraints: List[SkillConstraint] = Field(default_factory=list)
    tool_observations: List[Dict[str, str]] = Field(default_factory=list)


class PageGenerationContext(BaseModel):
    deck_brief: DeckBrief
    current_page: PageBrief
    previous_page: PageBrief | None = None
    next_page: PageBrief | None = None
    prior_page_summaries: List[Dict[str, Any]] = Field(default_factory=list)


class PageRepairReport(BaseModel):
    page_id: str
    issues: List[str] = Field(default_factory=list)
    accepted: bool = False
    attempt_count: int = 1
    issue_score_before: int = 0
    issue_score_after: int = 0


class ComposerPageBlueprint(FreeformPageBlueprint):
    # LLM-composed pages must declare the MOVO-assigned archetype. Keeping the
    # legacy FreeformPageBlueprint default would hide missing assignments.
    layout_type: str = ""
    # No min_length at pydantic level — business logic in _page_quality_issues handles this
    # with profile-aware thresholds (4 for content, 3 for cover/thankyou).
    blocks: List[FreeformBlock] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Rendering / preview contracts.
# ---------------------------------------------------------------------------


class HtmlCompileResult(BaseModel):
    html: str
    slide_count: int
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PreviewArtifactRef(BaseModel):
    url: str = ""
    object_path: str = ""
    filename: str = ""


class PresentationPreviewBundle(BaseModel):
    artifact_version: str = "0.1"
    pipeline_version: str = "current"
    deck_ir: Dict[str, Any]
    page_ir_refs: List[Dict[str, Any]] = Field(default_factory=list)
    html_preview: PreviewArtifactRef
    deck_ir_artifact: PreviewArtifactRef
    validation_report_artifact: PreviewArtifactRef = Field(default_factory=PreviewArtifactRef)
    debug_bundle_artifact: PreviewArtifactRef = Field(default_factory=PreviewArtifactRef)
    export_source_artifact: PreviewArtifactRef = Field(default_factory=PreviewArtifactRef)
    slide_count: int
    preview_metadata: Dict[str, Any] = Field(default_factory=dict)


class FrontendPresentationDocument(BaseModel):
    type: str = "presentation_preview_bundle"
    url: str = ""
    object_path: str = ""
    filename: str = ""
    title: str = ""
    bundle: Dict[str, Any] = Field(default_factory=dict)
    summary: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Story planning contracts.
# ---------------------------------------------------------------------------

PageType = Literal["cover", "agenda", "section_divider", "content", "thank_you"]
DensityLevel = Literal["low", "medium", "medium_high", "high"]
PageIntent = Literal[
    "introduce_topic",
    "frame_problem",
    "explain_solution",
    "compare_options",
    "show_architecture",
    "show_process",
    "show_roadmap",
    "show_metrics",
    "show_case",
    "ask_for_decision",
    "close_gratitude",
]
EvidenceMode = Literal[
    "headline_only",
    "supporting_text",
    "qualitative_structure",
    "structured_data",
    "visual_evidence",
]
AudienceMode = Literal["executive", "business", "mixed", "expert"]
EmphasisMode = Literal["headline", "thesis", "primary_evidence", "summary", "cta"]


class StoryPageSpec(BaseModel):
    page_id: str
    page_index: int
    page_type: PageType
    communication_goal: str
    key_message: str
    visual_intent: str
    narrative_role: str
    density_level: DensityLevel = "medium"
    page_intent: PageIntent = "explain_solution"
    evidence_mode: EvidenceMode = "supporting_text"
    audience_mode: AudienceMode = "mixed"
    emphasis: EmphasisMode = "thesis"
    speaking_mode: str = ""
    decision_stage: str = ""


class StoryDeckPlan(BaseModel):
    deck_id: str
    deck_goal: str
    target_audience: str
    presentation_context: str = ""
    language: str = "zh-CN"
    narrative_outline: List[str] = Field(default_factory=list)
    pages: List[StoryPageSpec] = Field(default_factory=list)
