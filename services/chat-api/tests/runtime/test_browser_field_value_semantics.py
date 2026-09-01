from app.enterprise_capabilities.browser.engine.form_input.field_semantics import stable_placeholder_role
from app.enterprise_capabilities.browser.engine.form_input.field_value import current_field_value
from app.enterprise_capabilities.browser.engine.form_input.inventory import discover_fields
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def test_instructional_placeholders_identify_title_and_body() -> None:
    assert stable_placeholder_role("请在这里输入标题") == "title"
    assert stable_placeholder_role("从这里开始写正文") == "body"


def test_decorative_editor_placeholder_is_not_a_current_value() -> None:
    element = {
        "contentEditable": True,
        "placeholder": "从这里开始写正文",
        "placeholderDecorative": True,
        "value": "从这里开始写正文",
    }

    assert current_field_value(element, placeholder=element["placeholder"]) == ""


def test_real_value_equal_to_non_decorative_placeholder_is_preserved() -> None:
    element = {
        "contentEditable": True,
        "placeholder": "正文",
        "placeholderDecorative": False,
        "value": "正文",
    }

    assert current_field_value(element, placeholder=element["placeholder"]) == "正文"


def test_discovery_keeps_empty_editor_and_assigns_explicit_roles() -> None:
    observation = Observation(
        url="https://publisher.example.test/edit",
        title="Editor",
        elements=[
            {
                "ref": "title",
                "role": "textbox",
                "name": "",
                "tag": "div",
                "contentEditable": True,
                "editable": True,
                "visible": True,
                "placeholder": "请在这里输入标题",
                "value": "",
                "scopeId": "0:#editor",
                "width": 600,
                "height": 40,
            },
            {
                "ref": "body",
                "role": "textbox",
                "name": "",
                "tag": "div",
                "contentEditable": True,
                "editable": True,
                "visible": True,
                "placeholder": "从这里开始写正文",
                "placeholderDecorative": True,
                "value": "从这里开始写正文",
                "scopeId": "0:#editor",
                "width": 600,
                "height": 320,
            },
        ],
    )

    fields = discover_fields(observation)

    assert [(field.ref, field.semantic_role, field.current_value) for field in fields] == [
        ("title", "title", ""),
        ("body", "body", ""),
    ]
