from __future__ import annotations

"""API 路由聚合层，统一挂载 auth/favorites/knowledge/chat 子路由。"""

from fastapi import APIRouter

from app.api.routes import auth, chat, favorites, knowledge

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth/douyin", tags=["auth"])
api_router.include_router(favorites.router, prefix="/favorites", tags=["favorites"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
