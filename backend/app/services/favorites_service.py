from __future__ import annotations

"""收藏夹同步服务：把采集快照与本地库做差异对齐。"""

from collections import OrderedDict

from sqlalchemy import and_, delete, desc, func, select
from sqlalchemy.orm import Session

from app.models import FavoriteCollection, FavoriteVideo, VideoCache
from app.schemas import FavoriteCollectionDTO, FavoriteVideoDTO
from app.services.chroma_service import get_chroma_service
from app.services.douyin_collector import FavoriteScrapeSnapshot, collector

ALL_COLLECTION_ID = "all"
ALL_COLLECTION_TITLE = "全部收藏"


class FavoritesService:
    async def sync_from_douyin(self, db: Session) -> dict:
        # 从抖音侧拉取最新收藏夹快照
        """
        功能：执行 FavoritesService.sync_from_douyin 的同步逻辑。
        参数：
        - db：输入参数。
        返回值：
        - dict：函数处理结果。
        """
        snapshot = await collector.fetch_snapshot(max_collections=100, max_items_per_collection=500)

        collections_by_platform = self._sync_collections(db, snapshot)
        added, removed = self._sync_videos_and_cache(db, snapshot, collections_by_platform)
        db.commit()

        total_collections = db.scalar(
            select(func.count())
            .select_from(FavoriteCollection)
            .where(FavoriteCollection.platform == "douyin", FavoriteCollection.is_active.is_(True))
        ) or 0
        total_videos = db.scalar(
            select(func.count(func.distinct(FavoriteVideo.platform_item_id)))
            .select_from(FavoriteVideo)
            .where(FavoriteVideo.is_active.is_(True))
        ) or 0

        return {
            "collections_total": int(total_collections),
            "videos_total": int(total_videos),
            "added_videos": added,
            "removed_videos": removed,
        }

    def _sync_collections(
        self,
        db: Session,
        snapshot: FavoriteScrapeSnapshot,
    ) -> dict[str, FavoriteCollection]:
        """
        功能：执行 FavoritesService._sync_collections 的同步逻辑。
        参数：
        - db：输入参数。
        - snapshot：输入参数。
        返回值：
        - dict[str, FavoriteCollection]：函数处理结果。
        """
        existing = db.execute(
            select(FavoriteCollection).where(FavoriteCollection.platform == "douyin")
        ).scalars().all()
        existing_map = {row.platform_collection_id: row for row in existing}

        seen: set[str] = set()
        for col in snapshot.collections:
            seen.add(col.platform_collection_id)
            row = existing_map.get(col.platform_collection_id)
            if row is None:
                row = FavoriteCollection(
                    platform="douyin",
                    platform_collection_id=col.platform_collection_id,
                    title=col.title,
                    item_count=col.item_count,
                    cover_url=col.cover_url,
                    is_active=True,
                )
                db.add(row)
                existing_map[col.platform_collection_id] = row
            else:
                row.title = col.title
                row.item_count = col.item_count
                row.cover_url = col.cover_url
                row.is_active = True

        for row in existing:
            if row.platform_collection_id not in seen:
                row.is_active = False

        db.flush()
        return existing_map

    def _sync_videos_and_cache(
        self,
        db: Session,
        snapshot: FavoriteScrapeSnapshot,
        collections_by_platform: dict[str, FavoriteCollection],
    ) -> tuple[int, int]:
        # 目标关系：collection_id + platform_item_id
        """
        功能：执行 FavoritesService._sync_videos_and_cache 的同步逻辑。
        参数：
        - db：输入参数。
        - snapshot：输入参数。
        - collections_by_platform：输入参数。
        返回值：
        - tuple[int, int]：函数处理结果。
        """
        desired_pairs: dict[tuple[int, str], dict] = {}
        desired_video_payload: dict[str, dict] = {}

        for video in snapshot.videos:
            desired_video_payload[video.platform_item_id] = {
                "url": video.url,
                "title": video.title,
                "author": video.author,
                "duration_sec": video.duration_sec,
            }
            for collection_platform_id in video.collection_ids:
                collection = collections_by_platform.get(collection_platform_id)
                if collection is None:
                    continue
                desired_pairs[(collection.id, video.platform_item_id)] = {
                    "collection_id": collection.id,
                    "platform_item_id": video.platform_item_id,
                    "url": video.url,
                    "title": video.title,
                    "author": video.author,
                    "duration_sec": video.duration_sec,
                }

        active_collections = db.execute(
            select(FavoriteCollection.id).where(
                FavoriteCollection.platform == "douyin",
                FavoriteCollection.is_active.is_(True),
            )
        ).all()
        active_collection_ids = [row[0] for row in active_collections]

        existing_rows = []
        if active_collection_ids:
            existing_rows = db.execute(
                select(FavoriteVideo).where(FavoriteVideo.collection_id.in_(active_collection_ids))
            ).scalars().all()
        existing_map = {(row.collection_id, row.platform_item_id): row for row in existing_rows}
        existing_video_ids = {row.platform_item_id for row in existing_rows}
        desired_video_ids = set(desired_video_payload.keys())
        added_video_ids = desired_video_ids - existing_video_ids

        for key, payload in desired_pairs.items():
            row = existing_map.get(key)
            if row is None:
                db.add(
                    FavoriteVideo(
                        collection_id=payload["collection_id"],
                        platform_item_id=payload["platform_item_id"],
                        url=payload["url"],
                        title=payload["title"],
                        author=payload["author"],
                        duration_sec=payload["duration_sec"],
                        is_active=True,
                    )
                )
                continue
            row.url = payload["url"]
            row.title = payload["title"]
            row.author = payload["author"]
            row.duration_sec = payload["duration_sec"]
            row.is_active = True

        removed_ids: set[str] = set()
        for key, row in existing_map.items():
            if key in desired_pairs:
                continue
            removed_ids.add(row.platform_item_id)
            db.delete(row)

        cache_rows = db.execute(select(VideoCache)).scalars().all()
        cache_map = {row.platform_item_id: row for row in cache_rows}
        for platform_item_id, payload in desired_video_payload.items():
            cache = cache_map.get(platform_item_id)
            if cache is None:
                db.add(
                    VideoCache(
                        platform_item_id=platform_item_id,
                        url=payload["url"],
                        title=payload["title"],
                        author=payload["author"],
                        duration_sec=payload["duration_sec"],
                        status="pending",
                    )
                )
            else:
                cache.url = payload["url"]
                cache.title = payload["title"]
                cache.author = payload["author"]
                cache.duration_sec = payload["duration_sec"]

        db.flush()

        # 删除已不在任何收藏夹中的孤儿视频缓存与向量
        if removed_ids:
            still_used_ids = {
                row[0]
                for row in db.execute(
                    select(FavoriteVideo.platform_item_id).where(
                        FavoriteVideo.platform_item_id.in_(removed_ids)
                    )
                ).all()
            }
            orphan_ids = sorted(removed_ids - still_used_ids)
            if orphan_ids:
                db.execute(delete(VideoCache).where(VideoCache.platform_item_id.in_(orphan_ids)))
                chroma = get_chroma_service()
                chroma.delete_videos(orphan_ids)

        removed_video_ids = existing_video_ids - desired_video_ids
        return len(added_video_ids), len(removed_video_ids)

    def list_collections(self, db: Session) -> list[FavoriteCollectionDTO]:
        """
        功能：列出 FavoritesService.list_collections 对应的数据集合。
        参数：
        - db：输入参数。
        返回值：
        - list[FavoriteCollectionDTO]：函数处理结果。
        """
        total = db.scalar(
            select(func.count(func.distinct(FavoriteVideo.platform_item_id))).where(FavoriteVideo.is_active.is_(True))
        ) or 0

        rows = db.execute(
            select(FavoriteCollection)
            .where(
                FavoriteCollection.platform == "douyin",
                FavoriteCollection.is_active.is_(True),
            )
            .order_by(desc(FavoriteCollection.item_count), desc(FavoriteCollection.updated_at))
        ).scalars().all()

        result = [
            FavoriteCollectionDTO(
                id=0,
                collection_id=ALL_COLLECTION_ID,
                title=ALL_COLLECTION_TITLE,
                item_count=int(total),
                is_active=True,
            )
        ]
        for row in rows:
            result.append(
                FavoriteCollectionDTO(
                    id=row.id,
                    collection_id=row.platform_collection_id,
                    title=row.title,
                    item_count=row.item_count,
                    is_active=row.is_active,
                )
            )
        return result

    def list_collection_videos(
        self,
        db: Session,
        collection_id: str,
        page: int,
        size: int,
    ) -> tuple[list[FavoriteVideoDTO], int]:
        """
        功能：列出 FavoritesService.list_collection_videos 对应的数据集合。
        参数：
        - db：输入参数。
        - collection_id：输入参数。
        - page：输入参数。
        - size：输入参数。
        返回值：
        - tuple[list[FavoriteVideoDTO], int]：函数处理结果。
        """
        offset = (page - 1) * size

        if collection_id == ALL_COLLECTION_ID:
            rows = db.execute(
                select(FavoriteVideo, VideoCache.status)
                .join(VideoCache, VideoCache.platform_item_id == FavoriteVideo.platform_item_id, isouter=True)
                .where(FavoriteVideo.is_active.is_(True))
                .order_by(desc(FavoriteVideo.updated_at), desc(FavoriteVideo.id))
            ).all()

            dedup = OrderedDict()
            for row, status in rows:
                if row.platform_item_id in dedup:
                    continue
                dedup[row.platform_item_id] = (row, status or "pending")

            values = list(dedup.values())
            total = len(values)
            page_items = values[offset : offset + size]
            return [self._to_video_dto(row, status, ALL_COLLECTION_ID) for row, status in page_items], total

        collection = db.execute(
            select(FavoriteCollection).where(
                FavoriteCollection.platform == "douyin",
                FavoriteCollection.platform_collection_id == collection_id,
                FavoriteCollection.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if collection is None:
            return [], 0

        total = db.scalar(
            select(func.count())
            .select_from(FavoriteVideo)
            .where(
                FavoriteVideo.collection_id == collection.id,
                FavoriteVideo.is_active.is_(True),
            )
        ) or 0

        rows = db.execute(
            select(FavoriteVideo, VideoCache.status)
            .join(VideoCache, VideoCache.platform_item_id == FavoriteVideo.platform_item_id, isouter=True)
            .where(
                FavoriteVideo.collection_id == collection.id,
                FavoriteVideo.is_active.is_(True),
            )
            .order_by(desc(FavoriteVideo.updated_at), desc(FavoriteVideo.id))
            .offset(offset)
            .limit(size)
        ).all()

        return [self._to_video_dto(row, status or "pending", collection_id) for row, status in rows], int(total)

    def resolve_collection_ids(self, db: Session, collection_ids: list[str]) -> list[FavoriteCollection]:
        """
        功能：执行 FavoritesService.resolve_collection_ids 的核心业务逻辑。
        参数：
        - db：输入参数。
        - collection_ids：输入参数。
        返回值：
        - list[FavoriteCollection]：函数处理结果。
        """
        normalized = [item for item in collection_ids if item and item != ALL_COLLECTION_ID]
        if not normalized:
            return db.execute(
                select(FavoriteCollection).where(
                    FavoriteCollection.platform == "douyin",
                    FavoriteCollection.is_active.is_(True),
                )
            ).scalars().all()

        return db.execute(
            select(FavoriteCollection).where(
                FavoriteCollection.platform == "douyin",
                FavoriteCollection.is_active.is_(True),
                FavoriteCollection.platform_collection_id.in_(normalized),
            )
        ).scalars().all()

    def list_platform_item_ids_by_collection(self, db: Session, collection_id: str) -> list[str]:
        """
        功能：列出 FavoritesService.list_platform_item_ids_by_collection 对应的数据集合。
        参数：
        - db：输入参数。
        - collection_id：输入参数。
        返回值：
        - list[str]：函数处理结果。
        """
        if collection_id == ALL_COLLECTION_ID:
            rows = db.execute(
                select(FavoriteVideo.platform_item_id)
                .where(FavoriteVideo.is_active.is_(True))
                .group_by(FavoriteVideo.platform_item_id)
            ).all()
            return [row[0] for row in rows]

        collection = db.execute(
            select(FavoriteCollection).where(
                FavoriteCollection.platform == "douyin",
                FavoriteCollection.platform_collection_id == collection_id,
                FavoriteCollection.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if collection is None:
            return []

        rows = db.execute(
            select(FavoriteVideo.platform_item_id)
            .where(
                FavoriteVideo.collection_id == collection.id,
                FavoriteVideo.is_active.is_(True),
            )
            .group_by(FavoriteVideo.platform_item_id)
        ).all()
        return [row[0] for row in rows]

    @staticmethod
    def _to_video_dto(row: FavoriteVideo, status: str, collection_id: str) -> FavoriteVideoDTO:
        """
        功能：执行 FavoritesService._to_video_dto 的内部处理逻辑。
        参数：
        - row：输入参数。
        - status：输入参数。
        - collection_id：输入参数。
        返回值：
        - FavoriteVideoDTO：函数处理结果。
        """
        return FavoriteVideoDTO(
            id=row.id,
            collection_id=collection_id,
            platform_item_id=row.platform_item_id,
            url=row.url,
            title=row.title,
            author=row.author,
            duration_sec=row.duration_sec,
            status=status,
        )


favorites_service = FavoritesService()
