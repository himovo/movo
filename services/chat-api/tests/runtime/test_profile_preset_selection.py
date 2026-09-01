import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.enterprise_capabilities.content.profile_presets.catalog import PresetCatalog
from app.enterprise_capabilities.content.profile_presets.contracts import ComposeProfile
from app.enterprise_capabilities.content.profile_presets.resolver import ProfilePresetResolver


def _skill(skill_id: str):
    return {
        "id": skill_id,
        "name": skill_id,
        "is_active": True,
        "advanced": {"policy": {"compose_policy": {"tone": "professional"}}},
        "skill_contract": {"structure": {"required_blocks": ["结论"]}},
    }


def test_catalog_uses_only_upstream_selected_writing_skills():
    selected_style = _skill("selected-style")
    unrelated_active = _skill("unrelated-active")

    candidates = PresetCatalog().list_candidates(
        output_spec={
            "selected_style_skills": [selected_style],
            "user_skills": [selected_style, unrelated_active],
        }
    )

    assert [item.preset_id for item in candidates] == ["selected-style"]


def test_catalog_does_not_fall_back_to_unrelated_active_skills():
    assert PresetCatalog().list_candidates(
        output_spec={"user_skills": [_skill("unrelated-active")]}
    ) == []


def test_resolver_does_not_rerank_upstream_selected_skill():
    async def run_case():
        resolver = ProfilePresetResolver()

        async def fake_profile(**_kwargs):
            return ComposeProfile(intent_statement="测试", raw_request="测试")

        async def should_not_run(**_kwargs):
            raise AssertionError("upstream-selected candidates must not be re-ranked")

        resolver.extract_compose_profile = fake_profile
        resolver._rank = should_not_run
        resolver._conflicts.check = should_not_run
        resolver._quality.validate = lambda **_kwargs: {"ok": True, "score": 1.0, "issues": []}
        return await resolver.resolve(
            messages=[{"role": "user", "content": "测试"}],
            output_spec={"selected_style_skills": [_skill("selected-style")]},
            task_ir={},
        )

    result = asyncio.run(run_case())

    assert result.selected_preset is not None
    assert result.selected_preset.preset_id == "selected-style"
    assert result.trace["candidate_source"] == "upstream_selected_writing_skills"
