from __future__ import annotations

from playwright.async_api import Page


class WeChatLoginPage:
    def __init__(self, page: Page) -> None:
        self.page = page

    async def wait_qr_scan(self, timeout_ms: int = 120000) -> None:
        await self.page.get_by_text("扫码登录").first.wait_for(state="visible", timeout=timeout_ms)
