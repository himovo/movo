from __future__ import annotations

from app.enterprise_capabilities.browser.engine.agent_loop import planner as browser_planner
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation, StepRecord


def _observation(revision: str, elements: list[dict]) -> Observation:
    return Observation(
        url="https://example.test/editor",
        title="Editor",
        elements=elements,
        revision=revision,
    )


def _captured_pins(monkeypatch, history, current) -> set[str]:
    captured: dict[str, set[str]] = {}

    def fake_compact(observation, *, goal, target, pinned_refs):
        del observation, goal, target
        captured["refs"] = set(pinned_refs or ())
        return {"url": current.url, "elements": []}

    monkeypatch.setattr(browser_planner, "compact_observation", fake_compact)
    browser_planner._build_user_turn("发布文章", history, current)
    return captured["refs"]


def test_does_not_pin_same_ref_when_new_revision_reassigned_it(monkeypatch) -> None:
    previous = _observation("tab:1", [{
        "ref": "e7", "role": "button", "name": "发布", "selector": "#publish",
    }])
    current = _observation("tab:2", [{
        "ref": "e7", "role": "button", "name": "删除", "selector": "#delete",
        "visible": True, "hitTestable": True,
    }])
    history = [StepRecord(
        observation=current,
        decision=Decision(tool="browser_click", args={"ref": "e7"}),
        ok=True,
        decision_observation=previous,
    )]

    assert _captured_pins(monkeypatch, history, current) == set()


def test_migrates_historical_pin_to_uniquely_matching_live_identity(monkeypatch) -> None:
    previous = _observation("tab:1", [{
        "ref": "e7", "role": "button", "name": "发布", "selector": "#publish",
    }])
    current = _observation("tab:2", [
        {"ref": "e1", "role": "button", "name": "删除", "selector": "#delete"},
        {
            "ref": "e12", "role": "button", "name": "发布", "selector": "#publish",
            "visible": True, "hitTestable": True,
        },
    ])
    history = [StepRecord(
        observation=current,
        decision=Decision(tool="browser_click", args={"ref": "e7"}),
        ok=True,
        decision_observation=previous,
    )]

    assert _captured_pins(monkeypatch, history, current) == {"e12"}


def test_same_revision_keeps_observation_local_ref_compatibility(monkeypatch) -> None:
    current = _observation("tab:2", [{
        "ref": "e7", "role": "button", "name": "发布",
        "visible": True, "hitTestable": True,
    }])
    history = [StepRecord(
        observation=current,
        decision=Decision(tool="browser_click", args={"ref": "e7"}),
        ok=True,
        decision_observation=current,
    )]

    assert _captured_pins(monkeypatch, history, current) == {"e7"}


def test_legacy_record_without_pre_dispatch_observation_is_not_pinned(monkeypatch) -> None:
    current = _observation("tab:2", [{
        "ref": "e7", "role": "button", "name": "发布", "selector": "#publish",
        "visible": True, "hitTestable": True,
    }])
    history = [StepRecord(
        observation=current,
        decision=Decision(tool="browser_click", args={"ref": "e7"}),
        ok=True,
    )]

    assert _captured_pins(monkeypatch, history, current) == set()
