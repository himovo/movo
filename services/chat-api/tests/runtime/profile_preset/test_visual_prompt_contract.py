import asyncio

from app.enterprise_capabilities.content.evaluation.standards_generator import _SYSTEM_PROMPT
from app.enterprise_capabilities.content.profile_presets.contracts import ComposeProfile, ProfilePreset
from app.enterprise_capabilities.content.profile_presets.prompt_constraints import (
    CONTENT_REVIEW_VISUAL_BOUNDARY,
    VISUAL_BODY_SEPARATION_CONSTRAINT,
)
from app.enterprise_capabilities.content.profile_presets import synthesizer as synthesizer_module


class _CapturingModel:
    def __init__(self, calls):
        self._calls = calls

    async def ainvoke(self, messages):
        self._calls.append(messages)
        return ProfilePreset(
            identity="social post writer",
            style_reference={"positive": ["concise"]},
            structure_contract={"required_blocks": ["标题", "正文"]},
            anti_patterns={"forbidden_words": ["placeholder"]},
            formatting_rules={"rules": ["markdown"]},
            quality_gates={"min_words": 300, "max_words": 800},
            output_contract={"format": "markdown"},
        )


class _CapturingClient:
    def __init__(self, calls):
        self._calls = calls

    def with_structured_output(self, *_args, **_kwargs):
        return _CapturingModel(self._calls)


def _profile():
    return ComposeProfile(
        intent_statement="生成一篇带配图的小红书笔记",
        deliverable_signature="social_media_post",
        raw_request="基于上文生成小红书笔记，要有配图",
        min_words=300,
        max_words=800,
    )


def test_dynamic_preset_synthesis_and_repair_share_visual_body_boundary(monkeypatch):
    calls = []
    monkeypatch.setattr(
        synthesizer_module,
        "get_request_scoped_llm_client",
        lambda **_kwargs: _CapturingClient(calls),
    )
    synthesizer = synthesizer_module.DynamicPresetSynthesizer()

    async def run_case():
        preset = await synthesizer.synthesize(
            compose_profile=_profile(), output_spec={}, task_ir={}
        )
        await synthesizer.repair(
            compose_profile=_profile(),
            output_spec={},
            task_ir={},
            current_preset=preset,
            issues=["test"],
        )

    asyncio.run(run_case())

    assert len(calls) == 2
    assert all(VISUAL_BODY_SEPARATION_CONSTRAINT in call[0].content for call in calls)


def test_content_review_prompt_rejects_visual_production_notes_as_body():
    assert CONTENT_REVIEW_VISUAL_BOUNDARY in _SYSTEM_PROMPT
    assert "image suggestions" in _SYSTEM_PROMPT
    assert "textual substitute" in _SYSTEM_PROMPT
