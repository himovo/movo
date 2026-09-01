from app.context_engine.token_budget import estimate_tokens
from app.enterprise_capabilities.content.writer_engine.unified_compose.writer_prompt_budget import (
    FINAL_WRITER_INPUT_TOKEN_CAP,
    fit_writer_prompt,
)


def test_writer_prompt_budget_preserves_normal_prompt():
    result = fit_writer_prompt(system="system rules", user="user request")

    assert result.system == "system rules"
    assert result.user == "user request"
    assert not result.truncated


def test_writer_prompt_budget_caps_large_chinese_evidence():
    fence = "```"
    result = fit_writer_prompt(
        system="必须遵守写作合同。" * 1000,
        user=f"用户事实与搜索证据。\n{fence}text\n" + "证据。" * 120000 + f"\n{fence}",
    )

    assert result.truncated
    assert result.estimated_tokens <= FINAL_WRITER_INPUT_TOKEN_CAP
    assert estimate_tokens(result.system) + estimate_tokens(result.user) <= FINAL_WRITER_INPUT_TOKEN_CAP
    assert result.user.startswith("用户事实与搜索证据。")
    assert result.user.count(fence) % 2 == 0
