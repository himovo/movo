from app.infrastructure.execution_events.history import normalize_execution_history


def test_current_history_stays_v3_and_can_be_resequenced():
    source = [{
        "v": 3,
        "event_id": "run_1",
        "id": "run_1",
        "ts": 1,
        "type": "run.started",
        "revision": 1,
        "payload": {},
    }]

    normalized = normalize_execution_history(source, resequence=True)

    assert normalized[0]["v"] == 3
    assert normalized[0]["stream_seq"] == 1
    assert "stream_seq" not in source[0]


def test_legacy_history_is_imported_as_v3_before_replay():
    source = [
        {"v": 2, "id": "start", "ts": 1, "type": "session.start", "payload": {}},
        {"v": 2, "id": "delta", "ts": 2, "type": "text.delta", "payload": {"text": "历史答案"}},
        {"v": 2, "id": "done", "ts": 3, "type": "text.done", "payload": {"text": "历史答案"}},
        {"v": 2, "id": "end", "ts": 4, "type": "session.end", "payload": {}},
    ]

    normalized = normalize_execution_history(source)

    assert normalized
    assert all(event["v"] == 3 for event in normalized)
    answers = [
        event for event in normalized
        if event.get("item_kind") == "final_answer" and event.get("type") == "item.completed"
    ]
    assert answers[-1]["payload"]["text"] == "历史答案"
