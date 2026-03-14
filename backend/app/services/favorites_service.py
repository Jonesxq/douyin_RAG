from __future__ import annotations

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models import SourceItem
from app.schemas import FavoriteItem
from app.services.douyin_collector import collector


class FavoritesService:
    async def sync_from_douyin(self, db: Session) -> None:
        scraped_items = await collector.fetch_favorites(max_items=500)
        if not scraped_items:
            return

        ids = [item.platform_item_id for item in scraped_items]
        existing_items = db.execute(
            select(SourceItem).where(SourceItem.platform_item_id.in_(ids))
        ).scalars().all()
        existing_map = {item.platform_item_id: item for item in existing_items}

        for item in scraped_items:
            existing = existing_map.get(item.platform_item_id)
            if existing:
                existing.url = item.url
                existing.title = item.title
                existing.author = item.author
                existing.duration_sec = item.duration_sec
            else:
                db.add(
                    SourceItem(
                        platform="douyin",
                        platform_item_id=item.platform_item_id,
                        url=item.url,
                        title=item.title,
                        author=item.author,
                        duration_sec=item.duration_sec,
                        ingest_status="pending",
                    )
                )
        db.commit()

    def list_favorites(self, db: Session, page: int, size: int) -> tuple[list[FavoriteItem], int]:
        total = db.execute(select(func.count()).select_from(SourceItem)).scalar_one()
        offset = (page - 1) * size
        rows = db.execute(
            select(SourceItem)
            .order_by(desc(SourceItem.created_at))
            .offset(offset)
            .limit(size)
        ).scalars().all()

        items = [
            FavoriteItem(
                id=row.id,
                platform_item_id=row.platform_item_id,
                url=row.url,
                title=row.title,
                author=row.author,
                duration_sec=row.duration_sec,
                fav_time=row.fav_time,
                ingest_status=row.ingest_status,
            )
            for row in rows
        ]
        return items, total


favorites_service = FavoritesService()
