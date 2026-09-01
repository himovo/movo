from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.services.presentation.contracts import (
    FreeformPageBlueprint,
    PageBrief,
    PageRepairReport,
)

from .page_executor import BoundedPageExecutor
from .session import PresentationExecutionSession

logger = logging.getLogger(__name__)


class FreeformPageExecutionCoordinator:
    """Own resume/order/concurrency concerns outside the page designer."""

    def __init__(self, concurrency: int = 3) -> None:
        self._executor = BoundedPageExecutor[PageBrief, FreeformPageBlueprint](concurrency)

    async def build(
        self,
        *,
        page_briefs: list[PageBrief],
        session: PresentationExecutionSession | None,
        generate: Callable[[int, PageBrief], Awaitable[FreeformPageBlueprint]],
    ) -> tuple[list[FreeformPageBlueprint], list[PageRepairReport]]:
        restored = self._restored_pages(session)

        async def checkpoint(page_id: str, page: FreeformPageBlueprint) -> None:
            if session is not None:
                await session.checkpoint_page(page_id, page.model_dump())

        pages = await self._executor.run(
            items=page_briefs,
            item_id=lambda brief: str(brief.page_id or "").strip(),
            existing=restored,
            generate=generate,
            checkpoint=checkpoint,
            check_cancelled=session.raise_if_cancelled if session is not None else lambda: None,
        )
        return pages, [self._report(page) for page in pages]

    @staticmethod
    def planned_prior_context(
        page_briefs: list[PageBrief],
        current_index: int,
    ) -> list[dict[str, Any]]:
        return [
            {
                "page_id": str(brief.page_id or "").strip(),
                "key_takeaway": str(brief.key_takeaway or "").strip(),
                "composition_intent": str(brief.composition_intent or "").strip(),
                "layout_signature": (
                    f"planned_archetype={str(brief.layout_archetype_id or '').strip()}|"
                    f"page_type={str(brief.page_type or '').strip()}"
                ),
            }
            for brief in page_briefs[max(0, current_index - 3):current_index]
        ]

    @staticmethod
    def _restored_pages(
        session: PresentationExecutionSession | None,
    ) -> dict[str, FreeformPageBlueprint]:
        restored: dict[str, FreeformPageBlueprint] = {}
        if session is None:
            return restored
        for page_id, payload in session.pages.items():
            try:
                restored[page_id] = FreeformPageBlueprint.model_validate(
                    payload.get("blueprint", payload)
                )
            except Exception:
                logger.warning(
                    "presentation_page_checkpoint_invalid job_id=%s page_id=%s",
                    session.job_id,
                    page_id,
                    exc_info=True,
                )
        return restored

    @staticmethod
    def _report(page: FreeformPageBlueprint) -> PageRepairReport:
        return PageRepairReport(
            page_id=page.page_id,
            issues=[],
            accepted=True,
            attempt_count=1,
            issue_score_before=0,
            issue_score_after=0,
        )


__all__ = ["FreeformPageExecutionCoordinator"]
