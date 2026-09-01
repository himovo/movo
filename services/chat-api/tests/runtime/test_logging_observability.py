import json
import logging

from app.infrastructure.observability.config import JsonLineFormatter, restore_print_for_tests
from app.infrastructure.observability.spans import current_span_snapshot, log_span
from app.infrastructure.request_context import reset_request_context, set_request_context


def test_json_formatter_injects_context_fields():
    previous = set_request_context({"request_id": "req_1", "session_id": "sess_1", "user_id": "u1"})
    try:
        record = logging.LogRecord(
            name="app.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        from app.infrastructure.observability.config import ContextFilter

        ContextFilter().filter(record)
        record.event = "test.event"
        line = JsonLineFormatter().format(record)
        payload = json.loads(line)
        assert payload["event"] == "test.event"
        assert payload["request_id"] == "req_1"
        assert payload["session_id"] == "sess_1"
        assert payload["user_id"] == "u1"
    finally:
        reset_request_context(previous)
        restore_print_for_tests()


def test_log_span_exposes_current_span_snapshot():
    previous = set_request_context({"request_id": "req_2"})
    try:
        with log_span("unit.test", item="x"):
            snapshot = current_span_snapshot()
            assert snapshot["span"] == "unit.test"
            assert snapshot["item"] == "x"
            assert snapshot["span_id"].startswith("span_")
        assert current_span_snapshot() == {}
    finally:
        reset_request_context(previous)
        restore_print_for_tests()
