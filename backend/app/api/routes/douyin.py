from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import FavoriteListResponse
from app.services.favorites_service import favorites_service

router = APIRouter()


@router.get("/favorites", response_model=FavoriteListResponse)
async def list_favorites(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    sync: bool = Query(True),
    db: Session = Depends(get_db),
) -> FavoriteListResponse:
    try:
        if sync:
            await favorites_service.sync_from_douyin(db)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to sync favorites: {exc}") from exc

    items, total = favorites_service.list_favorites(db, page=page, size=size)
    return FavoriteListResponse(items=items, page=page, size=size, total=total)
