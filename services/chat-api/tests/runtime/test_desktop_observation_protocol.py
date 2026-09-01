from app.enterprise_capabilities.browser.engine.desktop_agent_executor import _obs_from_payload


def test_nested_local_agent_observation_is_not_dropped():
    observation = _obs_from_payload({
        "url": "https://mail.example/inbox",
        "title": "Inbox",
        "observation": {
            "url": "https://mail.example/inbox",
            "title": "Inbox",
            "elements": [{"ref": "e1", "role": "button", "name": "Compose"}],
            "pageText": "Compose Inbox",
            "frameCount": 2,
        },
    })

    assert observation is not None
    assert observation.elements[0]["ref"] == "e1"
    assert observation.page_text == "Compose Inbox"
    assert observation.frame_count == 2

