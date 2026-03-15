from __future__ import annotations

"""后台任务 worker 管理器：异步队列消费与失败重试。"""

import asyncio
import logging

from app.core.config import get_settings
from app.services.knowledge_service import knowledge_service

logger = logging.getLogger(__name__)
settings = get_settings()


class SyncWorkerManager:
    def __init__(self) -> None:
        # 任务队列里存放 sync_task_id
        """
        功能：初始化 SyncWorkerManager 的实例状态。
        参数：
        - 无。
        返回值：
        - None：构造函数不返回业务值。
        """
        self.queue: asyncio.Queue[int] = asyncio.Queue()
        self.tasks: list[asyncio.Task[None]] = []
        self.running = False

    async def start(self) -> None:
        """
        功能：执行 SyncWorkerManager.start 的核心业务逻辑。
        参数：
        - 无。
        返回值：
        - None：函数处理结果。
        """
        if self.running:
            return
        self.running = True
        for idx in range(settings.task_worker_concurrency):
            task = asyncio.create_task(self._worker_loop(idx + 1))
            self.tasks.append(task)
        logger.info("Sync worker started with concurrency=%s", settings.task_worker_concurrency)

    async def stop(self) -> None:
        """
        功能：执行 SyncWorkerManager.stop 的核心业务逻辑。
        参数：
        - 无。
        返回值：
        - None：函数处理结果。
        """
        self.running = False
        for task in self.tasks:
            task.cancel()
        self.tasks.clear()

    async def enqueue(self, task_id: int) -> None:
        """
        功能：执行 SyncWorkerManager.enqueue 的核心业务逻辑。
        参数：
        - task_id：输入参数。
        返回值：
        - None：函数处理结果。
        """
        await self.queue.put(task_id)

    async def _worker_loop(self, worker_idx: int) -> None:
        """
        功能：执行 SyncWorkerManager._worker_loop 的内部处理逻辑。
        参数：
        - worker_idx：输入参数。
        返回值：
        - None：函数处理结果。
        """
        while self.running:
            task_id = await self.queue.get()
            try:
                logger.info("Worker-%s processing sync task %s", worker_idx, task_id)
                # 任务处理是 CPU/IO 混合逻辑，放到线程池避免阻塞事件循环
                status = await asyncio.to_thread(knowledge_service.process_task, task_id)
                if status == "pending":
                    await asyncio.sleep(1)
                    await self.queue.put(task_id)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("Worker-%s crashed while processing task %s", worker_idx, task_id)
            finally:
                self.queue.task_done()


worker_manager = SyncWorkerManager()
