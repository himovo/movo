from __future__ import annotations

from playwright.async_api import Page


class WeChatDraftListPage:
    def __init__(self, page: Page) -> None:
        self.page = page

    async def find_draft(self, title: str) -> bool:
        loc = self.page.get_by_text(title).first
        try:
            await loc.wait_for(state="visible", timeout=5000)
            return True
        except Exception:
            return False
