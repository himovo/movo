import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.llm.providers.azure_openai import AzureOpenAIClient


def test_json_object_input_marker_is_added_when_missing() -> None:
    input_items = [
        {
            "type": "message",
            "role": "user",
            "content": "Plan this task.",
        }
    ]

    out = AzureOpenAIClient._ensure_json_object_input_marker(input_items)

    assert len(out) == 2
    assert out[0]["role"] == "user"
    assert "JSON" in out[0]["content"]
    assert out[1] is input_items[0]


def test_json_object_input_marker_is_not_duplicated() -> None:
    input_items = [
        {
            "type": "message",
            "role": "user",
            "content": "Return JSON for this task.",
        }
    ]

    out = AzureOpenAIClient._ensure_json_object_input_marker(input_items)

    assert out is input_items


if __name__ == "__main__":
    test_json_object_input_marker_is_added_when_missing()
    test_json_object_input_marker_is_not_duplicated()
