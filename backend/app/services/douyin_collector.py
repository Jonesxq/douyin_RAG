from __future__ import annotations

"""抖音采集服务：扫码登录、收藏夹快照抓取。"""

import asyncio
import logging
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _ensure_windows_proactor_policy() -> None:
    """
    功能：执行 _ensure_windows_proactor_policy 的内部处理逻辑。
    参数：
    - 无。
    返回值：
    - None：函数处理结果。
    """
    if sys.platform != "win32":
        return
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:  # noqa: BLE001
        logger.exception("Failed to set Windows Proactor event loop policy")


def _find_project_chromium_executable() -> Path | None:
    """
    功能：执行 _find_project_chromium_executable 的内部处理逻辑。
    参数：
    - 无。
    返回值：
    - Path | None：函数处理结果。
    """
    base = Path(settings.playwright_browsers_path)
    if not base.exists():
        return None

    candidates = sorted(base.glob("chromium-*/chrome-win/chrome.exe"), reverse=True)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


@dataclass
class FavoriteScrapedCollection:
    platform_collection_id: str
    title: str
    item_count: int
    cover_url: str | None = None


@dataclass
class FavoriteScrapedVideo:
    platform_item_id: str
    url: str
    title: str
    author: str
    duration_sec: int | None
    collection_ids: set[str] = field(default_factory=set)


@dataclass
class FavoriteScrapeSnapshot:
    collections: list[FavoriteScrapedCollection] = field(default_factory=list)
    videos: list[FavoriteScrapedVideo] = field(default_factory=list)


class DouyinCollector:
    def __init__(self) -> None:
        """
        功能：初始化 DouyinCollector 的实例状态。
        参数：
        - 无。
        返回值：
        - None：构造函数不返回业务值。
        """
        self.status = "idle"
        self.message = ""
        self._login_task: asyncio.Task[None] | None = None
        self.storage_state_path = Path(settings.playwright_user_data_dir) / "state.json"

    def _browser_launch_candidates(self, headless: bool) -> list[tuple[str, dict]]:
        """
        功能：执行 DouyinCollector._browser_launch_candidates 的内部处理逻辑。
        参数：
        - headless：输入参数。
        返回值：
        - list[tuple[str, dict]]：函数处理结果。
        """
        candidates: list[tuple[str, dict]] = []

        executable = _find_project_chromium_executable()
        if executable:
            candidates.append(
                (
                    f"project-chromium:{executable}",
                    {"headless": headless, "executable_path": str(executable)},
                )
            )

        if settings.playwright_browser_channel.strip():
            candidates.append(
                (
                    f"channel:{settings.playwright_browser_channel}",
                    {"headless": headless, "channel": settings.playwright_browser_channel.strip()},
                )
            )
        elif sys.platform == "win32":
            candidates.append(("channel:msedge", {"headless": headless, "channel": "msedge"}))

        candidates.append(("playwright-default", {"headless": headless}))
        return candidates

    def _launch_persistent_context(self, p) -> object:
        """
        功能：执行 DouyinCollector._launch_persistent_context 的内部处理逻辑。
        参数：
        - p：输入参数。
        返回值：
        - object：函数处理结果。
        """
        last_exc: Exception | None = None
        for label, kwargs in self._browser_launch_candidates(settings.playwright_headless):
            try:
                logger.info("Launching login browser via %s", label)
                return p.chromium.launch_persistent_context(
                    user_data_dir=settings.playwright_user_data_dir,
                    **kwargs,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Login browser launch failed via %s: %s", label, exc)
                last_exc = exc

        raise RuntimeError(f"All browser launch candidates failed: {last_exc}")

    def _launch_browser(self, p, headless: bool):
        """
        功能：执行 DouyinCollector._launch_browser 的内部处理逻辑。
        参数：
        - p：输入参数。
        - headless：输入参数。
        返回值：
        - 未显式标注：请以函数实现中的 return 语句为准。
        """
        last_exc: Exception | None = None
        for label, kwargs in self._browser_launch_candidates(headless):
            try:
                logger.info("Launching crawl browser via %s", label)
                return p.chromium.launch(**kwargs)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Crawl browser launch failed via %s: %s", label, exc)
                last_exc = exc

        raise RuntimeError(f"All browser launch candidates failed: {last_exc}")

    def logout(self) -> tuple[bool, str]:
        """
        功能：执行 DouyinCollector.logout 的核心业务逻辑。
        参数：
        - 无。
        返回值：
        - tuple[bool, str]：函数处理结果。
        """
        errors: list[str] = []

        # 如果仍有登录任务在跑，先取消，避免状态被并发覆盖。
        if self._login_task and not self._login_task.done():
            self._login_task.cancel()
            self._login_task = None

        try:
            if self.storage_state_path.exists():
                self.storage_state_path.unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"remove state failed: {exc}")

        # 清理 Playwright 用户数据目录，避免再次点击扫码时自动复用旧会话。
        user_data_dir = Path(settings.playwright_user_data_dir)
        try:
            if user_data_dir.exists():
                shutil.rmtree(user_data_dir, ignore_errors=False)
            user_data_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"remove user_data_dir failed: {exc}")

        # 清理下载链路使用的 cookie 文件，避免旧会话影响入库。
        try:
            cookie_file = settings.storage_path / "tmp" / "yt_dlp_douyin_cookies.txt"
            if cookie_file.exists():
                cookie_file.unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"remove cookie_file failed: {exc}")

        if errors:
            self.status = "failed"
            self.message = "; ".join(errors)[:1000]
            return False, self.message

        self.status = "idle"
        self.message = "Logged out. Please scan QR code again."
        return True, self.message

    def start_login(self) -> tuple[bool, str]:
        # 启动扫码登录任务：只负责触发，不阻塞 API 请求线程。
        """
        功能：执行 DouyinCollector.start_login 的核心业务逻辑。
        参数：
        - 无。
        返回值：
        - tuple[bool, str]：函数处理结果。
        """
        if self.status == "pending" and self._login_task and not self._login_task.done():
            return False, "Login already in progress"

        self.status = "pending"
        self.message = "Scan QR code in the opened browser window"
        self._login_task = asyncio.create_task(self._login_flow())
        return True, self.message

    async def _login_flow(self) -> None:
        """
        功能：执行 DouyinCollector._login_flow 的内部处理逻辑。
        参数：
        - 无。
        返回值：
        - None：函数处理结果。
        """
        await asyncio.to_thread(self._login_flow_sync)

    def _login_flow_sync(self) -> None:
        """
        功能：执行 DouyinCollector._login_flow_sync 的内部处理逻辑。
        参数：
        - 无。
        返回值：
        - None：函数处理结果。
        """
        try:
            _ensure_windows_proactor_policy()
            with sync_playwright() as p:
                context = self._launch_persistent_context(p)
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(settings.douyin_home_url, timeout=120_000)

                found = False
                for _ in range(120):
                    cookies = context.cookies()
                    has_login_cookie = any(c.get("name") in {"sessionid", "sid_guard"} for c in cookies)
                    if has_login_cookie:
                        found = True
                        break
                    time.sleep(1)

                if not found:
                    self.status = "failed"
                    self.message = "Login timeout. Please retry."
                    context.close()
                    return

                context.storage_state(path=str(self.storage_state_path))
                context.close()

                self.status = "logged_in"
                self.message = "Login successful"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Douyin login failed")
            self.status = "failed"
            self.message = str(exc)

    async def fetch_snapshot(
        self,
        max_collections: int = 100,
        max_items_per_collection: int = 500,
    ) -> FavoriteScrapeSnapshot:
        """
        功能：执行 DouyinCollector.fetch_snapshot 的核心业务逻辑。
        参数：
        - max_collections：输入参数。
        - max_items_per_collection：输入参数。
        返回值：
        - FavoriteScrapeSnapshot：函数处理结果。
        """
        if not self.storage_state_path.exists():
            raise RuntimeError("No login state found. Please login first.")

        return await asyncio.to_thread(
            self._fetch_snapshot_sync,
            max_collections,
            max_items_per_collection,
        )

    @staticmethod
    def _duration_to_seconds(raw_duration: object) -> int | None:
        """
        功能：执行 DouyinCollector._duration_to_seconds 的内部处理逻辑。
        参数：
        - raw_duration：输入参数。
        返回值：
        - int | None：函数处理结果。
        """
        if raw_duration is None:
            return None
        try:
            duration = int(raw_duration)
        except (TypeError, ValueError):
            return None
        if duration <= 0:
            return None
        return duration // 1000 if duration > 1000 else duration

    def _fetch_snapshot_via_collects_module(
        self,
        page,
        max_collections: int,
        max_items_per_collection: int,
    ) -> FavoriteScrapeSnapshot:
        # 通过页面内 webpack 导出的 collects API 读取收藏夹与视频列表
        """
        功能：执行 DouyinCollector._fetch_snapshot_via_collects_module 的内部处理逻辑。
        参数：
        - page：输入参数。
        - max_collections：输入参数。
        - max_items_per_collection：输入参数。
        返回值：
        - FavoriteScrapeSnapshot：函数处理结果。
        """
        raw_result = page.evaluate(
            """
            async ({ maxCollections, maxItemsPerCollection }) => {
                const getWebpackRequire = () => {
                    const chunks = window.webpackChunkdouyin_web;
                    if (!Array.isArray(chunks)) return null;
                    const req = chunks.push([[Symbol("collector")], {}, (r) => r]);
                    try { chunks.pop(); } catch (e) {}
                    return req;
                };

                const req = getWebpackRequire();
                if (!req || !req.m) {
                    return { ok: false, error: "no_webpack_require" };
                }

                let moduleId = null;
                for (const [id, mod] of Object.entries(req.m)) {
                    let src = "";
                    try { src = Function.prototype.toString.call(mod); } catch (e) { continue; }
                    if (
                        src.includes("/aweme/v1/web/collects/list/") &&
                        src.includes("/aweme/v1/web/collects/video/list/")
                    ) {
                        moduleId = id;
                        break;
                    }
                }
                if (!moduleId) {
                    return { ok: false, error: "collect_module_not_found" };
                }

                const api = req(Number(moduleId));
                const listFn = api.So;
                const videoFn = api.d6;
                if (typeof listFn !== "function" || typeof videoFn !== "function") {
                    return {
                        ok: false,
                        error: "collect_api_exports_missing",
                        moduleId,
                        exportKeys: Object.keys(api || {}),
                    };
                }

                const collections = [];
                let cursor = 0;
                let hasMore = true;
                let guard = 0;
                while (hasMore && guard < 30 && collections.length < maxCollections) {
                    guard += 1;
                    const resp = await listFn({ cursor, offset: Math.min(30, maxCollections) });
                    if (!resp || typeof resp.statusCode !== "number") {
                        return { ok: false, error: "collect_list_bad_resp", moduleId };
                    }
                    if (resp.statusCode !== 0) {
                        return { ok: false, error: "collect_list_status", statusCode: resp.statusCode, moduleId };
                    }

                    const data = Array.isArray(resp.data) ? resp.data : [];
                    for (const c of data) {
                        if (!c || !c.collectionFolderId) continue;
                        collections.push(c);
                        if (collections.length >= maxCollections) break;
                    }
                    cursor = Number(resp.cursor || 0);
                    hasMore = Boolean(resp.hasMore);
                }

                const itemsByCollection = {};
                for (const collection of collections) {
                    const cid = String(collection.collectionFolderId);
                    const rows = [];
                    const seenIds = new Set();
                    let cCursor = 0;
                    let cHasMore = true;
                    let cGuard = 0;
                    while (cHasMore && cGuard < 120 && rows.length < maxItemsPerCollection) {
                        cGuard += 1;
                        const videoResp = await videoFn({ collectsId: cid, cursor: cCursor, offset: 20 });
                        if (!videoResp || typeof videoResp.statusCode !== "number") {
                            return { ok: false, error: "collect_video_bad_resp", moduleId, collectionId: cid };
                        }
                        if (videoResp.statusCode !== 0) {
                            return {
                                ok: false,
                                error: "collect_video_status",
                                statusCode: videoResp.statusCode,
                                moduleId,
                                collectionId: cid,
                            };
                        }

                        const videos = Array.isArray(videoResp.data) ? videoResp.data : [];
                        for (const video of videos) {
                            const awemeId = String(video?.awemeId || video?.groupId || "").trim();
                            if (!awemeId || seenIds.has(awemeId)) continue;
                            seenIds.add(awemeId);
                            rows.push({
                                awemeId,
                                title: String(video?.itemTitle || video?.desc || "Untitled"),
                                author: String(video?.authorInfo?.nickname || ""),
                                durationMs: Number(video?.video?.duration || 0) || null,
                            });
                            if (rows.length >= maxItemsPerCollection) break;
                        }

                        cCursor = Number(videoResp.cursor || 0);
                        cHasMore = Boolean(videoResp.hasMore);
                    }
                    itemsByCollection[cid] = rows;
                }

                return { ok: true, moduleId, collections, itemsByCollection };
            }
            """,
            {
                "maxCollections": max_collections,
                "maxItemsPerCollection": max_items_per_collection,
            },
        )

        if not isinstance(raw_result, dict):
            raise RuntimeError("collects module returned invalid payload")
        if not raw_result.get("ok"):
            raise RuntimeError(f"collects module failed: {raw_result}")

        raw_collections = raw_result.get("collections")
        raw_items_by_collection = raw_result.get("itemsByCollection")
        if not isinstance(raw_collections, list) or not isinstance(raw_items_by_collection, dict):
            raise RuntimeError("collects module returned invalid structure")

        collections: list[FavoriteScrapedCollection] = []
        videos_by_id: dict[str, FavoriteScrapedVideo] = {}

        for collection in raw_collections:
            if not isinstance(collection, dict):
                continue
            collection_id = str(collection.get("collectionFolderId") or "").strip()
            if not collection_id:
                continue
            title = str(collection.get("collectionFolderName") or "").strip() or "未命名收藏夹"
            item_count = int(collection.get("videoTotal") or 0)
            cover_url = collection.get("cover")
            if cover_url is not None:
                cover_url = str(cover_url)

            collections.append(
                FavoriteScrapedCollection(
                    platform_collection_id=collection_id,
                    title=title[:255],
                    item_count=max(item_count, 0),
                    cover_url=cover_url,
                )
            )

            rows = raw_items_by_collection.get(collection_id, [])
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                aweme_id = str(row.get("awemeId") or "").strip()
                if not aweme_id or not aweme_id.isdigit():
                    continue
                video = videos_by_id.get(aweme_id)
                if video is None:
                    video = FavoriteScrapedVideo(
                        platform_item_id=aweme_id,
                        url=f"https://www.douyin.com/video/{aweme_id}",
                        title=(str(row.get("title") or "Untitled").strip() or "Untitled")[:500],
                        author=str(row.get("author") or "").strip()[:255],
                        duration_sec=self._duration_to_seconds(row.get("durationMs")),
                    )
                    videos_by_id[aweme_id] = video
                video.collection_ids.add(collection_id)

        if not collections:
            raise RuntimeError("No collections found from collects module")

        logger.info(
            "Fetched %d collections and %d videos from Douyin collects module",
            len(collections),
            len(videos_by_id),
        )
        return FavoriteScrapeSnapshot(collections=collections, videos=list(videos_by_id.values()))

    def _fetch_snapshot_sync(self, max_collections: int, max_items_per_collection: int) -> FavoriteScrapeSnapshot:
        """
        功能：执行 DouyinCollector._fetch_snapshot_sync 的内部处理逻辑。
        参数：
        - max_collections：输入参数。
        - max_items_per_collection：输入参数。
        返回值：
        - FavoriteScrapeSnapshot：函数处理结果。
        """
        _ensure_windows_proactor_policy()
        with sync_playwright() as p:
            browser = self._launch_browser(p, headless=True)
            context = browser.new_context(storage_state=str(self.storage_state_path))
            page = context.new_page()
            page.goto(settings.favorites_url, timeout=120_000)
            time.sleep(2.0)

            snapshot = self._fetch_snapshot_via_collects_module(
                page,
                max_collections=max_collections,
                max_items_per_collection=max_items_per_collection,
            )

            context.close()
            browser.close()
            return snapshot


collector = DouyinCollector()
