from __future__ import annotations

from playwright.async_api import Page


class WeChatEditorPage:
    def __init__(self, page: Page) -> None:
        self.page = page

    async def fill_article(self, title: str, body: str) -> None:
        await self.page.get_by_label("标题").first.fill(title)
        await self.page.locator("[contenteditable='true']").first.fill(body)

    async def save_draft(self) -> None:
        await self.page.get_by_text("保存为草稿").first.click()
