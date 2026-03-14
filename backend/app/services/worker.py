from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.services.ingest_service import ingest_service

logger = logging.getLogger(__name__)
settings = get_settings()


class IngestWorkerManager:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[int] = asyncio.Queue()
        self.tasks: list[asyncio.Task[None]] = []
        self.running = False

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        for idx in range(settings.ingest_worker_concurrency):
            task = asyncio.create_task(self._worker_loop(idx + 1))
            self.tasks.append(task)
        logger.info("Ingest worker started with concurrency=%s", settings.ingest_worker_concurrency)

    async def stop(self) -> None:
        self.running = False
        for task in self.tasks:
            task.cancel()
        self.tasks.clear()

    async def enqueue(self, job_id: int) -> None:
        await self.queue.put(job_id)

    async def _worker_loop(self, worker_idx: int) -> None:
        while self.running:
            job_id = await self.queue.get()
            try:
                logger.info("Worker-%s processing job %s", worker_idx, job_id)
                status = await asyncio.to_thread(ingest_service.process_job, job_id)
                if status == "pending":
                    await asyncio.sleep(1)
                    await self.queue.put(job_id)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("Worker-%s crashed while processing job %s", worker_idx, job_id)
            finally:
                self.queue.task_done()


worker_manager = IngestWorkerManager()
