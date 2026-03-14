from __future__ import annotations

from app.db.base import Base
from app.db.session import engine
from app.models import entities  # noqa: F401


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
