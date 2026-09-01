from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

from app.enterprise_capabilities.content.capability_ops import capability_family


_CONTENT_CAPABILITIES = {
    "file.transform_content",
    "file.generate_table",
}

_TEXT_PATHS = (
    "final_publish_markdown",
    "publish_assembly.final_markdown",
    "final_markdown",
    "report_markdown",
    "article_markdown",
    "edited_markdown",
    "transformed_markdown",
    "markdown_table",
    "markdown",
    "answer",
    "final_answer",
    "content",
)


@dataclass
class WorkflowContentContribution:
    node_id: str
    title: str
    effect: str
    markdown: str


@dataclass
class WorkflowContentAssembly:
    final_markdown: str
    contributions: List[WorkflowContentContribution] = field(default_factory=list)

    def as_artifact(self) -> Dict[str, Any]:
        return {
            "body_markdown": self.final_markdown,
            "final_markdown": self.final_markdown,
            "contributions": [
                {
                    "node_id": item.node_id,
                    "title": item.title,
                    "effect": item.effect,
                    "chars": len(item.markdown),
                }
                for item in self.contributions
            ],
        }


def assemble_workflow_content(
    *,
    output_spec: Dict[str, Any],
    nodes: Sequence[Any],
    graph_artifacts: Dict[str, Any],
) -> WorkflowContentAssembly | None:
    """Assemble reader-facing workflow node outputs into one final markdown body.

    This intentionally does not inspect tool/search/KB raw evidence. Those nodes
    remain evidence sources; only explicit content-producing workflow nodes can
    contribute to the final document body.
    """

    if not _workflow_selected(output_spec=output_spec, nodes=nodes):
        return None

    contributions: List[WorkflowContentContribution] = []
    for node in list(nodes or []):
        node_id = str(getattr(node, "node_id", "") or "").strip()
        if not node_id:
            continue
        meta = getattr(node, "meta", None) if isinstance(getattr(node, "meta", None), dict) else {}
        cap = str(meta.get("capability_id") or "").strip()
        if not _is_content_node(cap):
            continue
        artifact = graph_artifacts.get(node_id)
        if not isinstance(artifact, dict):
            continue
        text = _extract_markdown(artifact)
        if not text:
            continue
        effect = _content_effect(node=node, meta=meta, cap=cap, has_primary=any(c.effect == "primary" for c in contributions))
        if effect in {"supporting", "evidence", "ignore", "attach", "attachment"}:
            continue
        title = _contribution_title(node=node, meta=meta)
        contributions.append(
            WorkflowContentContribution(
                node_id=node_id,
                title=title,
                effect=effect,
                markdown=text,
            )
        )

    if len(contributions) < 2 and not any(item.effect in {"append", "replace", "patch"} for item in contributions):
        return None

    final = _compose_markdown(contributions)
    if not final:
        return None
    return WorkflowContentAssembly(final_markdown=final, contributions=contributions)


def _workflow_selected(*, output_spec: Dict[str, Any], nodes: Sequence[Any]) -> bool:
    selected = output_spec.get("selected_skill") if isinstance(output_spec.get("selected_skill"), dict) else {}
    if _is_workflow_skill(selected):
        return True
    for node in list(nodes or []):
        meta = getattr(node, "meta", None) if isinstance(getattr(node, "meta", None), dict) else {}
        selected = meta.get("selected_skill") if isinstance(meta.get("selected_skill"), dict) else {}
        if _is_workflow_skill(selected):
            return True
    return False


def _is_workflow_skill(skill: Dict[str, Any]) -> bool:
    skill_type = str(skill.get("skill_type") or "").strip().lower()
    role = str(skill.get("role") or "").strip().lower()
    return skill_type == "composite_task" or role in {"execution", "browser"}


def _is_content_node(capability_id: str) -> bool:
    cap = str(capability_id or "").strip()
    return capability_family(cap) == "generation" or cap in _CONTENT_CAPABILITIES


def _content_effect(*, node: Any, meta: Dict[str, Any], cap: str, has_primary: bool) -> str:
    workflow_step = meta.get("workflow_step") if isinstance(meta.get("workflow_step"), dict) else {}
    semantic = meta.get("semantic_config") if isinstance(meta.get("semantic_config"), dict) else {}
    if not semantic and isinstance(workflow_step.get("semantic_config"), dict):
        semantic = dict(workflow_step.get("semantic_config") or {})
    raw = (
        semantic.get("contentEffect")
        or semantic.get("content_effect")
        or semantic.get("deliveryRole")
        or semantic.get("delivery_role")
        or semantic.get("publishRole")
        or semantic.get("publish_role")
        or ""
    )
    effect = str(raw or "").strip().lower()
    aliases = {
        "main": "primary",
        "body": "primary",
        "final": "primary",
        "section": "append",
        "appendix": "append",
        "attachment": "attach",
    }
    effect = aliases.get(effect, effect)
    if effect:
        return effect
    if cap == "file.generate_table":
        return "append"
    if cap == "file.transform_content":
        return "append"
    return "append" if has_primary else "primary"


def _contribution_title(*, node: Any, meta: Dict[str, Any]) -> str:
    workflow_step = meta.get("workflow_step") if isinstance(meta.get("workflow_step"), dict) else {}
    for value in (
        workflow_step.get("output_alias"),
        workflow_step.get("title"),
        getattr(node, "goal", ""),
        getattr(node, "node_id", ""),
    ):
        text = str(value or "").strip()
        if text:
            return text[:80]
    return "补充内容"


def _extract_markdown(artifact: Dict[str, Any]) -> str:
    for path in _TEXT_PATHS:
        value = _nested_value(artifact, path)
        if isinstance(value, str):
            text = _clean_text(value)
            if text:
                return text
    return ""


def _nested_value(obj: Dict[str, Any], path: str) -> Any:
    cur: Any = obj
    for part in [item for item in str(path or "").split(".") if item]:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _clean_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if _looks_like_json_payload(text):
        return ""
    return text


def _looks_like_json_payload(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    if raw[0] in "[{" and raw[-1:] in "]}":
        return True
    return bool(re.match(r"^```json\s*[\[{]", raw, flags=re.IGNORECASE))


def _compose_markdown(contributions: List[WorkflowContentContribution]) -> str:
    parts: List[str] = []
    seen: set[str] = set()
    for item in contributions:
        body = item.markdown.strip()
        if not body or body in seen:
            continue
        seen.add(body)
        if item.effect == "primary":
            parts.append(body)
            continue
        if re.match(r"^\s{0,3}#{1,6}\s+", body):
            parts.append(body)
        else:
            parts.append(f"## {item.title}\n\n{body}")
    return "\n\n".join(part.strip() for part in parts if part.strip()).strip()
