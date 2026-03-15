from __future__ import annotations

"""FastAPI 应用入口。负责初始化数据库、自检、路由和后台 worker。"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.startup_checks import run_startup_checks
from app.db.init_db import init_db
from app.services.worker import worker_manager

settings = get_settings()

configure_logging()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    # 启动时初始化数据库表结构
    """
    功能：执行 on_startup 的核心业务逻辑。
    参数：
    - 无。
    返回值：
    - None：函数处理结果。
    """
    init_db()
    # 启动时做依赖与运行环境检查
    run_startup_checks()
    # 启动后台同步任务 worker
    await worker_manager.start()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    # 优雅停止 worker，避免任务中断悬挂
    """
    功能：执行 on_shutdown 的核心业务逻辑。
    参数：
    - 无。
    返回值：
    - None：函数处理结果。
    """
    await worker_manager.stop()


@app.get("/health")
def health() -> dict[str, str]:
    """
    功能：执行 health 的核心业务逻辑。
    参数：
    - 无。
    返回值：
    - dict[str, str]：函数处理结果。
    """
    return {"status": "ok"}


app.include_router(api_router, prefix=settings.api_prefix)
