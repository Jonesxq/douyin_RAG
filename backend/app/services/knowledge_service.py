from __future__ import annotations

"""知识入库任务服务：下载音频、转写、切块、向量化、写入状态。"""

import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import FavoriteCollection, FavoriteVideo, SyncTask, VideoCache
from app.schemas import SyncTaskDTO
from app.services.asr_service import transcribe_audio
from app.services.chroma_service import get_chroma_service
from app.services.favorites_service import favorites_service
from app.services.llm_service import QwenClient
from app.services.media_service import download_audio
from app.services.text_processing import build_chunks

logger = logging.getLogger(__name__)
settings = get_settings()


class KnowledgeService:
    def create_sync_tasks(self, db: Session, collection_ids: list[str]) -> list[SyncTask]:
        """
        功能：创建 KnowledgeService.create_sync_tasks 对应的资源或记录。
        参数：
        - db：输入参数。
        - collection_ids：输入参数。
        返回值：
        - list[SyncTask]：函数处理结果。
        """
        collections = favorites_service.resolve_collection_ids(db, collection_ids)
        if not collections:
            return []

        jobs: list[SyncTask] = []
        for collection in collections:
            active = db.execute(
                select(SyncTask).where(
                    SyncTask.task_type == "knowledge_sync",
                    SyncTask.collection_id == collection.id,
                    SyncTask.status.in_(["pending", "running"]),
                )
            ).scalar_one_or_none()
            if active is not None:
                jobs.append(active)
                continue

            job = SyncTask(
                task_type="knowledge_sync",
                collection_id=collection.id,
                collection_platform_id=collection.platform_collection_id,
                status="pending",
                step="queued",
                progress_total=0,
                progress_done=0,
            )
            db.add(job)
            jobs.append(job)

        db.commit()
        for job in jobs:
            db.refresh(job)
        return jobs

    def get_task(self, db: Session, task_id: int) -> SyncTask | None:
        """
        功能：获取 KnowledgeService.get_task 对应的数据或对象。
        参数：
        - db：输入参数。
        - task_id：输入参数。
        返回值：
        - SyncTask | None：函数处理结果。
        """
        return db.get(SyncTask, task_id)

    def to_dto(self, task: SyncTask) -> SyncTaskDTO:
        """
        功能：执行 KnowledgeService.to_dto 的核心业务逻辑。
        参数：
        - task：输入参数。
        返回值：
        - SyncTaskDTO：函数处理结果。
        """
        return SyncTaskDTO(
            id=task.id,
            task_type=task.task_type,
            collection_id=task.collection_platform_id,
            status=task.status,
            step=task.step,
            progress_total=task.progress_total,
            progress_done=task.progress_done,
            message=task.message,
            error_msg=task.error_msg,
            retry_count=task.retry_count,
            created_at=task.created_at,
            started_at=task.started_at,
            finished_at=task.finished_at,
        )

    def process_task(self, task_id: int) -> str:
        """
        功能：执行 KnowledgeService.process_task 的核心业务逻辑。
        参数：
        - task_id：输入参数。
        返回值：
        - str：函数处理结果。
        """
        db = SessionLocal()
        try:
            task = db.get(SyncTask, task_id)
            if task is None:
                return "missing"

            if task.collection_id is None:
                task.status = "failed"
                task.step = "missing_collection"
                task.error_msg = "Collection not found"
                task.finished_at = datetime.utcnow()
                db.commit()
                return task.status

            collection = db.get(FavoriteCollection, task.collection_id)
            if collection is None:
                task.status = "failed"
                task.step = "missing_collection"
                task.error_msg = "Collection not found"
                task.finished_at = datetime.utcnow()
                db.commit()
                return task.status

            task.status = "running"
            task.step = "loading"
            task.message = ""
            task.error_msg = ""
            task.started_at = datetime.utcnow()

            videos = db.execute(
                select(FavoriteVideo)
                .where(
                    FavoriteVideo.collection_id == collection.id,
                    FavoriteVideo.is_active.is_(True),
                )
                .order_by(FavoriteVideo.updated_at.desc())
            ).scalars().all()

            by_item_id: dict[str, FavoriteVideo] = {}
            for row in videos:
                by_item_id.setdefault(row.platform_item_id, row)

            platform_ids = list(by_item_id.keys())
            task.progress_total = len(platform_ids)
            task.progress_done = 0
            db.commit()

            # 每个任务复用同一批服务实例，减少重复初始化开销
            qwen = QwenClient()
            chroma = get_chroma_service()

            ok_count = 0
            failed_count = 0
            failures: list[str] = []

            for idx, platform_item_id in enumerate(platform_ids, start=1):
                task.step = "processing"
                task.progress_done = idx - 1
                db.commit()

                source = by_item_id[platform_item_id]
                cache = db.execute(
                    select(VideoCache).where(VideoCache.platform_item_id == platform_item_id)
                ).scalar_one_or_none()
                if cache is None:
                    cache = VideoCache(
                        platform_item_id=platform_item_id,
                        url=source.url,
                        title=source.title,
                        author=source.author,
                        duration_sec=source.duration_sec,
                        status="pending",
                    )
                    db.add(cache)
                    db.flush()

                audio_path: Path | None = None
                try:
                    cache.status = "processing"
                    cache.error_msg = ""
                    db.commit()

                    audio_path = download_audio(source.url, platform_item_id)
                    raw_segments, language = transcribe_audio(audio_path)
                    chunk_results = build_chunks(raw_segments)
                    if not chunk_results:
                        raise RuntimeError("No chunks generated from transcript")

                    chunk_texts = [chunk.text for chunk in chunk_results]
                    embeddings = qwen.embed_texts(chunk_texts)

                    collection_ids = db.execute(
                        select(FavoriteCollection.platform_collection_id)
                        .join(FavoriteVideo, FavoriteVideo.collection_id == FavoriteCollection.id)
                        .where(
                            FavoriteVideo.platform_item_id == platform_item_id,
                            FavoriteVideo.is_active.is_(True),
                        )
                    ).all()
                    collection_id_values = [row[0] for row in collection_ids]

                    # 先删后写，保证同一视频的向量是最新版本
                    chroma.delete_videos([platform_item_id])
                    chunk_ids = chroma.upsert_video_chunks(
                        platform_item_id=platform_item_id,
                        title=source.title,
                        collection_ids=collection_id_values,
                        chunks=chunk_texts,
                        embeddings=embeddings,
                        lang=language,
                        source="asr_local",
                    )

                    cache.transcript_text = "\n".join(seg.text for seg in raw_segments)
                    cache.transcript_lang = language
                    cache.chunk_count = len(chunk_results)
                    # 保留 chunk 元数据，后续可用于定位与调试
                    cache.chunk_payload = [
                        {
                            "chunk_id": chunk_ids[i],
                            "text": chunk_results[i].text,
                            "token_count": chunk_results[i].token_count,
                            "start_ms": chunk_results[i].start_ms,
                            "end_ms": chunk_results[i].end_ms,
                            "lang": chunk_results[i].lang,
                        }
                        for i in range(len(chunk_results))
                    ]
                    cache.content_source = "asr_local"
                    cache.status = "success"
                    cache.error_msg = ""
                    cache.processed_at = datetime.utcnow()
                    cache.retry_count = 0

                    ok_count += 1
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Knowledge task %s failed for video %s", task_id, platform_item_id)
                    cache.status = "failed"
                    cache.error_msg = str(exc)[:4000]
                    cache.retry_count += 1
                    failures.append(f"{platform_item_id}: {exc}")
                    failed_count += 1
                finally:
                    if audio_path and audio_path.exists():
                        try:
                            audio_path.unlink(missing_ok=True)
                        except Exception:  # noqa: BLE001
                            pass
                    task.progress_done = idx
                    db.commit()

            task.finished_at = datetime.utcnow()
            task.step = "done"
            if failed_count == 0:
                task.status = "success"
                task.message = f"Processed {ok_count} videos"
                task.error_msg = ""
            else:
                task.status = "failed"
                task.message = f"Processed {ok_count}, failed {failed_count}"
                task.error_msg = "\n".join(failures[:20])[:4000]
            db.commit()
            return task.status

        except Exception as exc:  # noqa: BLE001
            logger.exception("Sync task %s crashed", task_id)
            db.rollback()

            task = db.get(SyncTask, task_id)
            if task is None:
                return "failed"

            task.error_msg = str(exc)[:4000]
            if task.retry_count < settings.task_retry_count:
                task.retry_count += 1
                task.status = "pending"
                task.step = "retry_scheduled"
            else:
                task.status = "failed"
                task.step = "failed"
                task.finished_at = datetime.utcnow()
            db.commit()
            return task.status
        finally:
            db.close()

    def stats(self, db: Session) -> dict:
        """
        功能：执行 KnowledgeService.stats 的核心业务逻辑。
        参数：
        - db：输入参数。
        返回值：
        - dict：函数处理结果。
        """
        total_collections = db.scalar(
            select(func.count())
            .select_from(FavoriteCollection)
            .where(and_(FavoriteCollection.platform == "douyin", FavoriteCollection.is_active.is_(True)))
        ) or 0
        total_videos = db.scalar(
            select(func.count(func.distinct(FavoriteVideo.platform_item_id))).where(FavoriteVideo.is_active.is_(True))
        ) or 0
        processed_videos = db.scalar(
            select(func.count()).select_from(VideoCache).where(VideoCache.status == "success")
        ) or 0
        total_chunks = db.scalar(select(func.sum(VideoCache.chunk_count)).where(VideoCache.status == "success")) or 0

        return {
            "total_collections": int(total_collections),
            "total_videos": int(total_videos),
            "processed_videos": int(processed_videos),
            "total_chunks": int(total_chunks),
        }


knowledge_service = KnowledgeService()
