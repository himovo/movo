from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from app.llm.types import Message, Role
from pydantic import BaseModel, Field

from app.llm.factory import get_request_scoped_llm_client


class _GateExtract(BaseModel):
    style_score: float = 0.0
    structure_score: float = 0.0
    evidence_score: float = 0.0
    visual_score: float = 0.0
    passed: bool = False
    issues: List[str] = Field(default_factory=list)


class OutputStyleGate:
    def __init__(self) -> None:
        self._llm = get_request_scoped_llm_client(streaming=False, stage="editorial", intent="generation")

    def _fallback(self, *, content: str, prompt_contract: Dict[str, Any]) -> Dict[str, Any]:
        text = str(content or "")
        structure_axes = dict(prompt_contract.get("structure_axes") or {})
        evidence_axes = dict(prompt_contract.get("evidence_axes") or {})
        visual_axes = dict(prompt_contract.get("visual_axes") or {})
        rb = [str(x).strip() for x in (structure_axes.get("required_blocks") or []) if str(x).strip()]
        hits = 0
        lower = text.lower()
        for b in rb:
            if b and b.lower() in lower:
                hits += 1
        structure_score = (hits / max(1, len(rb))) if rb else 0.8
        evidence_required = bool(evidence_axes.get("citation_required"))
        has_ref = bool(re.search(r"\[\d+\]|参考|reference|source", text, flags=re.IGNORECASE))
        evidence_score = 1.0 if (not evidence_required or has_ref) else 0.4
        required_visual = int(visual_axes.get("required_total") or 0)
        image_count = len(re.findall(r"!\[[^\]]*\]\([^)]+\)", text))
        visual_score = 1.0 if required_visual <= 0 else min(1.0, image_count / max(1, required_visual))
        style_score = 0.75
        passed = structure_score >= 0.72 and evidence_score >= 0.6 and visual_score >= 0.6
        issues = []
        if structure_score < 0.72:
            issues.append("structure_coverage_low")
        if evidence_score < 0.6:
            issues.append("evidence_coverage_low")
        if visual_score < 0.6:
            issues.append("visual_coverage_low")
        return {
            "style_score": style_score,
            "structure_score": structure_score,
            "evidence_score": evidence_score,
            "visual_score": visual_score,
            "passed": passed,
            "issues": issues,
        }

    async def evaluate(self, *, content: str, prompt_contract: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "prompt_contract": prompt_contract,
            "content": str(content or "")[:10000],
        }
        system = (
            "Evaluate whether the content satisfies prompt_contract. "
            "Return strict JSON: style_score, structure_score, evidence_score, visual_score, passed, issues."
        )
        try:
            model = self._llm.with_structured_output(_GateExtract, method="function_calling")
            res = await model.ainvoke(
                [
                    Message(role=Role.SYSTEM, content=system),
                    Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False, default=str)),
                ]
            )
            if isinstance(res, _GateExtract):
                out = {
                    "style_score": max(0.0, min(1.0, float(res.style_score or 0.0))),
                    "structure_score": max(0.0, min(1.0, float(res.structure_score or 0.0))),
                    "evidence_score": max(0.0, min(1.0, float(res.evidence_score or 0.0))),
                    "visual_score": max(0.0, min(1.0, float(res.visual_score or 0.0))),
                    "passed": bool(res.passed),
                    "issues": [str(x) for x in (res.issues or []) if str(x).strip()],
                }
                return out
        except Exception:
            pass
        return self._fallback(content=content, prompt_contract=prompt_contract)
