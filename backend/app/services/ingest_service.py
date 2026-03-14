from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import Chunk, IngestJob, MediaAsset, SourceItem, TranscriptSegment
from app.schemas import IngestJobDTO
from app.services.asr_service import transcribe_audio
from app.services.llm_service import QwenClient
from app.services.media_service import download_video, extract_audio, sha256_file
from app.services.chroma_service import get_chroma_service
from app.services.text_processing import build_chunks

logger = logging.getLogger(__name__)
settings = get_settings()


class IngestService:
    def create_jobs(self, db: Session, item_ids: list[int]) -> list[IngestJob]:
        if not item_ids:
            return []

        rows = db.execute(select(SourceItem).where(SourceItem.id.in_(item_ids))).scalars().all()
        if not rows:
            return []

        jobs: list[IngestJob] = []
        for source in rows:
            source.ingest_status = "queued"
            job = IngestJob(source_item_id=source.id, status="pending", step="queued")
            db.add(job)
            jobs.append(job)

        db.commit()
        for job in jobs:
            db.refresh(job)
        return jobs

    def get_job(self, db: Session, job_id: int) -> IngestJob | None:
        return db.get(IngestJob, job_id)

    def to_dto(self, job: IngestJob) -> IngestJobDTO:
        return IngestJobDTO(
            id=job.id,
            source_item_id=job.source_item_id,
            status=job.status,
            step=job.step,
            error_msg=job.error_msg,
            retry_count=job.retry_count,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )

    def process_job(self, job_id: int) -> str:
        db = SessionLocal()
        try:
            job = db.get(IngestJob, job_id)
            if not job:
                return "missing"

            source = db.get(SourceItem, job.source_item_id)
            if not source:
                job.status = "failed"
                job.step = "missing_source"
                job.error_msg = "Source item not found"
                job.finished_at = datetime.utcnow()
                db.commit()
                return job.status

            job.status = "running"
            job.step = "downloading"
            job.error_msg = ""
            job.started_at = datetime.utcnow()
            source.ingest_status = "processing"
            db.commit()

            video_path = download_video(source.url, source.platform_item_id)
            audio_path = extract_audio(video_path, source.platform_item_id)

            db.execute(delete(MediaAsset).where(MediaAsset.source_item_id == source.id))
            db.add(
                MediaAsset(
                    source_item_id=source.id,
                    video_path=str(video_path),
                    audio_path=str(audio_path),
                    video_sha256=sha256_file(video_path),
                    audio_sha256=sha256_file(audio_path),
                    download_status="success",
                )
            )
            db.commit()

            job.step = "transcribing"
            db.commit()

            raw_segments, language = transcribe_audio(audio_path)

            db.execute(delete(TranscriptSegment).where(TranscriptSegment.source_item_id == source.id))
            db.commit()

            for idx, seg in enumerate(raw_segments):
                db.add(
                    TranscriptSegment(
                        source_item_id=source.id,
                        seg_index=idx,
                        start_ms=seg.start_ms,
                        end_ms=seg.end_ms,
                        text_raw=seg.text,
                        lang=seg.lang,
                        asr_model=settings.asr_model_size,
                        confidence=None,
                    )
                )
            db.commit()

            job.step = "chunking"
            db.commit()

            chunk_results = build_chunks(raw_segments)
            if not chunk_results:
                raise RuntimeError("No chunks generated from transcript")

            db.execute(delete(Chunk).where(Chunk.source_item_id == source.id))
            db.commit()

            chunk_rows: list[Chunk] = []
            for idx, chunk in enumerate(chunk_results):
                row = Chunk(
                    source_item_id=source.id,
                    chunk_index=idx,
                    text_clean=chunk.text,
                    token_count=chunk.token_count,
                    lang=chunk.lang or language,
                    start_ms=chunk.start_ms,
                    end_ms=chunk.end_ms,
                    fts_text=chunk.text,
                )
                db.add(row)
                chunk_rows.append(row)

            db.flush()

            job.step = "embedding"
            db.commit()

            qwen = QwenClient()
            texts = [row.text_clean for row in chunk_rows]
            embeddings = qwen.embed_texts(texts)

            chroma = get_chroma_service()
            chroma.delete_by_source_item(source.id)
            chroma.upsert_vectors(
                chunk_ids=[row.id for row in chunk_rows],
                source_item_ids=[source.id for _ in chunk_rows],
                langs=[row.lang for row in chunk_rows],
                embeddings=embeddings,
            )

            source.ingest_status = "success"
            job.status = "success"
            job.step = "done"
            job.finished_at = datetime.utcnow()
            db.commit()
            return job.status

        except Exception as exc:  # noqa: BLE001
            logger.exception("Job %s failed", job_id)
            db.rollback()

            job = db.get(IngestJob, job_id)
            source = db.get(SourceItem, job.source_item_id) if job else None

            if job:
                job.error_msg = str(exc)[:4000]
                if job.retry_count < settings.ingest_retry_count:
                    job.retry_count += 1
                    job.status = "pending"
                    job.step = "retry_scheduled"
                else:
                    job.status = "failed"
                    job.step = "failed"
                    job.finished_at = datetime.utcnow()

            if source:
                source.ingest_status = "failed" if job and job.status == "failed" else source.ingest_status

            db.commit()
            return job.status if job else "failed"
        finally:
            db.close()


ingest_service = IngestService()
