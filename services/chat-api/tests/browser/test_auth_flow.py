import asyncio

from app.enterprise_capabilities.browser.engine.auth_flow import wait_for_authentication
from app.enterprise_capabilities.browser.engine.auth_state import AuthTransitionTracker
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def test_auth_wait_is_passive_and_requires_stable_idle_success():
    asyncio.run(_exercise_auth_wait())


async def _exercise_auth_wait():
    tracker = AuthTransitionTracker()
    tracker.observe(
        url="https://id.example.com/login",
        assessment={"state": "required"},
        has_page_evidence=True,
    )
    calls = []
    observations = [
        {"url": "https://app.example.com/home", "title": "Home", "elements": [{"ref": "e1"}], "pageText": "", "auth": {"state": "unknown"}, "interaction": {"humanIdleMs": 2000}},
        {"url": "https://app.example.com/home", "title": "Home", "elements": [{"ref": "e1"}], "pageText": "", "auth": {"state": "unknown"}, "interaction": {"humanIdleMs": 2000}},
    ]

    async def dispatch(decision):
        calls.append(decision.tool)
        observation = observations.pop(0)
        return {"observation": observation}, True, None

    def parse(payload):
        return Observation(
            url=payload["url"], title=payload["title"],
            elements=payload["elements"], page_text=payload["pageText"],
            auth=payload["auth"],
        )

    events = [event async for event in wait_for_authentication(
        dispatch=dispatch,
        parse_observation=parse,
        tracker=tracker,
        current_observation=Observation(url="https://id.example.com/login", title="Login", elements=[]),
        timeout_seconds=1,
        poll_seconds=0,
    )]

    assert calls == ["browser_observe", "browser_observe"]
    assert events[-1].state == "authenticated"
