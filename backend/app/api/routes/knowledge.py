from __future__ import annotations

"""知识库同步任务接口（创建任务、查询进度、统计）。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import KnowledgeStatsResponse, KnowledgeSyncRequest, KnowledgeSyncResponse, SyncTaskDTO
from app.services.knowledge_service import knowledge_service
from app.services.worker import worker_manager

router = APIRouter()


@router.post("/sync", response_model=KnowledgeSyncResponse)
async def create_sync_tasks(
    payload: KnowledgeSyncRequest,
    db: Session = Depends(get_db),
) -> KnowledgeSyncResponse:
    """
    功能：创建 create_sync_tasks 对应的资源或记录。
    参数：
    - payload：输入参数。
    - db：输入参数。
    返回值：
    - KnowledgeSyncResponse：函数处理结果。
    """
    tasks = knowledge_service.create_sync_tasks(db, payload.collection_ids)
    if not tasks:
        raise HTTPException(status_code=400, detail="No valid collections found")

    for task in tasks:
        await worker_manager.enqueue(task.id)

    return KnowledgeSyncResponse(tasks=[knowledge_service.to_dto(task) for task in tasks])


@router.get("/sync/{task_id}", response_model=SyncTaskDTO)
def get_sync_task(task_id: int, db: Session = Depends(get_db)) -> SyncTaskDTO:
    """
    功能：获取 get_sync_task 对应的数据或对象。
    参数：
    - task_id：输入参数。
    - db：输入参数。
    返回值：
    - SyncTaskDTO：函数处理结果。
    """
    task = knowledge_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return knowledge_service.to_dto(task)


@router.get("/stats", response_model=KnowledgeStatsResponse)
def get_stats(db: Session = Depends(get_db)) -> KnowledgeStatsResponse:
    """
    功能：获取 get_stats 对应的数据或对象。
    参数：
    - db：输入参数。
    返回值：
    - KnowledgeStatsResponse：函数处理结果。
    """
    return KnowledgeStatsResponse(**knowledge_service.stats(db))
