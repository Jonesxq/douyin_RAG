from __future__ import annotations

"""问答与会话管理接口：提问、流式输出、会话增删查。"""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import (
    ChatAskRequest,
    ChatAskResponse,
    ChatMessagesResponse,
    ChatSessionsResponse,
)
from app.services.rag_service import rag_service

router = APIRouter()


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
        return rag_service.answer(db, payload.query, payload.session_id, payload.collection_ids)
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
    return response


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
