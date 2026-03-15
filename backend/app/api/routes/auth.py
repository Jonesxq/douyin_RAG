from __future__ import annotations

"""登录相关接口：启动扫码登录、查询登录状态。"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import UserSession
from app.schemas import LoginStartResponse, LoginStatusResponse
from app.services.douyin_collector import collector

router = APIRouter()


@router.post("/login/start", response_model=LoginStartResponse)
async def start_login() -> LoginStartResponse:
    """
    功能：执行 start_login 的核心业务逻辑。
    参数：
    - 无。
    返回值：
    - LoginStartResponse：函数处理结果。
    """
    started, message = collector.start_login()
    return LoginStartResponse(started=started, message=message)


@router.get("/login/status", response_model=LoginStatusResponse)
async def login_status(db: Session = Depends(get_db)) -> LoginStatusResponse:
    """
    功能：执行 login_status 的核心业务逻辑。
    参数：
    - db：输入参数。
    返回值：
    - LoginStatusResponse：函数处理结果。
    """
    session = db.execute(select(UserSession).where(UserSession.session_id == "local")).scalar_one_or_none()
    if session is None:
        session = UserSession(session_id="local")
        db.add(session)

    session.is_logged_in = collector.status == "logged_in"
    session.message = collector.message
    db.commit()

    return LoginStatusResponse(status=collector.status, message=collector.message)
