from __future__ import annotations

"""收藏夹同步与查询接口。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import (
    FavoriteCollectionsResponse,
    FavoritesSyncResponse,
    FavoriteVideosResponse,
)
from app.services.favorites_service import favorites_service

router = APIRouter()


@router.post("/sync", response_model=FavoritesSyncResponse)
async def sync_favorites(db: Session = Depends(get_db)) -> FavoritesSyncResponse:
    """
    功能：执行 sync_favorites 的同步逻辑。
    参数：
    - db：输入参数。
    返回值：
    - FavoritesSyncResponse：函数处理结果。
    """
    try:
        result = await favorites_service.sync_from_douyin(db)
        return FavoritesSyncResponse(**result)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to sync favorites: {exc}") from exc


@router.get("/collections", response_model=FavoriteCollectionsResponse)
def list_collections(db: Session = Depends(get_db)) -> FavoriteCollectionsResponse:
    """
    功能：列出 list_collections 对应的数据集合。
    参数：
    - db：输入参数。
    返回值：
    - FavoriteCollectionsResponse：函数处理结果。
    """
    items = favorites_service.list_collections(db)
    return FavoriteCollectionsResponse(items=items)


@router.get("/collections/{collection_id}/videos", response_model=FavoriteVideosResponse)
def list_collection_videos(
    collection_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> FavoriteVideosResponse:
    """
    功能：列出 list_collection_videos 对应的数据集合。
    参数：
    - collection_id：输入参数。
    - page：输入参数。
    - size：输入参数。
    - db：输入参数。
    返回值：
    - FavoriteVideosResponse：函数处理结果。
    """
    items, total = favorites_service.list_collection_videos(db, collection_id=collection_id, page=page, size=size)
    return FavoriteVideosResponse(items=items, page=page, size=size, total=total)
