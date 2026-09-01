import asyncio

from app.enterprise_capabilities.browser.engine.transition_stabilizer import stabilize_transition_observation
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


def test_transition_waits_until_the_new_page_interaction_surface_stabilizes():
    before = Observation(url="https://example.test/search", title="Results", elements=[])
    initial = {"observation": {
        "url": "https://example.test/post/1",
        "title": "Post",
        "elements": [{"ref": "e1", "role": "link", "name": "background"}],
        "effects": [{"kind": "dom_added", "text": "发布成功"}],
    }}
    probes = iter([
        {"observation": {"url": "https://example.test/post/1", "title": "Post", "elements": [{"ref": "e2", "role": "textbox", "name": "Comment", "editable": True}]}},
        {"observation": {"url": "https://example.test/post/1", "title": "Post", "elements": [{"ref": "e3", "role": "textbox", "name": "Comment", "editable": True}]}},
    ])

    async def dispatch(_decision):
        return next(probes), True, None

    result = asyncio.run(
        stabilize_transition_observation(
            decision=Decision(tool="browser_click", args={"ref": "e9"}),
            before=before,
            result=initial,
            dispatch=dispatch,
            wait_seconds=0,
        )
    )

    assert result["observation"]["elements"][0]["role"] == "textbox"
    assert result["observation"]["effects"][0]["text"] == "发布成功"


def test_non_transition_does_not_add_observation_calls():
    before = Observation(url="https://example.test", title="Home", elements=[])
    calls = 0

    async def dispatch(_decision):
        nonlocal calls
        calls += 1
        return {}, True, None

    result = asyncio.run(
        stabilize_transition_observation(
            decision=Decision(tool="browser_click", args={"ref": "e1"}),
            before=before,
            result={"observation": {"url": before.url, "title": before.title, "elements": []}},
            dispatch=dispatch,
            wait_seconds=0,
        )
    )

    assert calls == 0
    assert result["observation"]["url"] == before.url
