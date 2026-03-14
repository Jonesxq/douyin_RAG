from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

from yt_dlp import YoutubeDL

from app.core.config import get_settings

settings = get_settings()


class MediaPipelineError(RuntimeError):
    pass


def sha256_file(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def download_video(url: str, platform_item_id: str) -> Path:
    video_dir = settings.storage_path / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)

    output_template = str(video_dir / f"{platform_item_id}.%(ext)s")

    options = {
        "outtmpl": output_template,
        "format": "bestvideo*+bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
    }

    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        file_path = ydl.prepare_filename(info)

    candidate = Path(file_path)
    if candidate.suffix != ".mp4":
        candidate = candidate.with_suffix(".mp4")

    if not candidate.exists():
        # fallback in case merge output naming changes
        matches = sorted(video_dir.glob(f"{platform_item_id}.*"))
        if not matches:
            raise MediaPipelineError(f"Video download failed for {url}")
        candidate = matches[0]

    return candidate


def extract_audio(video_path: Path, platform_item_id: str) -> Path:
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise MediaPipelineError("ffmpeg is not installed or not in PATH")

    audio_dir = settings.storage_path / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / f"{platform_item_id}.mp3"

    cmd = [
        ffmpeg_path,
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "libmp3lame",
        "-ab",
        "128k",
        str(audio_path),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise MediaPipelineError(f"ffmpeg extract failed: {completed.stderr}")

    return audio_path
