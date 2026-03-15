from __future__ import annotations

"""数据库引擎与会话工厂。"""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine_kwargs: dict = {
    "future": True,
    "pool_pre_ping": True,
}

if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, **engine_kwargs)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Session:
    """
    功能：获取 get_db 对应的数据或对象。
    参数：
    - 无。
    返回值：
    - Session：函数处理结果。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
