from __future__ import annotations

"""项目配置中心：读取 .env、路径归一化、启动前环境约束。"""

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    app_name: str = "Douyin Favorites RAG"
    app_env: str = "dev"
    api_prefix: str = ""

    cors_origins: str = "http://localhost:5173"

    database_url: str = "sqlite:///./backend/storage/douyin_rag.db"

    storage_root: str = "backend/storage"
    playwright_user_data_dir: str = "backend/storage/playwright"
    playwright_browsers_path: str = "backend/storage/playwright-browsers"
    playwright_browser_channel: str = ""
    favorites_url: str = "https://www.douyin.com/user/self?showTab=favorite_collection"
    douyin_home_url: str = "https://www.douyin.com/"
    playwright_headless: bool = False

    task_worker_concurrency: int = 2
    task_retry_count: int = 2

    asr_model_size: str = "small"
    asr_device: str = "cpu"
    asr_compute_type: str = "int8"
    ffmpeg_path: str = ""

    chroma_persist_directory: str = "backend/storage/chroma"
    chroma_collection_name: str = "video_chunks_local"
    chroma_distance: str = "cosine"

    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_chat_model: str = "qwen-plus"
    qwen_embedding_model: str = "text-embedding-v3"
    embedding_provider: str = "local"
    local_embedding_model: str = "BAAI/bge-small-zh-v1.5"
    local_embedding_cache_dir: str = "backend/storage/models"

    rag_topk_dense: int = 20
    rag_topk_fts: int = 20
    rag_context_count: int = 8
    rag_route_with_llm: bool = True
    chat_history_window: int = 6
    chat_max_content_chars: int = 1200

    startup_validate: bool = True
    startup_require_python312: bool = True

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> List[str]:
        """
        功能：执行 Settings.cors_origin_list 的核心业务逻辑。
        参数：
        - 无。
        返回值：
        - List[str]：函数处理结果。
        """
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def storage_path(self) -> Path:
        """
        功能：执行 Settings.storage_path 的核心业务逻辑。
        参数：
        - 无。
        返回值：
        - Path：函数处理结果。
        """
        return Path(self.storage_root)


def _resolve_project_path(value: str) -> Path:
    """
    功能：执行 _resolve_project_path 的内部处理逻辑。
    参数：
    - value：输入参数。
    返回值：
    - Path：函数处理结果。
    """
    path = Path(value)
    if path.is_absolute():
        return path

    normalized = value.replace("\\", "/").lstrip("./")
    if normalized.startswith("backend/"):
        return (PROJECT_ROOT / normalized).resolve()

    return (BACKEND_ROOT / path).resolve()


def _resolve_database_url(value: str) -> str:
    """
    功能：执行 _resolve_database_url 的内部处理逻辑。
    参数：
    - value：输入参数。
    返回值：
    - str：函数处理结果。
    """
    if not value.startswith("sqlite:///"):
        return value

    raw_path = value.removeprefix("sqlite:///")
    if raw_path in {":memory:", ""}:
        return value

    resolved = _resolve_project_path(raw_path)
    # Normalize Windows paths for SQLAlchemy URL parsing.
    return f"sqlite:///{resolved.as_posix()}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    功能：获取 get_settings 对应的数据或对象。
    参数：
    - 无。
    返回值：
    - Settings：函数处理结果。
    """
    settings = Settings()
    settings.database_url = _resolve_database_url(settings.database_url)
    settings.storage_root = str(_resolve_project_path(settings.storage_root))
    settings.playwright_user_data_dir = str(_resolve_project_path(settings.playwright_user_data_dir))
    settings.playwright_browsers_path = str(_resolve_project_path(settings.playwright_browsers_path))
    settings.chroma_persist_directory = str(_resolve_project_path(settings.chroma_persist_directory))
    settings.local_embedding_cache_dir = str(_resolve_project_path(settings.local_embedding_cache_dir))

    settings.storage_path.mkdir(parents=True, exist_ok=True)
    Path(settings.playwright_user_data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.playwright_browsers_path).mkdir(parents=True, exist_ok=True)
    Path(settings.chroma_persist_directory).mkdir(parents=True, exist_ok=True)
    Path(settings.local_embedding_cache_dir).mkdir(parents=True, exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = settings.playwright_browsers_path

    if settings.startup_require_python312 and (sys.version_info.major != 3 or sys.version_info.minor != 12):
        raise RuntimeError(
            "This project requires Python 3.12. "
            "Please run backend with uv and --python 3.12."
        )

    return settings
