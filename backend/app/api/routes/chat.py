from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import ChatQueryRequest, ChatResponse
from app.services.rag_service import rag_service

router = APIRouter()


@router.post("/query", response_model=ChatResponse)
def query(payload: ChatQueryRequest, db: Session = Depends(get_db)) -> ChatResponse:
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query is empty")

    try:
        return rag_service.answer(db, payload.query, payload.session_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
