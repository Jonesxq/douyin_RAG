from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Douyin Favorites RAG"
    app_env: str = "dev"
    api_prefix: str = ""

    cors_origins: str = "http://localhost:5173"

    # SQLite default for personal local deployment.
    database_url: str = "sqlite:///./backend/storage/douyin_rag.db"

    storage_root: str = "backend/storage"
    playwright_user_data_dir: str = "backend/storage/playwright"
    favorites_url: str = "https://www.douyin.com/user/self?showTab=favorite_collection"
    douyin_home_url: str = "https://www.douyin.com/"
    playwright_headless: bool = False

    ingest_worker_concurrency: int = 2
    ingest_retry_count: int = 2

    asr_model_size: str = "small"
    asr_device: str = "cpu"
    asr_compute_type: str = "int8"

    chroma_persist_directory: str = "backend/storage/chroma"
    chroma_collection_name: str = "video_chunks"
    chroma_distance: str = "cosine"
    embedding_dim: int = 1024

    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_chat_model: str = "qwen-plus"
    qwen_embedding_model: str = "text-embedding-v3"

    rag_topk_dense: int = 20
    rag_topk_fts: int = 20
    rag_context_count: int = 8

    model_config = SettingsConfigDict(
        env_file="backend/.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> List[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def storage_path(self) -> Path:
        return Path(self.storage_root)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    Path(settings.playwright_user_data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.chroma_persist_directory).mkdir(parents=True, exist_ok=True)
    return settings
