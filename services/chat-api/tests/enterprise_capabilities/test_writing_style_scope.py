from __future__ import annotations

import pytest

from app.dsh_runtime.profile.models import RuntimeProfileSnapshot
from app.dsh_runtime.profile.skills.models import WritingStyleDefinition
from app.enterprise_capabilities.content.style_scope import apply_writing_style_ref


def profile() -> RuntimeProfileSnapshot:
    return RuntimeProfileSnapshot(
        profile_version="rp-a",
        content_hash="a" * 64,
        tenant_id="tenant-a",
        subject_user_id="user-a",
        model_source_tenant_id="tenant-a",
        model_instance_id="model-a",
        provider_id="provider-a",
        provider_type="openai_compatible",
        provider_name="provider",
        model_name="model",
        display_name="model",
        capabilities=("chat",),
        writing_styles=(WritingStyleDefinition(
            ref="style-" + "b" * 24,
            version="style-v1",
            source_id="style-source",
            source_scope="organization",
            name="报告规范",
            instructions="只约束写作。",
        ),),
    )


def test_workflow_style_ref_is_consumed_and_applied_only_to_content_context():
    arguments, context = apply_writing_style_ref(
        {"request": "写报告", "writing_style_ref": "style-" + "b" * 24}, {}, profile(),
    )
    assert "writing_style_ref" not in arguments
    assert context["selected_writing_skill_id"] == "style-source"


def test_manual_style_has_priority_over_workflow_binding():
    _, context = apply_writing_style_ref(
        {"writing_style_ref": "style-" + "b" * 24},
        {"selected_writing_skill_id": "manual-style"}, profile(),
    )
    assert context["selected_writing_skill_id"] == "manual-style"


def test_unknown_style_ref_fails_closed():
    with pytest.raises(PermissionError):
        apply_writing_style_ref({"writing_style_ref": "style-" + "c" * 24}, {}, profile())
