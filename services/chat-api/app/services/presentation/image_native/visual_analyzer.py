from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, List, Tuple

from app.llm.configured_multimodal import ConfiguredMultimodalClient
from app.services.presentation.image_native.contracts import VisualRegionAnalysis, VisualSemanticAnalysis
from app.services.presentation.image_native.prompt_builder import (
    build_visual_detail_analysis_prompt,
    build_visual_region_analysis_prompt,
    build_visual_analysis_prompt,
    build_visual_analysis_repair_prompt,
)

logger = logging.getLogger(__name__)

_SCHEMATIC_ROLE_HINTS = (
    "mlp",
    "cnn",
    "rnn",
    "transformer",
    "neural",
    "network",
    "topology",
    "layer",
    "schematic",
    "architecture",
    "perceptron",
)


class VisualSemanticAnalyzer:
    def __init__(self) -> None:
        self._client = ConfiguredMultimodalClient()

    async def _emit_progress(
        self,
        progress_callback: Callable[[Dict[str, Any]], Awaitable[None] | None] | None,
        payload: Dict[str, Any],
    ) -> None:
        if progress_callback is None:
            return
        result = progress_callback(dict(payload or {}))
        if hasattr(result, "__await__"):
            await result

    async def analyze(
        self,
        *,
        page_plan: Dict[str, Any],
        image_bytes: bytes,
        user_id: str,
        session_id: str,
        progress_callback: Callable[[Dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> VisualSemanticAnalysis:
        await self._emit_progress(
            progress_callback,
            {
                "stage": "coarse_region_analysis",
                "status": "running",
                "page_id": str(page_plan.get("page_id") or ""),
                "message": "开始粗分析：识别页面区域、复杂度与重建策略",
            },
        )
        coarse_payload = await self._client.call_json(
            prompt=build_visual_region_analysis_prompt(page_plan=page_plan),
            image_bytes=image_bytes,
            stage="presentation_image_native_visual_region_analysis",
            intent="generation",
            user_id=user_id,
            session_id=session_id,
            request_payload_extra={"page_id": str(page_plan.get("page_id") or "")},
        )
        coarse = VisualRegionAnalysis.model_validate(coarse_payload)
        coarse = _normalize_region_strategies(coarse)
        await self._emit_progress(
            progress_callback,
            {
                "stage": "coarse_region_analysis",
                "status": "completed",
                "page_id": str(page_plan.get("page_id") or ""),
                "region_count": len(list(coarse.regions or [])),
                "coarse_region_analysis": coarse.model_dump(),
                "message": f"粗分析完成：共识别 {len(list(coarse.regions or []))} 个区域",
            },
        )

        await self._emit_progress(
            progress_callback,
            {
                "stage": "detail_visual_analysis",
                "status": "running",
                "page_id": str(page_plan.get("page_id") or ""),
                "region_count": len(list(coarse.regions or [])),
                "message": f"开始细分析：按区域复杂度拆解可编辑元素（{len(list(coarse.regions or []))} 个区域）",
            },
        )
        merged_analysis = _seed_analysis_from_coarse(page_plan=page_plan, coarse=coarse)
        total_regions = len(list(coarse.regions or []))
        for index, region in enumerate(list(coarse.regions or []), start=1):
            region_label = str(region.semantic_role or region.region_type or region.id or f"region_{index}").strip()
            await self._emit_progress(
                progress_callback,
                {
                    "stage": "detail_visual_region_analysis",
                    "status": "running",
                    "page_id": str(page_plan.get("page_id") or ""),
                    "region_id": str(region.id or ""),
                    "region_index": index,
                    "region_total": total_regions,
                    "region_type": str(region.region_type or ""),
                    "region_complexity": str(region.complexity or ""),
                    "message": f"开始细分析区域 {index}/{total_regions}：{region_label}",
                },
            )
            payload = await self._client.call_json(
                prompt=build_visual_detail_analysis_prompt(
                    page_plan=page_plan,
                    coarse_region_analysis=coarse.model_dump(),
                    focus_region=region.model_dump(),
                ),
                image_bytes=image_bytes,
                stage="presentation_image_native_visual_analysis_region",
                intent="generation",
                user_id=user_id,
                session_id=f"{session_id}::{str(region.id or index)}",
                request_payload_extra={
                    "page_id": str(page_plan.get("page_id") or ""),
                    "region_id": str(region.id or ""),
                    "region_index": index,
                    "region_total": total_regions,
                    "region_type": str(region.region_type or ""),
                    "region_complexity": str(region.complexity or ""),
                },
            )
            region_analysis = VisualSemanticAnalysis.model_validate(payload)
            merged_analysis = _merge_analysis_parts(base=merged_analysis, part=region_analysis, fallback_region=region)
            await self._emit_progress(
                progress_callback,
                {
                    "stage": "detail_visual_region_analysis",
                    "status": "completed",
                    "page_id": str(page_plan.get("page_id") or ""),
                    "region_id": str(region.id or ""),
                    "region_index": index,
                    "region_total": total_regions,
                    "region_type": str(region.region_type or ""),
                    "region_complexity": str(region.complexity or ""),
                    "region_label": region_label,
                    "region_visual_analysis": region_analysis.model_dump(),
                    "merged_visual_analysis": merged_analysis.model_dump(),
                    "element_count": len(list(region_analysis.elements or [])),
                    "text_count": len(list(region_analysis.text_elements or [])),
                    "message": (
                        f"区域 {index}/{total_regions} 细分析完成：{region_label} "
                        f"（{len(list(region_analysis.elements or []))} 个元素 / "
                        f"{len(list(region_analysis.text_elements or []))} 个文本）"
                    ),
                },
            )

        analysis = merged_analysis
        if not list(analysis.regions or []):
            analysis.regions = list(coarse.regions or [])
        await self._emit_progress(
            progress_callback,
            {
                "stage": "detail_visual_analysis",
                "status": "completed",
                "page_id": str(page_plan.get("page_id") or ""),
                "element_count": len(list(analysis.elements or [])),
                "text_count": len(list(analysis.text_elements or [])),
                "visual_analysis": analysis.model_dump(),
                "message": f"细分析完成：{len(list(analysis.elements or []))} 个元素 / {len(list(analysis.text_elements or []))} 个文本",
            },
        )
        issues = detect_visual_analysis_gaps(analysis)
        if not issues:
            return analysis
        if _should_keep_analysis_without_repair(issues):
            logger.info(
                "presentation_image_native_visual_analysis_repair_skipped page_id=%s issues=%s",
                str(page_plan.get("page_id") or ""),
                issues,
            )
            return analysis

        logger.info(
            "presentation_image_native_visual_analysis_retry page_id=%s issues=%s",
            str(page_plan.get("page_id") or ""),
            issues,
        )
        await self._emit_progress(
            progress_callback,
            {
                "stage": "detail_visual_analysis_repair",
                "status": "running",
                "page_id": str(page_plan.get("page_id") or ""),
                "issues": list(issues),
                "message": f"分析结果需要修复：{len(list(issues))} 个问题",
            },
        )
        repaired_payload = await self._client.call_json(
            prompt=build_visual_analysis_repair_prompt(
                page_plan=page_plan,
                prior_analysis={"coarse_regions": coarse.model_dump(), "detailed_analysis": analysis.model_dump()},
                issues=issues,
            ),
            image_bytes=image_bytes,
            stage="presentation_image_native_visual_analysis_repair",
            intent="generation",
            user_id=user_id,
            session_id=session_id,
            request_payload_extra={"page_id": str(page_plan.get("page_id") or ""), "repair_issues": issues},
        )
        repaired = VisualSemanticAnalysis.model_validate(repaired_payload)
        if not list(repaired.regions or []):
            repaired.regions = list(coarse.regions or [])
        if _repair_regresses_analysis(original=analysis, repaired=repaired):
            logger.warning(
                "presentation_image_native_visual_analysis_repair_rejected page_id=%s original_elements=%s original_texts=%s repaired_elements=%s repaired_texts=%s",
                str(page_plan.get("page_id") or ""),
                len(list(analysis.elements or [])),
                len(list(analysis.text_elements or [])),
                len(list(repaired.elements or [])),
                len(list(repaired.text_elements or [])),
            )
            return analysis
        await self._emit_progress(
            progress_callback,
            {
                "stage": "detail_visual_analysis_repair",
                "status": "completed",
                "page_id": str(page_plan.get("page_id") or ""),
                "element_count": len(list(repaired.elements or [])),
                "text_count": len(list(repaired.text_elements or [])),
                "visual_analysis_repaired": repaired.model_dump(),
                "message": f"修复分析完成：{len(list(repaired.elements or []))} 个元素 / {len(list(repaired.text_elements or []))} 个文本",
            },
        )
        repaired_issues = detect_visual_analysis_gaps(repaired)
        if repaired_issues:
            logger.warning(
                "presentation_image_native_visual_analysis_repair_incomplete page_id=%s issues=%s",
                str(page_plan.get("page_id") or ""),
                repaired_issues,
            )
        return repaired


def _repair_regresses_analysis(*, original: VisualSemanticAnalysis, repaired: VisualSemanticAnalysis) -> bool:
    """Reject repair results that accidentally erase a useful analysis.

    The repair pass is allowed to reduce noisy over-decomposition, but it must
    not collapse a previously detailed content-page analysis back to regions
    only. That failure mode produces an almost blank reconstructed page.
    """
    original_elements = len(list(original.elements or []))
    original_texts = len(list(original.text_elements or []))
    original_groups = len(list(original.groups or []))
    repaired_elements = len(list(repaired.elements or []))
    repaired_texts = len(list(repaired.text_elements or []))
    repaired_groups = len(list(repaired.groups or []))

    if original_elements + original_texts < 12:
        return False
    if repaired_elements + repaired_texts == 0:
        return True
    if original_elements >= 20 and repaired_elements < max(6, int(original_elements * 0.35)):
        return True
    if original_texts >= 8 and repaired_texts < max(3, int(original_texts * 0.35)):
        return True
    if original_groups >= 4 and repaired_groups == 0:
        return True
    return False


def _should_keep_analysis_without_repair(issues: List[str]) -> bool:
    """Avoid risky repair calls for minor soft-budget overages.

    A slightly over-budget editable analysis is preferable to an LLM repair pass
    that may over-compress or erase content. Hard structural gaps still repair.
    """
    normalized = [str(issue or "").strip() for issue in list(issues or []) if str(issue or "").strip()]
    if len(normalized) != 1:
        return False
    issue = normalized[0]
    if not issue.startswith("element_budget_exceeded:"):
        return False
    try:
        count = int(issue.split(":", 1)[1])
    except Exception:
        return False
    return count <= 140


def detect_visual_analysis_gaps(analysis: VisualSemanticAnalysis) -> List[str]:
    issues: List[str] = []
    element_ids = {str(elem.id or "").strip() for elem in list(analysis.elements or []) if str(elem.id or "").strip()}
    group_children, diagram_groups = _group_child_context(analysis)
    regions = list(getattr(analysis, "regions", []) or [])

    missing_icon_children = [
        child_id
        for child_id in group_children
        if child_id.startswith("icon_") and child_id not in element_ids
    ]
    if missing_icon_children:
        issues.append(f"missing_icon_elements:{','.join(missing_icon_children[:20])}")

    missing_timeline_markers = [
        child_id
        for child_id in group_children
        if child_id.startswith("timeline_dot_") and child_id not in element_ids
    ]
    if missing_timeline_markers:
        issues.append(f"missing_timeline_markers:{','.join(missing_timeline_markers[:20])}")

    elements_by_group: Dict[str, List[str]] = {}
    for elem in list(analysis.elements or []):
        group_id = str(elem.group_id or "").strip()
        if not group_id:
            continue
        elements_by_group.setdefault(group_id, []).append(str(elem.type or "").strip().lower())

    for group_id, group_role in diagram_groups:
        if _is_dense_topology_group(group_id=group_id, group_role=group_role, regions=regions):
            continue
        child_types = elements_by_group.get(group_id, [])
        has_internal_structure = any(elem_type in {"circle", "line", "icon"} for elem_type in child_types)
        if not has_internal_structure:
            issues.append(f"diagram_group_missing_internal_elements:{group_id}:{group_role}")

    total_elements = len(list(analysis.elements or []))
    if total_elements > 90:
        issues.append(f"element_budget_exceeded:{total_elements}")

    return issues


def _normalize_region_strategies(coarse: VisualRegionAnalysis) -> VisualRegionAnalysis:
    """Clamp obviously wrong region strategies before detailed analysis.

    Dense technical schematics like MLP / CNN / transformer diagrams are still
    worth reconstructing as editable diagrams; they should not fall through to
    abstract mode just because they contain many links. We keep the rule
    generalized by using role/type hints rather than image-specific ids.
    """
    out = coarse.model_copy(deep=True)
    normalized = []
    for region in list(out.regions or []):
        role_text = " ".join(
            [
                str(region.id or ""),
                str(region.region_type or ""),
                str(region.semantic_role or ""),
                str(region.notes or ""),
                " ".join(str(x or "") for x in list(region.expected_element_types or [])),
            ]
        ).lower()
        if (
            str(region.complexity or "").strip().lower() == "dense_topology"
            and str(region.analysis_strategy or "").strip().lower() == "abstract"
            and any(hint in role_text for hint in _SCHEMATIC_ROLE_HINTS)
        ):
            region.analysis_strategy = "skeletal"
            expected = [str(x or "").strip().lower() for x in list(region.expected_element_types or [])]
            for needed in ("circle", "line", "text"):
                if needed not in expected:
                    expected.append(needed)
            region.expected_element_types = expected
        normalized.append(region)
    out.regions = normalized
    return out


def _group_child_context(analysis: VisualSemanticAnalysis) -> Tuple[List[str], List[Tuple[str, str]]]:
    child_ids: List[str] = []
    diagram_groups: List[Tuple[str, str]] = []
    for group in list(analysis.groups or []):
        group_id = str(group.id or "").strip()
        group_type = str(group.group_type or "").strip().lower()
        semantic_role = str(group.semantic_role or "").strip().lower()
        notes = str(group.notes or "").strip().lower()
        for child_id in list(group.child_ids or []):
            raw = str(child_id or "").strip()
            if raw:
                child_ids.append(raw)
        if group_type == "diagram_region" and any(token in f"{semantic_role} {notes}" for token in ("mlp", "network", "diagram", "schematic", "neural")):
            diagram_groups.append((group_id, semantic_role or notes or group_type))
    return child_ids, diagram_groups


def _is_dense_topology_group(*, group_id: str, group_role: str, regions: List[Any]) -> bool:
    lowered_role = str(group_role or "").strip().lower()
    if any(token in lowered_role for token in ("mlp", "network", "neural", "topology")):
        for region in regions:
            region_role = str(getattr(region, "semantic_role", "") or "").strip().lower()
            strategy = str(getattr(region, "analysis_strategy", "") or "").strip().lower()
            complexity = str(getattr(region, "complexity", "") or "").strip().lower()
            related = {str(item or "").strip() for item in list(getattr(region, "related_group_ids", []) or [])}
            if group_id and related and group_id in related:
                return complexity == "dense_topology" or strategy in {"skeletal", "abstract"}
            if any(token in region_role for token in ("mlp", "network", "neural", "topology")) and (
                complexity == "dense_topology" or strategy in {"skeletal", "abstract"}
            ):
                return True
    return False


def _seed_analysis_from_coarse(*, page_plan: Dict[str, Any], coarse: VisualRegionAnalysis) -> VisualSemanticAnalysis:
    return VisualSemanticAnalysis(
        page_id=str(page_plan.get("page_id") or coarse.page_id or ""),
        canvas=dict(coarse.canvas or {"w": 1600, "h": 900, "aspect": "16:9"}),
        style=dict(coarse.style or {}),
        layout=dict(coarse.layout or {}),
        regions=list(coarse.regions or []),
        reconstruction_notes=list(coarse.reconstruction_notes or []),
        risks=list(coarse.risks or []),
    )


def _merge_analysis_parts(
    *,
    base: VisualSemanticAnalysis,
    part: VisualSemanticAnalysis,
    fallback_region: Any | None = None,
) -> VisualSemanticAnalysis:
    if dict(part.style or {}):
        base.style = dict(part.style or {})
    if dict(part.layout or {}):
        base.layout = dict(part.layout or {})
    base.elements = _merge_items(base.elements, part.elements)
    base.text_elements = _merge_items(base.text_elements, part.text_elements)
    base.groups = _merge_items(base.groups, part.groups)
    base.relationships = _merge_relationships(base.relationships, part.relationships)
    base.image_assets = _merge_dict_items(base.image_assets, part.image_assets)
    base.reconstruction_notes = _merge_scalar_list(base.reconstruction_notes, part.reconstruction_notes)
    base.risks = _merge_scalar_list(base.risks, part.risks)
    part_regions = list(part.regions or [])
    if part_regions:
        base.regions = _merge_items(base.regions, part_regions)
    elif fallback_region is not None:
        base.regions = _merge_items(base.regions, [fallback_region])
    return base


def _merge_items(existing: List[Any] | None, incoming: List[Any] | None) -> List[Any]:
    merged: Dict[str, Any] = {}
    ordered: List[Any] = []
    for item in list(existing or []) + list(incoming or []):
        item_id = str(getattr(item, "id", "") or "").strip()
        if item_id:
            if item_id in merged:
                for idx, prior in enumerate(ordered):
                    prior_id = str(getattr(prior, "id", "") or "").strip()
                    if prior_id == item_id:
                        ordered[idx] = item
                        break
            else:
                ordered.append(item)
            merged[item_id] = item
            continue
        ordered.append(item)
    return ordered


def _merge_relationships(existing: List[Any] | None, incoming: List[Any] | None) -> List[Any]:
    seen: set[tuple[str, str, str]] = set()
    ordered: List[Any] = []
    for item in list(existing or []) + list(incoming or []):
        key = (
            str(getattr(item, "source_id", "") or "").strip(),
            str(getattr(item, "target_id", "") or "").strip(),
            str(getattr(item, "relation_type", "") or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    return ordered


def _merge_dict_items(existing: List[Dict[str, Any]] | None, incoming: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    ordered: List[Dict[str, Any]] = []
    for item in list(existing or []) + list(incoming or []):
        item_dict = dict(item or {})
        item_id = str(item_dict.get("id") or "").strip()
        if item_id:
            if item_id in by_id:
                for idx, prior in enumerate(ordered):
                    if str((prior or {}).get("id") or "").strip() == item_id:
                        ordered[idx] = item_dict
                        break
            else:
                ordered.append(item_dict)
            by_id[item_id] = item_dict
            continue
        ordered.append(item_dict)
    return ordered


def _merge_scalar_list(existing: List[str] | None, incoming: List[str] | None) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for item in list(existing or []) + list(incoming or []):
        raw = str(item or "").strip()
        if not raw or raw in seen:
            continue
        seen.add(raw)
        ordered.append(raw)
    return ordered
