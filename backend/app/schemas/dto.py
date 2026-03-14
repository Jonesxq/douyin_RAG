from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class FavoriteItem(BaseModel):
    id: int
    platform_item_id: str
    url: str
    title: str
    author: str
    duration_sec: int | None = None
    fav_time: datetime | None = None
    ingest_status: str


class LoginStartResponse(BaseModel):
    started: bool
    message: str


class LoginStatusResponse(BaseModel):
    status: Literal["idle", "pending", "logged_in", "failed"]
    message: str = ""


class FavoriteListResponse(BaseModel):
    items: list[FavoriteItem]
    page: int
    size: int
    total: int


class CreateIngestJobsRequest(BaseModel):
    item_ids: list[int] = Field(default_factory=list)


class IngestJobDTO(BaseModel):
    id: int
    source_item_id: int
    status: str
    step: str
    error_msg: str
    retry_count: int
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class CreateIngestJobsResponse(BaseModel):
    jobs: list[IngestJobDTO]


class ChunkHit(BaseModel):
    chunk_id: int
    source_item_id: int
    score: float
    text: str


class ChatQueryRequest(BaseModel):
    query: str
    session_id: int | None = None


class ChatResponse(BaseModel):
    session_id: int
    answer: str
    latency_ms: int
    hits: list[ChunkHit]


class ErrorResponse(BaseModel):
    detail: str
