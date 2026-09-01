from app.enterprise_capabilities.browser.engine.form_input.observation_update import apply_confirmed_fill
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def test_confirmed_atomic_fill_updates_only_current_value() -> None:
    observation = Observation(
        url="https://example.test",
        title="test",
        elements=[{
            "ref": "e1", "role": "textbox", "name": "搜索关键词",
            "placeholder": "动态热点", "selector": "#search", "value": "",
        }],
    )

    updated = apply_confirmed_fill(
        observation,
        args={"ref": "e1", "value": "员工服务台"},
        result={"fill_receipt": {"status": "confirmed"}},
        ok=True,
    )

    assert updated.elements[0]["value"] == "员工服务台"
    assert updated.elements[0]["name"] == "搜索关键词"
    assert updated.elements[0]["placeholder"] == "动态热点"
