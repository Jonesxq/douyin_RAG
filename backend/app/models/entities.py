from __future__ import annotations

"""ORM 实体定义：收藏夹、视频缓存、同步任务、聊天会话等。"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    is_logged_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    message: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class FavoriteCollection(Base):
    __tablename__ = "favorite_collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(32), default="douyin", nullable=False)
    platform_collection_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cover_url: Mapped[str | None] = mapped_column(String(1024))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    videos = relationship("FavoriteVideo", back_populates="collection", cascade="all, delete-orphan")
    tasks = relationship("SyncTask", back_populates="collection")

    __table_args__ = (
        UniqueConstraint("platform", "platform_collection_id", name="uq_platform_collection"),
        Index("idx_fav_collection_active", "platform", "is_active"),
    )


class FavoriteVideo(Base):
    __tablename__ = "favorite_videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("favorite_collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform_item_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    author: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    fav_time: Mapped[datetime | None] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    collection = relationship("FavoriteCollection", back_populates="videos")

    __table_args__ = (
        UniqueConstraint("collection_id", "platform_item_id", name="uq_collection_video"),
        Index("idx_fav_video_collection_active", "collection_id", "is_active"),
    )


class VideoCache(Base):
    __tablename__ = "video_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform_item_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    author: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    transcript_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    transcript_lang: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    chunk_payload: Mapped[list[dict] | None] = mapped_column(JSON)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_source: Mapped[str] = mapped_column(String(32), default="asr_local", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    error_msg: Mapped[str] = mapped_column(Text, default="", nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SyncTask(Base):
    __tablename__ = "sync_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_type: Mapped[str] = mapped_column(String(32), default="knowledge_sync", nullable=False)
    collection_id: Mapped[int | None] = mapped_column(
        ForeignKey("favorite_collections.id", ondelete="SET NULL"),
        index=True,
    )
    collection_platform_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    step: Mapped[str] = mapped_column(String(64), default="queued", nullable=False)
    progress_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_done: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    error_msg: Mapped[str] = mapped_column(Text, default="", nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    collection = relationship("FavoriteCollection", back_populates="tasks")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), default="New Chat", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    route_type: Mapped[str] = mapped_column(String(32), default="vector", nullable=False)
    retrieved_video_ids: Mapped[list[str] | None] = mapped_column(JSON)
    retrieved_chunk_ids: Mapped[list[str] | None] = mapped_column(JSON)
    model: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    session = relationship("ChatSession", back_populates="messages")
