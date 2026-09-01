from app.browser.tools import is_browser_tool


def test_upload_file_is_a_registered_browser_tool() -> None:
    assert is_browser_tool("browser_upload_file")


def test_paste_image_is_a_registered_browser_tool() -> None:
    assert is_browser_tool("browser_paste_image")
