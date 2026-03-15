from __future__ import annotations

"""启动自检：检查 ffmpeg、Playwright、Chroma 与模型缓存目录。"""

import logging
import shutil
from pathlib import Path

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


def run_startup_checks() -> None:
    """
    功能：执行 run_startup_checks 的核心业务逻辑。
    参数：
    - 无。
    返回值：
    - None：函数处理结果。
    """
    if not settings.startup_validate:
        return

    issues: list[str] = []

    ffmpeg_ok = False
    if settings.ffmpeg_path.strip() and Path(settings.ffmpeg_path.strip()).exists():
        ffmpeg_ok = True
    if shutil.which("ffmpeg"):
        ffmpeg_ok = True
    if not ffmpeg_ok:
        issues.append(
            "ffmpeg not found in PATH and FFMPEG_PATH is not set. Ingest will fail until ffmpeg is available."
        )

    browser_path = Path(settings.playwright_browsers_path)
    chromium_exists = any(browser_path.glob("chromium-*/chrome-win/chrome.exe"))
    if not chromium_exists and not settings.playwright_browser_channel.strip():
        issues.append(
            "Playwright Chromium runtime not found in project storage. Run: "
            "uv run --project backend playwright install chromium"
        )

    chroma_dir = Path(settings.chroma_persist_directory)
    if not chroma_dir.exists():
        issues.append(f"Chroma persist directory missing: {chroma_dir}")

    cache_dir = Path(settings.local_embedding_cache_dir)
    if not cache_dir.exists():
        issues.append(f"Local embedding cache directory missing: {cache_dir}")

    if issues:
        for issue in issues:
            logger.warning("Startup check: %s", issue)
    else:
        logger.info("Startup checks passed")
