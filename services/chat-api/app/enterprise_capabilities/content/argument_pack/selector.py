from __future__ import annotations

from typing import Any, Dict, List, Sequence


class ArgumentPackSelector:
    def select_for_section(
        self,
        *,
        argument_pack: Dict[str, Any],
        title: str,
        objective: str,
        evidence_focus: Sequence[str],
        limit: int = 6,
    ) -> List[Dict[str, Any]]:
        buckets = [
            ("definitions", list(argument_pack.get("definitions") or [])),
            ("boundaries", list(argument_pack.get("boundaries") or [])),
            ("use_cases", list(argument_pack.get("use_cases") or [])),
            ("relationships", list(argument_pack.get("relationships") or [])),
        ]
        anchors = [str(title or "").strip(), str(objective or "").strip()] + [str(x).strip() for x in list(evidence_focus or []) if str(x).strip()]
        anchors = [x.lower() for x in anchors if x][:10]

        scored: List[Dict[str, Any]] = []
        for bucket_name, items in buckets:
            for item in items:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("label") or "").strip()
                summary = str(item.get("summary") or "").strip()
                hay = f"{label}\n{summary}".lower()
                score = 0
                for anchor in anchors:
                    if anchor and anchor in hay:
                        score += 3
                if bucket_name == "definitions" and any(tok in hay for tok in ["定义", "definition", "what is"]):
                    score += 1
                if bucket_name == "relationships" and any(tok in hay for tok in ["关系", "协作", "relationship", "connect"]):
                    score += 1
                if bucket_name == "use_cases" and any(tok in hay for tok in ["场景", "案例", "use case", "workflow"]):
                    score += 1
                if score <= 0 and anchors:
                    continue
                scored.append(
                    {
                        "bucket": bucket_name,
                        "label": label,
                        "summary": summary[:240],
                        "sources": list(item.get("sources") or [])[:4],
                        "score": score,
                    }
                )

        if not scored:
            fallback: List[Dict[str, Any]] = []
            for bucket_name, items in buckets:
                for item in items[:2]:
                    if not isinstance(item, dict):
                        continue
                    fallback.append(
                        {
                            "bucket": bucket_name,
                            "label": str(item.get("label") or "").strip(),
                            "summary": str(item.get("summary") or "").strip()[:240],
                            "sources": list(item.get("sources") or [])[:4],
                            "score": 0,
                        }
                    )
            return fallback[:limit]

        scored.sort(key=lambda x: (int(x.get("score") or 0), len(str(x.get("summary") or ""))), reverse=True)
        out: List[Dict[str, Any]] = []
        seen = set()
        for item in scored:
            key = (str(item.get("bucket") or ""), str(item.get("label") or ""), str(item.get("summary") or ""))
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
            if len(out) >= limit:
                break
        return out
