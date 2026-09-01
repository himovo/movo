from __future__ import annotations

import asyncio

from app.dsh_runtime.turn_runner import kernel_turn_context
from app.dsh_runtime.profile.tools import ToolProfileCompiler
from app.enterprise_capabilities.content.service import ContentProductionService
from app.enterprise_capabilities.content.invocation_contract import ContentInvocationContractRepository
from app.enterprise_capabilities.content.quality import ExistingContentQualityClosure
from app.enterprise_capabilities.content.routing import ContentWriterRouter
from app.enterprise_capabilities.content.visuals import FinalBodyVisualAssembler, FinalBodyVisualResult
from app.enterprise_capabilities.runtime import CapabilityExecutionContext, InternalCapabilityCatalog
from app.enterprise_capabilities.runtime.workflow_mapping import workflow_capability
from app.enterprise_capabilities.content.execution_mode.resolver import ExecutionModeResolver
from app.enterprise_capabilities.content.publish_assembly.contracts import GeneratedVisualAssetSpec, PublishAssemblySpec
from app.enterprise_capabilities.content.writer_engine.compose_skill import ToolWriterEngineComposeSkill
from app.enterprise_capabilities.content.evaluation.contracts import EvaluationResult, Issue, Standard


def _context(progress: list[dict], **turn_context) -> CapabilityExecutionContext:
    async def publish(event: dict) -> None:
        progress.append(event)

    return CapabilityExecutionContext(
        tenant_id="tenant-a", user_id="user-a", conversation_id="conversation-a",
        kernel_session_id="session-a", profile_version="profile-a", action_id="action-a",
        message_id="message-a", model_instance_id="model-a", turn_context=turn_context,
        progress_sink=publish,
    )


class _Styles:
    async def resolve(self, **kwargs):
        assert kwargs["selected_skill_id"] == "style-a"
        return [{"id": "style-a", "name": "企业写作规范"}], {
            "prompt_block": "# Writing Style Skill Contract\nUse concise prose."
        }


class _Writer:
    def __init__(self, *, with_image: bool = True) -> None:
        self.with_image = with_image
        self.context = None

    async def run_stream(self, context):
        self.context = context
        yield {"type": "activity", "content": {"kind": "writing", "message": "正在规划文章结构"}}
        image = "\n\n![架构图](https://example.test/architecture.png)" if self.with_image else ""
        yield {"type": "answer", "content": "# 成稿\n\n正文" + image}


class _PassThroughVisuals:
    async def finalize(self, **kwargs):
        return FinalBodyVisualResult(markdown=kwargs["markdown"])


async def _profile_applier(**kwargs):
    kwargs["output_spec"]["profile_preset"] = {"preset_id": "dynamic-a", "source": "dynamic"}
    return {"preset_id": "dynamic-a", "preset_source": "dynamic", "used_dynamic": True}


def test_content_capability_and_workflow_binding_use_migrated_pipeline() -> None:
    definition = next(
        item for item in InternalCapabilityCatalog().definitions()
        if item.capability_ref == "content.produce@v1"
    )
    assert definition.tool_name == "content_production"
    assert "single-pass long-form and sectional ultra-long-form" in definition.description
    assert "never from keywords" in definition.description
    assert "When accepted=true" in definition.description
    assert definition.timeout_mode == "activity"
    assert definition.timeout_ms == 1_800_000
    assert definition.inactivity_timeout_ms == 600_000
    assert definition.delivery_mode == "authoritative_markdown"
    assert definition.output_schema["required"] == ["success", "accepted", "acceptance"]
    acceptance_properties = definition.output_schema["properties"]["acceptance"]["properties"]
    assert acceptance_properties["character_count"] == {"type": "integer"}
    assert acceptance_properties["image_count"] == {"type": "integer"}
    assert acceptance_properties["required_visual_min"] == {"type": "integer"}
    binding = workflow_capability("generate_content")
    assert binding.runtime_shape == "tool"
    assert binding.capability_ref == "content.produce@v1"


def test_content_timeout_policy_is_compiled_into_dsh_tool_profile() -> None:
    class _EmptyAdminCatalog:
        async def list_enabled(self, tenant_id, user_id):
            return []

    tools = asyncio.run(ToolProfileCompiler(
        _EmptyAdminCatalog(), InternalCapabilityCatalog()
    ).compile(tenant_id="tenant-a", user_id="user-a"))
    content = next(item for item in tools if item.name == "content_production")
    assert content.timeout_mode == "activity"
    assert content.timeout_ms == 1_800_000
    assert content.inactivity_timeout_ms == 600_000
    assert content.delivery_mode == "authoritative_markdown"


def test_content_service_preserves_style_progress_and_generated_visual(monkeypatch) -> None:
    from app.enterprise_capabilities.content import service as module

    writer = _Writer(with_image=True)
    service = ContentProductionService(
        writer_factory=lambda: writer,
        style_resolver=_Styles(),
        profile_applier=_profile_applier,
        visual_assembler=_PassThroughVisuals(),
    )
    monkeypatch.setattr(module, "get_model_config", lambda *args: _async_value({"id": "model-a"}))
    monkeypatch.setattr(module, "get_default_model_config", lambda *args: _async_value(None))
    progress: list[dict] = []
    result = asyncio.run(service.run(
        {"request": "写一份企业AI报告并配一张图", "content_form": "report", "visual_min": 1},
        _context(
            progress,
            selected_writing_skill_id="style-a",
            language="zh",
            evidence_bundle={
                "results": [{
                    "tool": "progressive_research",
                    "title": "DSH source",
                    "source_url": "https://example.test/dsh",
                    "content": "DSH provides an agent runtime.",
                }],
            },
        ),
    ))
    assert result["success"] is True
    assert result["accepted"] is True
    assert result["acceptance"]["status"] == "accepted"
    assert result["acceptance"]["retry_allowed"] is False
    assert result["production"]["image_count"] == 1
    assert result["production"]["selected_style_names"] == ["企业写作规范"]
    assert progress[0]["parent_item_id"] == "action-a"
    assert progress[0]["payload"]["text"] == "正在解析写作要求、风格规范与证据边界"
    assert "正在规划文章结构" in [row["payload"]["text"] for row in progress]
    assert writer.context.payload["preserve_activity_events"] is True
    assert writer.context.payload["evidence_bundle"]["results"][0]["source_url"] == "https://example.test/dsh"
    assert result["production"]["evidence_count"] == 1
    assert "Writing Style Skill Contract" in writer.context.output_spec["writer_style_contract_block"]


def test_visual_minimum_fails_closed_when_pipeline_returns_no_image(monkeypatch) -> None:
    from app.enterprise_capabilities.content import service as module

    service = ContentProductionService(
        writer_factory=lambda: _Writer(with_image=False),
        style_resolver=_Styles(),
        profile_applier=_profile_applier,
        visual_assembler=_PassThroughVisuals(),
    )
    monkeypatch.setattr(module, "get_model_config", lambda *args: _async_value({"id": "model-a"}))
    monkeypatch.setattr(module, "get_default_model_config", lambda *args: _async_value(None))
    result = asyncio.run(service.run(
        {"request": "生成带图报告", "visual_min": 1},
        _context([], selected_writing_skill_id="style-a"),
    ))
    assert result["success"] is False
    assert result["accepted"] is False
    assert result["acceptance"]["status"] == "rejected"
    assert result["acceptance"]["retry_allowed"] is True
    assert result["acceptance"]["reasons"] == ["required_visuals_missing"]
    assert result["message"] == "required visuals were not generated"
    assert result["markdown"].startswith("# 成稿")


def test_direct_content_reuses_existing_quality_pipeline_and_repairs_once(monkeypatch) -> None:
    from app.enterprise_capabilities.content import service as module

    class Writer:
        def __init__(self):
            self.calls = 0

        async def run_stream(self, context):
            self.calls += 1
            context.output_spec["__writer_path"] = "single_shot"
            yield {"type": "activity", "content": {"kind": "writing", "message": "正在一次性撰写完整正文"}}
            if context.output_spec.get("__doc_level_eval_feedback"):
                yield {"type": "answer", "content": "# 修订成稿\n\n已补齐实施步骤"}
            else:
                yield {"type": "answer", "content": "# 初稿\n\n缺少实施步骤"}

    class Pipeline:
        def __init__(self):
            self.calls = []

        async def evaluate(self, **kwargs):
            self.calls.append(kwargs)
            standard = Standard(id="std_001", severity="major", description="包含实施步骤")
            return EvaluationResult(
                standards=[standard],
                issues=[Issue(
                    standard_id="std_001", severity="major", location="全文",
                    finding="缺少实施步骤", fix_suggestion="补充实施步骤",
                )],
                verdict="needs_repair",
                metadata={"evaluation_status": "completed"},
            )

    writer = Writer()
    pipeline = Pipeline()
    service = ContentProductionService(
        writer_factory=lambda: writer,
        style_resolver=_Styles(),
        profile_applier=_profile_applier,
        visual_assembler=_PassThroughVisuals(),
        quality_closure=ExistingContentQualityClosure(pipeline),
    )
    monkeypatch.setattr(module, "get_model_config", lambda *args: _async_value({"id": "model-a"}))
    monkeypatch.setattr(module, "get_default_model_config", lambda *args: _async_value(None))
    progress: list[dict] = []
    result = asyncio.run(service.run(
        {"request": "写一份包含实施步骤的企业报告", "content_form": "report"},
        _context(progress, selected_writing_skill_id="style-a", language="zh"),
    ))
    assert result["success"] is True
    assert result["accepted"] is True
    assert result["acceptance"]["quality_verdict"] == "repaired_unverified"
    assert result["markdown"].startswith("# 修订成稿")
    assert writer.calls == 2
    assert len(pipeline.calls) == 1
    assert result["production"]["quality"]["repair_applied"] is True
    assert result["production"]["quality"]["verdict"] == "repaired_unverified"
    assert result["production"]["quality"]["evaluation_status"] == "repaired"
    assert result["production"]["quality"]["metadata"]["post_repair_review_skipped"] is True
    timeline = [row["payload"]["text"] for row in progress]
    assert "初稿已完成，正在生成质量标准并检查正文" in timeline
    assert "质量检查发现需要修正的问题，正在按原写作要求重写" in timeline
    assert "修订已完成，正在继续配图与交付处理" in timeline


def test_content_retry_recovers_missing_visual_contract(monkeypatch) -> None:
    from app.enterprise_capabilities.content import invocation_contract as module

    class Collection:
        def __init__(self):
            self.row = {
                "active_turn": {
                    "message_id": "message-a", "status": "running",
                    "content_invocation_contracts": [],
                }
            }

        async def find_one(self, query, projection):
            return self.row

        async def update_one(self, query, update):
            items = update["$push"]["active_turn.content_invocation_contracts"]["$each"]
            self.row["active_turn"]["content_invocation_contracts"].extend(items)
            return object()

    collection = Collection()

    class DB:
        def __getitem__(self, name):
            return collection

    monkeypatch.setattr(module, "get_db", lambda: DB())
    repository = ContentInvocationContractRepository()

    async def run():
        first = await repository.resolve(
            tenant_id="tenant-a", user_id="user-a", kernel_session_id="session-a",
            message_id="message-a",
            arguments={
                "request": "写一份企业报告并配两张图", "content_form": "report",
                "min_words": 2000, "max_words": 2400, "visual_min": 2, "visual_max": 2,
            },
        )
        retry = await repository.resolve(
            tenant_id="tenant-a", user_id="user-a", kernel_session_id="session-a",
            message_id="message-a",
            arguments={"request": "写一份企业报告并配两张图", "content_form": "report"},
        )
        separate = await repository.resolve(
            tenant_id="tenant-a", user_id="user-a", kernel_session_id="session-a",
            message_id="message-a",
            arguments={"request": "写另一份不需要配图的报告", "content_form": "report"},
        )
        return first, retry, separate

    first, retry, separate = asyncio.run(run())
    assert first.recovered_fields == ()
    assert retry.arguments["visual_min"] == 2
    assert retry.arguments["visual_max"] == 2
    assert set(retry.recovered_fields) >= {"visual_min", "visual_max", "min_words", "max_words"}
    assert "visual_min" not in separate.arguments


def test_visual_request_does_not_override_single_shot_writer_route() -> None:
    skill = ToolWriterEngineComposeSkill.__new__(ToolWriterEngineComposeSkill)
    skill._mode_resolver = ExecutionModeResolver()
    route = skill._decide_execution_mode(
        strategy={
            "compose_policy": {"content_form": "guide"},
            "structure_contract": {"required_blocks": ["架构", "实施", "风险", "建议"]},
            "quality_gates": {"min_words": 1800, "max_words": 2200},
            "evidence_policy": {}, "prompt_contract": {},
        },
        output_spec={"content_task_spec": {"visual_plan": {"min_assets": 2, "max_assets": 2}}},
        user_query="写一篇约2000字的指南并配两张图",
    )
    assert route["mode"] == "direct_compose"
    assert "semantic_single_pass_feasible" in route["reasons"]
    assert "generated_visuals_require_sectional_pipeline" not in route["reasons"]


def test_dsh_content_router_exposes_only_direct_or_sectional_modes() -> None:
    direct_spec = {
        "profile_preset": {
            "compose_policy": {"content_form": "guide"},
            "structure_contract": {"required_blocks": ["架构", "实施", "风险", "建议"]},
            "quality_gates": {"min_words": 1800, "max_words": 2200},
        }
    }
    direct = ContentWriterRouter().apply(output_spec=direct_spec, user_query="撰写管理指南")
    assert direct["mode"] == "direct_compose"
    assert direct_spec["profile_preset"]["compose_policy"]["write_mode"] == "direct_compose"

    sectional_spec = {
        "profile_preset": {
            "compose_policy": {
                "content_form": "whitepaper",
                "delivery_profile": {"semantic_profile": {"document_scale": True}},
            },
            "structure_contract": {"required_blocks": [f"章节{i}" for i in range(1, 9)]},
            "quality_gates": {"min_words": 10000, "max_words": 12000},
        }
    }
    sectional = ContentWriterRouter().apply(output_spec=sectional_spec, user_query="撰写完整白皮书")
    assert sectional["mode"] == "sectional_compose"
    assert sectional_spec["profile_preset"]["compose_policy"]["write_mode"] == "sectional_compose"


class _DeferredFinalizer:
    def __init__(self) -> None:
        self.calls = 0

    def has_visual_work(self, **kwargs):
        return bool(kwargs["output_spec"]["content_task_spec"]["visual_plan"]["min_assets"])

    async def finalize(self, **kwargs):
        self.calls += 1
        asset = GeneratedVisualAssetSpec(
            slot_id="v1", role="architecture", anchor_section_id="s1", alt_text="架构图",
            image_url="https://example.test/generated.png", status="generated", reason="generated",
        )
        return PublishAssemblySpec(
            body_markdown=kwargs["final_markdown"],
            final_markdown=kwargs["final_markdown"] + "\n\n![架构图](https://example.test/generated.png)",
            generated_assets=[asset],
        )


def test_single_shot_content_uses_existing_deferred_visual_pipeline() -> None:
    finalizer = _DeferredFinalizer()
    assembler = FinalBodyVisualAssembler(finalizer_factory=lambda: finalizer)
    progress: list[dict] = []

    async def publish(event: dict) -> None:
        progress.append(event)

    result = asyncio.run(assembler.finalize(
        markdown="# 一次性成文\n\n完整正文",
        output_spec={
            "__writer_path": "single_shot",
            "content_task_spec": {"visual_plan": {"min_assets": 1, "max_assets": 1}},
        },
        user_query="写文章并配图", language="zh", user_id="user-a",
        progress_sink=publish,
    ))
    assert finalizer.calls == 1
    assert "generated.png" in result.markdown
    assert result.assets[0]["slot_id"] == "v1"
    assert progress[0]["content"]["kind"] == "visual"
    assert "正在规划并生成配图" in progress[0]["content"]["message"]


def test_sectional_content_does_not_repeat_deferred_visual_generation() -> None:
    finalizer = _DeferredFinalizer()
    assembler = FinalBodyVisualAssembler(finalizer_factory=lambda: finalizer)
    result = asyncio.run(assembler.finalize(
        markdown="# 分章内容\n\n![已有图片](https://example.test/section.png)",
        output_spec={
            "__writer_path": "sectional",
            "content_task_spec": {"visual_plan": {"min_assets": 1, "max_assets": 1}},
        },
        user_query="写长文并配图", language="zh", user_id="user-a",
    ))
    assert finalizer.calls == 0
    assert "section.png" in result.markdown


def test_selected_style_id_crosses_only_as_a_trusted_profile_reference() -> None:
    filtered = kernel_turn_context({
        "knowledge_qa_enabled": False,
        "documents": [{"object_path": "owned/a.docx"}],
        "selected_writing_skill_id": "style-secret",
        "user_request": "server-only original request",
    })
    assert filtered["documents"][0]["object_path"] == "owned/a.docx"
    # Step 7 lets the immutable Host profile resolve this opaque ID so direct
    # DSH writing can use the selected standard. The browser/client supplied
    # prose and the style instructions themselves never cross this boundary.
    assert filtered["selected_writing_skill_id"] == "style-secret"
    assert "user_request" not in filtered


async def _async_value(value):
    return value
