from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import CreateIngestJobsRequest, CreateIngestJobsResponse, IngestJobDTO
from app.services.ingest_service import ingest_service
from app.services.worker import worker_manager

router = APIRouter()


@router.post("/jobs", response_model=CreateIngestJobsResponse)
async def create_jobs(
    payload: CreateIngestJobsRequest,
    db: Session = Depends(get_db),
) -> CreateIngestJobsResponse:
    jobs = ingest_service.create_jobs(db, payload.item_ids)
    if not jobs:
        raise HTTPException(status_code=400, detail="No valid source items found")

    for job in jobs:
        await worker_manager.enqueue(job.id)

    return CreateIngestJobsResponse(jobs=[ingest_service.to_dto(job) for job in jobs])


@router.get("/jobs/{job_id}", response_model=IngestJobDTO)
def get_job(job_id: int, db: Session = Depends(get_db)) -> IngestJobDTO:
    job = ingest_service.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return ingest_service.to_dto(job)
