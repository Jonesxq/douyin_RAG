from __future__ import annotations

"""媒体处理服务：解析可下载媒体地址并抽取音频。"""

import json
import logging
import shutil
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from yt_dlp import YoutubeDL

from app.core.config import get_settings
from app.services.douyin_collector import _find_project_chromium_executable

settings = get_settings()
logger = logging.getLogger(__name__)

AWEME_DETAIL_API_MARKER = "/aweme/v1/web/aweme/detail/"
DOUYIN_REFERER = "https://www.douyin.com/"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class MediaPipelineError(RuntimeError):
    pass


def _is_douyin_url(url: str) -> bool:
    """
    功能：执行 _is_douyin_url 的内部处理逻辑。
    参数：
    - url：输入参数。
    返回值：
    - bool：函数处理结果。
    """
    return "douyin.com" in url


def _build_browser_launch_kwargs() -> list[dict]:
    """
    功能：执行 _build_browser_launch_kwargs 的内部处理逻辑。
    参数：
    - 无。
    返回值：
    - list[dict]：函数处理结果。
    """
    candidates: list[dict] = []

    executable = _find_project_chromium_executable()
    if executable:
        candidates.append({"headless": True, "executable_path": str(executable)})

    if settings.playwright_browser_channel.strip():
        candidates.append({"headless": True, "channel": settings.playwright_browser_channel.strip()})
    else:
        candidates.append({"headless": True, "channel": "msedge"})

    candidates.append({"headless": True})
    return candidates


def _resolve_ffmpeg_path() -> str:
    # 依次尝试 .env 配置、PATH、常见安装路径。
    """
    功能：执行 _resolve_ffmpeg_path 的内部处理逻辑。
    参数：
    - 无。
    返回值：
    - str：函数处理结果。
    """
    if settings.ffmpeg_path.strip():
        configured = Path(settings.ffmpeg_path.strip())
        if configured.exists():
            return str(configured)

    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path

    common_candidates = [
        Path("C:/ffmpeg/bin/ffmpeg.exe"),
        Path.home() / "ffmpeg" / "bin" / "ffmpeg.exe",
        settings.storage_path / "ffmpeg" / "bin" / "ffmpeg.exe",
    ]
    for candidate in common_candidates:
        if candidate.exists():
            return str(candidate)

    raise MediaPipelineError(
        "ffmpeg is not installed or not in PATH. Set FFMPEG_PATH in backend/.env, "
        "for example: FFMPEG_PATH=C:/ffmpeg/bin/ffmpeg.exe"
    )


def _export_cookiefile_from_state() -> Path:
    """
    功能：执行 _export_cookiefile_from_state 的内部处理逻辑。
    参数：
    - 无。
    返回值：
    - Path：函数处理结果。
    """
    state_path = Path(settings.playwright_user_data_dir) / "state.json"
    if not state_path.exists():
        raise MediaPipelineError(f"Playwright storage state missing: {state_path}")

    with state_path.open("r", encoding="utf-8") as f:
        state = json.load(f)

    cookies = state.get("cookies", []) if isinstance(state, dict) else []
    cookie_dir = settings.storage_path / "tmp"
    cookie_dir.mkdir(parents=True, exist_ok=True)
    cookie_file = cookie_dir / "yt_dlp_douyin_cookies.txt"

    lines = [
        "# Netscape HTTP Cookie File",
        "# Generated from Playwright storage state",
    ]
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        domain = str(cookie.get("domain") or "").strip()
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "")
        if not domain or not name:
            continue

        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        path = str(cookie.get("path") or "/")
        secure = "TRUE" if bool(cookie.get("secure")) else "FALSE"
        expires_raw = cookie.get("expires")
        try:
            expires = int(float(expires_raw)) if expires_raw and float(expires_raw) > 0 else 0
        except (TypeError, ValueError):
            expires = 0

        lines.append("\t".join([domain, include_subdomains, path, secure, str(expires), name, value]))

    cookie_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return cookie_file


def _extract_media_url_from_detail(detail_payload: dict) -> str:
    """
    功能：执行 _extract_media_url_from_detail 的内部处理逻辑。
    参数：
    - detail_payload：输入参数。
    返回值：
    - str：函数处理结果。
    """
    video = detail_payload.get("video")
    if not isinstance(video, dict):
        return ""

    play_addr = video.get("play_addr")
    if isinstance(play_addr, dict):
        url_list = play_addr.get("url_list")
        if isinstance(url_list, list):
            for item in url_list:
                if isinstance(item, str) and item.startswith("http"):
                    return item

    bit_rate = video.get("bit_rate")
    if isinstance(bit_rate, list):
        for stream in bit_rate:
            if not isinstance(stream, dict):
                continue
            play_addr = stream.get("play_addr")
            if not isinstance(play_addr, dict):
                continue
            url_list = play_addr.get("url_list")
            if not isinstance(url_list, list):
                continue
            for item in url_list:
                if isinstance(item, str) and item.startswith("http"):
                    return item
    return ""


def _resolve_media_url_via_playwright(url: str) -> str:
    """
    功能：执行 _resolve_media_url_via_playwright 的内部处理逻辑。
    参数：
    - url：输入参数。
    返回值：
    - str：函数处理结果。
    """
    state_path = Path(settings.playwright_user_data_dir) / "state.json"
    if not state_path.exists():
        raise MediaPipelineError("No login state found for Douyin download")

    last_error: Exception | None = None
    for launch_kwargs in _build_browser_launch_kwargs():
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(**launch_kwargs)
                context = browser.new_context(storage_state=str(state_path))
                page = context.new_page()
                media_url = ""

                def _on_response(response) -> None:
                    """
                    功能：执行 _on_response 的内部处理逻辑。
                    参数：
                    - response：输入参数。
                    返回值：
                    - None：函数处理结果。
                    """
                    nonlocal media_url
                    if media_url or AWEME_DETAIL_API_MARKER not in response.url:
                        return
                    try:
                        payload = response.json()
                    except Exception:  # noqa: BLE001
                        return
                    if not isinstance(payload, dict):
                        return
                    detail = payload.get("aweme_detail")
                    if not isinstance(detail, dict):
                        return
                    media_url = _extract_media_url_from_detail(detail)

                page.on("response", _on_response)
                page.goto(url, timeout=120_000, wait_until="domcontentloaded")

                for _ in range(24):
                    if media_url:
                        break
                    time.sleep(0.5)

                if not media_url:
                    media_url = page.evaluate(
                        "(() => { const v = document.querySelector('video'); return v ? (v.currentSrc || v.src || '') : ''; })()"
                    )

                context.storage_state(path=str(state_path))
                context.close()
                browser.close()

                if not media_url or not str(media_url).startswith("http"):
                    raise MediaPipelineError("Failed to resolve media URL from Douyin page")

                return str(media_url)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("Resolve media URL via %s failed: %s", launch_kwargs, exc)
            continue

    raise MediaPipelineError(f"Failed to resolve media URL: {last_error}")


def _extract_audio_from_media_url(media_url: str, output_audio_path: Path) -> Path:
    """
    功能：执行 _extract_audio_from_media_url 的内部处理逻辑。
    参数：
    - media_url：输入参数。
    - output_audio_path：输入参数。
    返回值：
    - Path：函数处理结果。
    """
    ffmpeg_path = _resolve_ffmpeg_path()
    headers = f"Referer: {DOUYIN_REFERER}\r\nUser-Agent: {UA}\r\n"
    cmd = [
        ffmpeg_path,
        "-y",
        "-headers",
        headers,
        "-i",
        media_url,
        "-vn",
        "-acodec",
        "libmp3lame",
        "-ab",
        "96k",
        str(output_audio_path),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise MediaPipelineError(f"ffmpeg media-url extract failed: {completed.stderr[:2000]}")
    return output_audio_path


def _download_audio_via_ytdlp(url: str, platform_item_id: str) -> Path:
    """
    功能：执行 _download_audio_via_ytdlp 的内部处理逻辑。
    参数：
    - url：输入参数。
    - platform_item_id：输入参数。
    返回值：
    - Path：函数处理结果。
    """
    audio_dir = settings.storage_path / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(audio_dir / f"{platform_item_id}.%(ext)s")

    options: dict = {
        "outtmpl": output_template,
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "96",
            }
        ],
        "retries": 2,
    }

    if _is_douyin_url(url):
        options["cookiefile"] = str(_export_cookiefile_from_state())
        options["http_headers"] = {
            "Referer": DOUYIN_REFERER,
            "User-Agent": UA,
        }

    with YoutubeDL(options) as ydl:
        ydl.extract_info(url, download=True)

    audio_path = audio_dir / f"{platform_item_id}.mp3"
    if not audio_path.exists():
        matches = sorted(audio_dir.glob(f"{platform_item_id}.*"))
        if not matches:
            raise MediaPipelineError(f"Audio download failed for {url}")
        audio_path = matches[0]

    return audio_path


def download_audio(url: str, platform_item_id: str) -> Path:
    # 抖音优先走 Playwright 解析媒体地址，失败后降级到 yt-dlp。
    """
    功能：执行 download_audio 的核心业务逻辑。
    参数：
    - url：输入参数。
    - platform_item_id：输入参数。
    返回值：
    - Path：函数处理结果。
    """
    audio_dir = settings.storage_path / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / f"{platform_item_id}.mp3"

    if _is_douyin_url(url):
        try:
            media_url = _resolve_media_url_via_playwright(url)
            return _extract_audio_from_media_url(media_url, audio_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Playwright audio extraction fallback to yt-dlp for %s: %s", platform_item_id, exc)

    return _download_audio_via_ytdlp(url, platform_item_id)
