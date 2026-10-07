from __future__ import annotations

"""问答与会话管理接口：提问、流式输出、会话增删查。"""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import ChatMessage, FavoriteVideo, VideoCache
from app.schemas import (
    ChatAskRequest,
    ChatAskResponse,
    ChatHit,
    ChatMessagesResponse,
    ChatSessionsResponse,
)
from app.services.rag_service import rag_service

router = APIRouter()


def _source_metadata(db: Session, chunk_ids: set[str], video_ids: set[str]) -> tuple[dict, dict]:
    """从本地缓存和收藏记录补充视频链接与转写片段时间点。"""
    if not video_ids:
        return {}, {}

    cache_rows = db.scalars(select(VideoCache).where(VideoCache.platform_item_id.in_(video_ids))).all()
    favorite_rows = db.scalars(
        select(FavoriteVideo)
        .where(FavoriteVideo.platform_item_id.in_(video_ids), FavoriteVideo.is_active.is_(True))
        .order_by(FavoriteVideo.updated_at.desc())
    ).all()

    videos: dict[str, dict] = {}
    for row in favorite_rows:
        videos.setdefault(row.platform_item_id, {"title": row.title, "url": row.url})

    chunks: dict[str, dict] = {}
    for row in cache_rows:
        videos[row.platform_item_id] = {"title": row.title, "url": row.url}
        fts_chunk_id = f"{row.platform_item_id}:fts"
        if fts_chunk_id in chunk_ids:
            chunks[fts_chunk_id] = {
                "platform_item_id": row.platform_item_id,
                "title": row.title,
                "url": row.url,
                "text": (row.transcript_text or "")[:1200],
                "start_ms": None,
                "end_ms": None,
            }
        payload = row.chunk_payload if isinstance(row.chunk_payload, list) else []
        for item in payload:
            if not isinstance(item, dict):
                continue
            chunk_id = str(item.get("chunk_id") or "")
            if chunk_id in chunk_ids:
                chunks[chunk_id] = {
                    "platform_item_id": row.platform_item_id,
                    "title": row.title,
                    "url": row.url,
                    "text": str(item.get("text") or ""),
                    "start_ms": item.get("start_ms"),
                    "end_ms": item.get("end_ms"),
                }
    return videos, chunks


def _enrich_hits(db: Session, hits: list[ChatHit]) -> list[ChatHit]:
    video_ids = {hit.platform_item_id for hit in hits if hit.platform_item_id}
    chunk_ids = {hit.chunk_id for hit in hits if hit.chunk_id}
    videos, chunks = _source_metadata(db, chunk_ids, video_ids)

    return [
        hit.model_copy(
            update={
                "title": (
                    hit.title
                    or chunks.get(hit.chunk_id, {}).get("title")
                    or videos.get(hit.platform_item_id, {}).get("title", "")
                ),
                "url": (
                    videos.get(hit.platform_item_id, {}).get("url")
                    or chunks.get(hit.chunk_id, {}).get("url", "")
                ),
                "text": hit.text or chunks.get(hit.chunk_id, {}).get("text", ""),
                "start_ms": chunks.get(hit.chunk_id, {}).get("start_ms"),
                "end_ms": chunks.get(hit.chunk_id, {}).get("end_ms"),
            }
        )
        for hit in hits
    ]


def _history_hits(message: ChatMessage, videos: dict, chunks: dict) -> list[ChatHit]:
    video_ids = message.retrieved_video_ids or []
    chunk_ids = message.retrieved_chunk_ids or []
    hits: list[ChatHit] = []
    seen_videos: set[str] = set()
    for chunk_id in chunk_ids:
        chunk = chunks.get(chunk_id)
        if not chunk:
            continue
        video_id = chunk["platform_item_id"]
        seen_videos.add(video_id)
        hits.append(
            ChatHit(
                chunk_id=chunk_id,
                platform_item_id=video_id,
                title=chunk.get("title", ""),
                score=0.0,
                text=chunk.get("text", ""),
                url=chunk.get("url", ""),
                start_ms=chunk.get("start_ms"),
                end_ms=chunk.get("end_ms"),
            )
        )

    for video_id in video_ids:
        if video_id in seen_videos:
            continue
        video = videos.get(video_id, {})
        hits.append(
            ChatHit(
                chunk_id="",
                platform_item_id=video_id,
                title=video.get("title", ""),
                score=0.0,
                text="",
                url=video.get("url", ""),
            )
        )
    return hits


def _sse_event(event: str, payload: dict) -> str:
    """
    功能：执行 _sse_event 的内部处理逻辑。
    参数：
    - event：输入参数。
    - payload：输入参数。
    返回值：
    - str：函数处理结果。
    """
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/ask", response_model=ChatAskResponse)
def ask(payload: ChatAskRequest, db: Session = Depends(get_db)) -> ChatAskResponse:
    """
    功能：执行 ask 的核心业务逻辑。
    参数：
    - payload：输入参数。
    - db：输入参数。
    返回值：
    - ChatAskResponse：函数处理结果。
    """
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query is empty")

    try:
        response = rag_service.answer(db, payload.query, payload.session_id, payload.collection_ids)
        return response.model_copy(update={"hits": _enrich_hits(db, response.hits)})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/ask/stream")
def ask_stream(payload: ChatAskRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    """
    功能：执行 ask_stream 的核心业务逻辑。
    参数：
    - payload：输入参数。
    - db：输入参数。
    返回值：
    - StreamingResponse：函数处理结果。
    """
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query is empty")

    def _generate():
        """
        功能：执行 _generate 的内部处理逻辑。
        参数：
        - 无。
        返回值：
        - 未显式标注：请以函数实现中的 return 语句为准。
        """
        try:
            for event, data in rag_service.answer_stream(db, payload.query, payload.session_id, payload.collection_ids):
                if event == "meta" and isinstance(data, dict):
                    raw_hits = data.get("hits", [])
                    hits = [ChatHit.model_validate(item) for item in raw_hits if isinstance(item, dict)]
                    data["hits"] = [hit.model_dump() for hit in _enrich_hits(db, hits)]
                yield _sse_event(event, data)
        except Exception as exc:  # noqa: BLE001
            yield _sse_event("error", {"message": str(exc)})

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions", response_model=ChatSessionsResponse)
def list_sessions(
    limit: int = Query(30, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ChatSessionsResponse:
    """
    功能：列出 list_sessions 对应的数据集合。
    参数：
    - limit：输入参数。
    - db：输入参数。
    返回值：
    - ChatSessionsResponse：函数处理结果。
    """
    return rag_service.list_sessions(db, limit=limit)


@router.get("/sessions/{session_id}/messages", response_model=ChatMessagesResponse)
def get_session_messages(session_id: int, db: Session = Depends(get_db)) -> ChatMessagesResponse:
    """
    功能：获取 get_session_messages 对应的数据或对象。
    参数：
    - session_id：输入参数。
    - db：输入参数。
    返回值：
    - ChatMessagesResponse：函数处理结果。
    """
    response = rag_service.get_session_messages(db, session_id)
    if response is None:
        raise HTTPException(status_code=404, detail="Session not found")

    rows = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
    ).all()
    rows_by_id = {row.id: row for row in rows}
    assistant_rows = [row for row in rows if row.role == "assistant"]
    video_ids = {video_id for row in assistant_rows for video_id in (row.retrieved_video_ids or [])}
    chunk_ids = {chunk_id for row in assistant_rows for chunk_id in (row.retrieved_chunk_ids or [])}
    videos, chunks = _source_metadata(db, chunk_ids, video_ids)
    items = [
        item.model_copy(update={"hits": _history_hits(rows_by_id[item.id], videos, chunks)})
        if item.role == "assistant" and item.id in rows_by_id
        else item
        for item in response.items
    ]
    return response.model_copy(update={"items": items})


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    """
    功能：删除 delete_session 对应的资源或记录。
    参数：
    - session_id：输入参数。
    - db：输入参数。
    返回值：
    - dict[str, bool]：函数处理结果。
    """
    deleted = rag_service.delete_session(db, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": True}


@router.delete("/sessions/{session_id}/messages")
def clear_session_messages(session_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    """
    功能：执行 clear_session_messages 的核心业务逻辑。
    参数：
    - session_id：输入参数。
    - db：输入参数。
    返回值：
    - dict[str, bool]：函数处理结果。
    """
    cleared = rag_service.clear_session_messages(db, session_id)
    if not cleared:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"cleared": True}
