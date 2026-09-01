from __future__ import annotations
from app.infrastructure.observability.config import log_print

import json
from typing import Any, Dict, List

from app.enterprise_capabilities.content.argument_pack.contracts import ArgumentItem, ArgumentPackSpec


class ArgumentPackBuilder:
    def build(
        self,
        *,
        output_spec: Dict[str, Any],
        tool_observations: List[Dict[str, Any]],
        content_plan: Dict[str, Any],
    ) -> ArgumentPackSpec:
        observations = [item for item in list(tool_observations or []) if isinstance(item, dict)]
        definitions: List[ArgumentItem] = []
        boundaries: List[ArgumentItem] = []
        use_cases: List[ArgumentItem] = []
        relationships: List[ArgumentItem] = []
        references: List[Dict[str, Any]] = []

        for obs in observations[:20]:
            summary = str(
                obs.get("summary")
                or obs.get("content")
                or obs.get("snippet")
                or obs.get("text")
                or ""
            ).strip()
            query = str(obs.get("query") or "").strip()
            sources = self._extract_sources(obs)
            if summary:
                definitions.append(ArgumentItem(label=query or "definition", summary=summary[:240], sources=sources))
                use_cases.append(ArgumentItem(label=query or "use_case", summary=summary[:240], sources=sources))
            if query:
                boundaries.append(ArgumentItem(label=query, summary=f"边界与限制：{summary[:180]}", sources=sources))
                relationships.append(ArgumentItem(label=query, summary=f"关系线索：{summary[:180]}", sources=sources))
            for src in obs.get("sources") or []:
                if isinstance(src, dict):
                    references.append(
                        {
                            "title": str(src.get("title") or src.get("name") or "").strip(),
                            "url": str(src.get("url") or src.get("source_url") or "").strip(),
                        }
                    )

        plan_sections = [item for item in list((content_plan or {}).get("sections") or []) if isinstance(item, dict)]
        if not definitions and plan_sections:
            for sec in plan_sections[:4]:
                title = str(sec.get("title") or "").strip()
                purpose = str(sec.get("purpose") or "").strip()
                definitions.append(ArgumentItem(label=title, summary=purpose, sources=[]))

        pack = ArgumentPackSpec(
            definitions=definitions[:8],
            boundaries=boundaries[:8],
            use_cases=use_cases[:8],
            relationships=relationships[:8],
            references=self._dedupe_refs(references)[:20],
            metadata={
                "source": "observation_fallback_builder",
                "observation_count": len(observations),
                "planned_sections": len(plan_sections),
            },
        )
        self._log_pack(pack)
        return pack

    @staticmethod
    def _extract_sources(obs: Dict[str, Any]) -> List[str]:
        out: List[str] = []
        for src in list(obs.get("sources") or [])[:6]:
            if isinstance(src, dict):
                url = str(src.get("url") or src.get("source_url") or "").strip()
                if url:
                    out.append(url)
        return out

    @staticmethod
    def _dedupe_refs(refs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        seen = set()
        for item in refs:
            url = str(item.get("url") or "").strip()
            key = url or json.dumps(item, ensure_ascii=False, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    @staticmethod
    def _log_pack(pack: ArgumentPackSpec) -> None:
        try:
            log_print(
                "[argument_pack] pack built | definitions=%s boundaries=%s use_cases=%s relationships=%s references=%s source=%s"
                % (
                    len(pack.definitions),
                    len(pack.boundaries),
                    len(pack.use_cases),
                    len(pack.relationships),
                    len(pack.references),
                    str((pack.metadata or {}).get("source") or ""),
                ),
                flush=True,
            )
        except Exception:
            pass
