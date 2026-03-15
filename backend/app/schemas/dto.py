from __future__ import annotations

"""Pydantic DTO 定义，用于 API 请求/响应数据校验。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LoginStartResponse(BaseModel):
    started: bool
    message: str


class LoginStatusResponse(BaseModel):
    status: Literal["idle", "pending", "logged_in", "failed"]
    message: str = ""


class LoginLogoutResponse(BaseModel):
    success: bool
    message: str


class FavoriteCollectionDTO(BaseModel):
    id: int
    collection_id: str
    title: str
    item_count: int
    is_active: bool


class FavoriteCollectionsResponse(BaseModel):
    items: list[FavoriteCollectionDTO]


class FavoriteVideoDTO(BaseModel):
    id: int
    collection_id: str
    platform_item_id: str
    url: str
    title: str
    author: str
    duration_sec: int | None = None
    status: str


class FavoriteVideosResponse(BaseModel):
    items: list[FavoriteVideoDTO]
    page: int
    size: int
    total: int


class FavoritesSyncResponse(BaseModel):
    collections_total: int
    videos_total: int
    added_videos: int
    removed_videos: int


class KnowledgeSyncRequest(BaseModel):
    collection_ids: list[str] = Field(default_factory=list)


class SyncTaskDTO(BaseModel):
    id: int
    task_type: str
    collection_id: str | None = None
    status: str
    step: str
    progress_total: int
    progress_done: int
    message: str
    error_msg: str
    retry_count: int
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class KnowledgeSyncResponse(BaseModel):
    tasks: list[SyncTaskDTO]


class KnowledgeStatsResponse(BaseModel):
    total_collections: int
    total_videos: int
    processed_videos: int
    total_chunks: int


class ChatHit(BaseModel):
    chunk_id: str
    platform_item_id: str
    title: str
    score: float
    text: str


class ChatAskRequest(BaseModel):
    query: str
    session_id: int | None = None
    collection_ids: list[str] | None = None


class ChatAskResponse(BaseModel):
    session_id: int
    route_type: str
    answer: str
    latency_ms: int
    hits: list[ChatHit]


class ChatSessionDTO(BaseModel):
    id: int
    title: str
    message_count: int
    last_message_at: datetime | None = None
    created_at: datetime


class ChatSessionsResponse(BaseModel):
    items: list[ChatSessionDTO]


class ChatMessageDTO(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    route_type: str
    created_at: datetime


class ChatMessagesResponse(BaseModel):
    session_id: int
    items: list[ChatMessageDTO]


class ErrorResponse(BaseModel):
    detail: str
