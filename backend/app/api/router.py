from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import auth, chat, douyin, ingest

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth/douyin", tags=["auth"])
api_router.include_router(douyin.router, prefix="/douyin", tags=["douyin"])
api_router.include_router(ingest.router, prefix="/ingest", tags=["ingest"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
