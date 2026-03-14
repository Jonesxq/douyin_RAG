from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from playwright.async_api import async_playwright

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

VIDEO_ID_PATTERN = re.compile(r"/video/(\d+)")


@dataclass
class FavoriteScrapedItem:
    platform_item_id: str
    url: str
    title: str
    author: str
    duration_sec: int | None


class DouyinCollector:
    def __init__(self) -> None:
        self.status = "idle"
        self.message = ""
        self._login_task: asyncio.Task[None] | None = None
        self.storage_state_path = Path(settings.playwright_user_data_dir) / "state.json"

    def start_login(self) -> tuple[bool, str]:
        if self.status == "pending" and self._login_task and not self._login_task.done():
            return False, "Login already in progress"

        self.status = "pending"
        self.message = "Scan QR code in the opened browser window"
        self._login_task = asyncio.create_task(self._login_flow())
        return True, self.message

    async def _login_flow(self) -> None:
        try:
            async with async_playwright() as p:
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=settings.playwright_user_data_dir,
                    headless=settings.playwright_headless,
                )
                page = context.pages[0] if context.pages else await context.new_page()
                await page.goto(settings.douyin_home_url, timeout=120_000)

                found = False
                for _ in range(120):
                    cookies = await context.cookies()
                    has_login_cookie = any(c.get("name") in {"sessionid", "sid_guard"} for c in cookies)
                    if has_login_cookie:
                        found = True
                        break
                    await asyncio.sleep(1)

                if not found:
                    self.status = "failed"
                    self.message = "Login timeout. Please retry."
                    await context.close()
                    return

                await context.storage_state(path=str(self.storage_state_path))
                await context.close()

                self.status = "logged_in"
                self.message = "Login successful"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Douyin login failed")
            self.status = "failed"
            self.message = str(exc)

    async def fetch_favorites(self, max_items: int = 200) -> list[FavoriteScrapedItem]:
        if not self.storage_state_path.exists():
            raise RuntimeError("No login state found. Please login first.")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(storage_state=str(self.storage_state_path))
            page = await context.new_page()
            await page.goto(settings.favorites_url, timeout=120_000)

            for _ in range(8):
                await page.mouse.wheel(0, 4000)
                await asyncio.sleep(1)

            raw_items = await page.evaluate(
                """
                () => {
                    const anchors = Array.from(document.querySelectorAll('a[href*="/video/"]'));
                    return anchors.map((a) => {
                        const href = a.getAttribute('href') || '';
                        const fullUrl = href.startsWith('http') ? href : `https://www.douyin.com${href}`;
                        const titleNode = a.querySelector('[data-e2e*="title"], h3, span');
                        const title = titleNode ? titleNode.textContent?.trim() || '' : (a.textContent || '').trim();
                        return {
                            url: fullUrl,
                            title: title || 'Untitled',
                            author: '',
                            duration_sec: null
                        }
                    });
                }
                """
            )

            await context.close()
            await browser.close()

        deduped: dict[str, FavoriteScrapedItem] = {}
        for item in raw_items:
            match = VIDEO_ID_PATTERN.search(item.get("url", ""))
            if not match:
                continue
            video_id = match.group(1)
            deduped[video_id] = FavoriteScrapedItem(
                platform_item_id=video_id,
                url=item.get("url", ""),
                title=(item.get("title") or "Untitled")[:500],
                author=(item.get("author") or "")[:255],
                duration_sec=item.get("duration_sec"),
            )

        return list(deduped.values())[:max_items]


collector = DouyinCollector()
