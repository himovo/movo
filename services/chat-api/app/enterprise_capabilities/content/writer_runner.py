"""Small execution adapter around ASKAI's existing writer skill."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from app.llm.types import Message, Role
from app.enterprise_capabilities.content.writer_engine.skill_contract import SkillContext

from .timeline import ContentTimelineProjector


@dataclass
class WriterRunResult:
    markdown: str
    writer_path: str = ""
    artifacts: list[dict[str, Any]] = field(default_factory=list)


class ContentWriterRunner:
    def __init__(self, writer_factory: Callable[[], Any]) -> None:
        self._writer_factory = writer_factory

    async def run(
        self,
        *,
        request: str,
        output_spec: dict[str, Any],
        payload: dict[str, Any],
        projector: ContentTimelineProjector,
        publish_progress: Callable[[dict[str, Any]], Any],
        feedback: str = "",
    ) -> WriterRunResult:
        current_spec = dict(output_spec)
        if feedback:
            current_spec["__doc_level_eval_feedback"] = feedback
        context = SkillContext(
            messages=[Message(role=Role.USER, content=request)],
            intent="generation",
            output_spec=current_spec,
            payload=dict(payload),
        )
        answers: list[str] = []
        artifacts: list[dict[str, Any]] = []
        async for event in self._writer_factory().run_stream(context):
            event_type = str(event.get("type") or "").strip().lower() if isinstance(event, dict) else ""
            if event_type == "answer":
                answers.append(str(event.get("content") or ""))
            elif event_type in {"activity", "commentary"}:
                for row in projector.project(event):
                    await publish_progress(row)
            elif event_type in {"document", "artifact"} and isinstance(event.get("content"), dict):
                artifacts.append(dict(event["content"]))
        output_spec.update(context.output_spec or {})
        return WriterRunResult(
            markdown="\n\n".join(part.strip() for part in answers if part.strip()).strip(),
            writer_path=str((context.output_spec or {}).get("__writer_path") or "").strip().lower(),
            artifacts=artifacts,
        )


__all__ = ["ContentWriterRunner", "WriterRunResult"]
