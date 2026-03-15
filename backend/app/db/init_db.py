from __future__ import annotations

"""数据库初始化与存储重建工具。"""

import shutil
from pathlib import Path

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.models import entities  # noqa: F401

settings = get_settings()


def init_db() -> None:
    """
    功能：执行 init_db 的核心业务逻辑。
    参数：
    - 无。
    返回值：
    - None：函数处理结果。
    """
    Base.metadata.create_all(bind=engine)


def rebuild_storage() -> None:
    """
    功能：执行 rebuild_storage 的核心业务逻辑。
    参数：
    - 无。
    返回值：
    - None：函数处理结果。
    """
    engine.dispose()
    db_url = settings.database_url
    if db_url.startswith("sqlite:///"):
        db_path = db_url.removeprefix("sqlite:///")
        path = Path(db_path)
        if not path.is_absolute():
            path = (Path(__file__).resolve().parents[2] / path).resolve()
        if path.exists():
            path.unlink()
    else:
        Base.metadata.drop_all(bind=engine)

    chroma_path = Path(settings.chroma_persist_directory)
    if chroma_path.exists():
        shutil.rmtree(chroma_path, ignore_errors=True)
    chroma_path.mkdir(parents=True, exist_ok=True)

    # Cleanup legacy accidental path (backend/backend/storage) from old relative DB URL.
    legacy_storage = Path(__file__).resolve().parents[2] / "backend" / "storage"
    if legacy_storage.exists():
        shutil.rmtree(legacy_storage, ignore_errors=True)

    Base.metadata.create_all(bind=engine)
