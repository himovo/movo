from app.browser.loop_policy import BROWSER_MAX_READS_PER_STATE, BROWSER_MAX_STEPS
from app.enterprise_capabilities.browser.engine.agent_loop.prompt import system_prompt


def test_browser_prompt_uses_shared_runtime_limits_in_both_languages() -> None:
    zh = system_prompt("zh")
    en = system_prompt("en")

    assert f"最多 {BROWSER_MAX_STEPS} 步" in zh
    assert f"最多 {BROWSER_MAX_READS_PER_STATE} 次" in zh
    assert f"at most {BROWSER_MAX_STEPS} steps" in en
    assert f"at most {BROWSER_MAX_READS_PER_STATE} total calls" in en
    assert "100 步" not in zh
    assert "~100 steps" not in en
    assert "per unique URL" not in en
