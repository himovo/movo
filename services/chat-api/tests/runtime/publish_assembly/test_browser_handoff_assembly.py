from __future__ import annotations

import asyncio

from app.enterprise_capabilities.content.publish_assembly.browser_handoff_assembly import (
    finalize_browser_handoff_assembly,
)
from app.enterprise_capabilities.content.publish_assembly.contracts import (
    GeneratedVisualAssetSpec,
    PublishAssemblySpec,
)


class _FakeFinalizer:
    def __init__(self, *, has_work: bool) -> None:
        self.has_work = has_work
        self.finalize_calls = 0

    def has_visual_work(self, *, final_markdown, output_spec) -> bool:
        assert final_markdown
        assert isinstance(output_spec, dict)
        return self.has_work

    async def finalize(self, **kwargs) -> PublishAssemblySpec:
        self.finalize_calls += 1
        assert kwargs["user_query"] == "生成图文文章"
        return PublishAssemblySpec(
            body_markdown="# 标题\n\n正文",
            final_markdown="# 标题\n\n正文\n\n![流程图](/api/files/generated.png)",
            generated_assets=[
                GeneratedVisualAssetSpec(
                    slot_id="v1",
                    image_url="/api/files/generated.png",
                    alt_text="流程图",
                    status="generated",
                ),
                GeneratedVisualAssetSpec(
                    slot_id="v2",
                    status="missing",
                ),
            ],
        )


def test_materializes_existing_visual_pipeline_before_browser_handoff() -> None:
    finalizer = _FakeFinalizer(has_work=True)

    result = asyncio.run(
        finalize_browser_handoff_assembly(
            markdown="# 标题\n\n正文",
            output_spec={"content_task_spec": {"visual_plan": {"required": True}}},
            user_query="生成图文文章",
            language="zh",
            user_id="user-1",
            finalizer=finalizer,
        )
    )

    assert finalizer.finalize_calls == 1
    assert result.markdown.endswith("![流程图](/api/files/generated.png)")
    assert result.visual_assets == [
        {
            "slot_id": "v1",
            "role": "",
            "anchor_section_id": "",
            "alt_text": "流程图",
            "image_url": "/api/files/generated.png",
            "status": "generated",
            "reason": "",
        }
    ]
    assert result.assembly["missing_slot_ids"] == []


def test_skips_visual_pipeline_when_generation_has_no_visual_work() -> None:
    finalizer = _FakeFinalizer(has_work=False)

    result = asyncio.run(
        finalize_browser_handoff_assembly(
            markdown="# 标题\n\n正文",
            output_spec={},
            user_query="生成文章",
            language="zh",
            user_id="user-1",
            finalizer=finalizer,
        )
    )

    assert finalizer.finalize_calls == 0
    assert result.markdown == "# 标题\n\n正文"
    assert result.visual_assets == []
    assert result.assembly == {}
