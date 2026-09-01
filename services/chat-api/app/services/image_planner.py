from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.llm.factory import get_request_scoped_llm_client
from app.llm.types import Message, Role


class SectionBrief(BaseModel):
    section_id: str
    heading: str
    start: int
    end: int
    excerpt: str


class PlannedPlacement(BaseModel):
    section_id: str
    decision: Literal["use_uploaded_image", "generate_new_visual", "no_image_needed"] = "no_image_needed"
    asset_id: Optional[str] = None
    score: float = 0.0
    caption: str = ""
    rationale: str = ""
    visual_prompt: str = ""


class ImagePlanResponse(BaseModel):
    placements: List[PlannedPlacement] = Field(default_factory=list)


USER_EVIDENCE_IMAGE_SOURCES = {"embedded_docx_image", "user_upload"}


def _asset_source(asset: Dict[str, Any]) -> str:
    return str(asset.get("source") or "").strip() or "user_upload"


def _is_user_evidence_asset(asset: Dict[str, Any]) -> bool:
    return _asset_source(asset) in USER_EVIDENCE_IMAGE_SOURCES


def _tokenize_relevance_text(value: Any, *, limit: int = 28) -> List[str]:
    text = str(value or "").strip()
    if not text:
        return []
    tokens: List[str] = []
    seen = set()
    for token in re.findall(r"[\w\u4e00-\u9fff]{2,}", text):
        normalized = token.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        tokens.append(normalized)
        if len(tokens) >= limit:
            break
    return tokens


def _score_asset_for_markdown(asset: Dict[str, Any], markdown: str) -> int:
    haystack = str(markdown or "").lower()
    fields = [
        asset.get("page_area"),
        asset.get("summary"),
        asset.get("flow_relationship"),
        asset.get("source_context"),
        asset.get("filename"),
        " ".join(str(x or "") for x in list(asset.get("tags") or [])[:12]),
    ]
    score = 0
    for token in _tokenize_relevance_text(" ".join(str(x or "") for x in fields), limit=40):
        if token in haystack:
            score += 1
    if _is_user_evidence_asset(asset):
        score += 2
    return score


def _rank_assets_for_planning(
    *,
    assets: List[Dict[str, Any]],
    markdown: str,
    sections: List[SectionBrief],
) -> List[Dict[str, Any]]:
    section_count = max(1, len(sections))
    evidence_count = len([asset for asset in assets if _is_user_evidence_asset(asset)])
    candidate_limit = min(
        len(assets),
        max(24, min(48, max(section_count * 8, int(len(str(markdown or "")) / 180) + 8))),
    )
    if evidence_count > 24:
        candidate_limit = min(len(assets), max(candidate_limit, min(48, evidence_count)))

    indexed = list(enumerate(assets))
    indexed.sort(
        key=lambda item: (
            0 if _is_user_evidence_asset(item[1]) else 1,
            -_score_asset_for_markdown(item[1], markdown),
            int(item[1].get("source_order") or item[1].get("image_index") or item[0]),
        )
    )
    return [dict(asset) for _, asset in indexed[:candidate_limit]]


def build_section_briefs(markdown: str, *, max_sections: int = 10) -> List[SectionBrief]:
    text = str(markdown or "")
    if not text.strip():
        return []
    lines = text.splitlines()
    headings: List[tuple[int, str]] = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("## "):
            continue
        title = stripped[3:].strip()
        if title:
            headings.append((idx, title))
    if not headings:
        excerpt = "\n".join(lines[:16]).strip()
        return [SectionBrief(section_id="section_1", heading="正文", start=0, end=len(lines), excerpt=excerpt[:1200])]

    briefs: List[SectionBrief] = []
    for pos, (start, heading) in enumerate(headings[:max_sections], start=1):
        end = headings[pos][0] if pos < len(headings) else len(lines)
        excerpt = "\n".join(lines[start + 1:end]).strip()
        if not excerpt:
            excerpt = heading
        briefs.append(
            SectionBrief(
                section_id=f"section_{pos}",
                heading=heading,
                start=start,
                end=end,
                excerpt=excerpt[:1400],
            )
        )
    return briefs


class ImagePlannerService:
    def __init__(self) -> None:
        self._llm = get_request_scoped_llm_client(streaming=False, stage="compose", intent="generation")

    @staticmethod
    def _evidence_caption(base: str) -> str:
        token = str(base or "").strip() or "image"
        if token.startswith("证据截图："):
            return token
        return f"证据截图：{token}"

    def _fallback_layout_hints(
        self,
        *,
        uploaded_assets: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        hints: List[Dict[str, Any]] = []
        for asset in uploaded_assets[:24]:
            path = str(asset.get("path") or "").strip()
            if not path:
                continue
            source = _asset_source(asset)
            hints.append(
                {
                    "image_id": str(asset.get("asset_id") or ""),
                    "path": path,
                    "caption": self._evidence_caption(
                        str(asset.get("page_area") or asset.get("filename") or asset.get("asset_id") or "image").strip()
                    ),
                    "semantic_cues": list(asset.get("tags") or [])[:8],
                    "status_tags": list(asset.get("status_tags") or [])[:4],
                    "target_heading": "",
                    "source": source,
                    "asset_source": source,
                    "score": 0.0,
                }
            )
        return hints

    async def plan_document_images(
        self,
        *,
        markdown: str,
        user_goal: str,
        uploaded_assets: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        assets = [dict(item) for item in (uploaded_assets or []) if isinstance(item, dict)]
        if not assets:
            return {"layout_hints": [], "generated_specs": [], "plan": []}

        sections = build_section_briefs(markdown)
        if not sections:
            return {"layout_hints": self._fallback_layout_hints(uploaded_assets=assets), "generated_specs": [], "plan": []}

        planning_assets = _rank_assets_for_planning(assets=assets, markdown=markdown, sections=sections)
        compact_assets: List[Dict[str, Any]] = []
        for item in planning_assets:
            compact_assets.append(
                {
                    "asset_id": str(item.get("asset_id") or "").strip(),
                    "summary": str(item.get("summary") or "").strip(),
                    "page_area": str(item.get("page_area") or "").strip(),
                    "flow_relationship": str(item.get("flow_relationship") or "").strip(),
                    "source_context": str(item.get("source_context") or "").strip()[:900],
                    "paragraph_index": item.get("paragraph_index"),
                    "source_order": item.get("source_order"),
                    "source": str(item.get("source") or "").strip(),
                    "tags": list(item.get("tags") or [])[:12],
                    "filename": str(item.get("filename") or "").strip(),
                }
            )

        prompt_payload = {
            "user_goal": str(user_goal or "").strip(),
            "sections": [section.model_dump() for section in sections[:10]],
            "uploaded_assets": compact_assets,
            "rules": [
                "Prefer uploaded screenshots when a section is describing a real UI page, concrete interaction step, or visible system state.",
                "Use generate_new_visual only when the section clearly benefits from a visual but no uploaded screenshot fits.",
                "Use no_image_needed when the section is mostly abstract requirements, scope, goals, or policy text.",
                "Do not assign the same uploaded asset to multiple sections unless it is strongly justified.",
                "Keep captions concise and reader-facing.",
                "For embedded Word-document images, use source_context, summary, paragraph_index, source_order, and nearby text cues to place images near the section that rewrites the same case/material.",
                "For news briefs or reports, prefer screenshots whose nearby text mentions the same language desk, platform, media outlet, title, person, or case described by the section.",
            ],
        }

        try:
            response = await self._llm.ainvoke_structured(
                [
                    Message(
                        role=Role.SYSTEM,
                        content=(
                            "You are an image planning engine for generated documents. "
                            "Map uploaded or source-document screenshots to the most suitable document sections. "
                            "Return JSON only via the schema."
                        ),
                    ),
                    Message(role=Role.USER, content=json.dumps(prompt_payload, ensure_ascii=False, indent=2)),
                ],
                ImagePlanResponse,
            )
        except Exception:
            return {
                "layout_hints": self._fallback_layout_hints(uploaded_assets=assets),
                "generated_specs": [],
                "plan": [],
            }

        section_map = {section.section_id: section for section in sections}
        asset_map = {
            str(item.get("asset_id") or "").strip(): item
            for item in planning_assets
            if str(item.get("asset_id") or "").strip()
        }
        layout_hints: List[Dict[str, Any]] = []
        generated_specs: List[Dict[str, Any]] = []
        normalized_plan: List[Dict[str, Any]] = []
        used_assets = set()

        for placement in list(response.placements or [])[:16]:
            section = section_map.get(str(placement.section_id or "").strip())
            if not section:
                continue
            decision = str(placement.decision or "no_image_needed").strip()
            normalized_plan.append(placement.model_dump())
            if decision == "use_uploaded_image":
                asset_id = str(placement.asset_id or "").strip()
                asset = asset_map.get(asset_id)
                if not asset or asset_id in used_assets:
                    continue
                path = str(asset.get("path") or "").strip()
                if not path:
                    continue
                caption = self._evidence_caption(
                    str(placement.caption or asset.get("page_area") or asset.get("filename") or asset_id).strip()
                )
                tags = list(asset.get("tags") or [])[:10]
                source = _asset_source(asset)
                hint = {
                    "image_id": asset_id,
                    "path": path,
                    "caption": caption or asset_id,
                    "semantic_cues": list(dict.fromkeys(([section.heading] + tags)))[:10],
                    "status_tags": list(asset.get("status_tags") or [])[:4],
                    "target_heading": section.heading,
                    "source": source,
                    "asset_source": source,
                    "score": float(placement.score or 0.0),
                    "rationale": str(placement.rationale or "").strip(),
                }
                layout_hints.append(hint)
                used_assets.add(asset_id)
            elif decision == "generate_new_visual":
                prompt = str(placement.visual_prompt or "").strip()
                if not prompt:
                    prompt = (
                        "Create one clean PRD support visual for this section. "
                        "Use concise labels and keep the semantics aligned with the section.\n\n"
                        f"Section: {section.heading}\n\n{section.excerpt[:1200]}"
                    )
                generated_specs.append(
                    {
                        "start": section.start + 1,
                        "end": section.end,
                        "label": "planned_visual",
                        "heading": f"## {section.heading}",
                        "prompt": prompt,
                    }
                )

        for asset in planning_assets:
            asset_id = str(asset.get("asset_id") or "").strip()
            if not asset_id or asset_id in used_assets:
                continue
            path = str(asset.get("path") or "").strip()
            if not path:
                continue
            source = _asset_source(asset)
            layout_hints.append(
                {
                    "image_id": asset_id,
                    "path": path,
                    "caption": self._evidence_caption(
                        str(asset.get("page_area") or asset.get("filename") or asset_id).strip()
                    ),
                    "semantic_cues": list(asset.get("tags") or [])[:10],
                    "status_tags": list(asset.get("status_tags") or [])[:4],
                    "target_heading": "",
                    "source": source,
                    "asset_source": source,
                    "score": 0.0,
                    "rationale": "preserve_uploaded_evidence_asset",
                }
            )
            used_assets.add(asset_id)

        if not layout_hints and not generated_specs:
            layout_hints = self._fallback_layout_hints(uploaded_assets=assets)

        return {
            "layout_hints": layout_hints,
            "generated_specs": generated_specs,
            "plan": normalized_plan,
        }
_image_planner_service: Optional[ImagePlannerService] = None


def get_image_planner_service() -> ImagePlannerService:
    global _image_planner_service
    if _image_planner_service is None:
        _image_planner_service = ImagePlannerService()
    return _image_planner_service
