from __future__ import annotations

import asyncio

from app.enterprise_capabilities.research import ResearchTimelineProjector
from app.enterprise_capabilities.runtime import CapabilityExecutionContext
from app.enterprise_capabilities.runtime.adapters import progressive_research
from app.enterprise_capabilities.research.progressive.models import ProgressiveResearchResult


def _context(progress):
    return CapabilityExecutionContext(
        tenant_id="tenant-a", user_id="user-a", conversation_id="conversation-a",
        kernel_session_id="session-a", profile_version="profile-a", action_id="action-a",
        message_id="message-a", model_instance_id="model-a", progress_sink=progress,
    )


def test_research_projector_preserves_operation_lifecycle_under_outer_tool() -> None:
    projector = ResearchTimelineProjector(outer_action_id="action-a", message_id="message-a")
    started = projector.project({
        "type": "operation.started",
        "content": {"operation_id": "search-1", "label": "第一轮检索", "category": "search"},
    })[0]
    completed = projector.project({
        "type": "operation.completed",
        "content": {"operation_id": "search-1", "detail": {"candidate_count": 8}},
    })[0]
    assert started["type"] == "item.started"
    assert completed["type"] == "item.completed"
    assert completed["item_id"] == started["item_id"]
    assert completed["parent_item_id"] == "action-a"
    assert completed["payload"]["label"] == "第一轮检索"


def test_progressive_adapter_uses_selected_model_and_streams_projected_progress(monkeypatch) -> None:
    rows = []

    async def progress(row):
        rows.append(row)

    async def fake_model_config(model_id, tenant_id):
        assert (model_id, tenant_id) == ("model-a", "tenant-a")
        return {"provider": "test", "model": "judge"}

    class FakeAgent:
        def __init__(self, **kwargs):
            self.progress_callback = kwargs["progress_callback"]

        async def run(self, **kwargs):
            assert kwargs["query"] == "compare products"
            await self.progress_callback({
                "type": "operation.started",
                "content": {"operation_id": "round-1", "label": "Search round 1", "category": "search"},
            })
            await self.progress_callback({
                "type": "operation.completed",
                "content": {"operation_id": "round-1", "detail": {"candidate_count": 3}},
            })
            return ProgressiveResearchResult(
                ok=True, query=kwargs["query"], rounds=1, results=[{"title": "A"}],
                evidence_sufficient=True, stop_reason="evidence_sufficient",
            )

    monkeypatch.setattr("app.enterprise_capabilities.runtime.adapters.get_model_config", fake_model_config)
    monkeypatch.setattr("app.enterprise_capabilities.runtime.adapters.ProgressiveResearchAgent", FakeAgent)
    result = asyncio.run(progressive_research({"query": "compare products"}, _context(progress)))
    assert result["success"] is True
    assert result["evidence_sufficient"] is True
    assert [row["type"] for row in rows] == ["item.started", "item.completed"]
