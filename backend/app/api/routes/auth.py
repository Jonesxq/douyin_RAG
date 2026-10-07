from __future__ import annotations

"""登录相关接口：启动扫码登录、查询登录状态。"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import UserSession
from app.schemas import LoginLogoutResponse, LoginStartResponse, LoginStatusResponse
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


@router.get("/login/qr")
async def login_qr() -> Response:
    """返回最新的抖音登录页截图；没有可用截图时返回 204。"""
    image = collector.get_login_qr_image()
    headers = {"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}
    if image is None:
        return Response(status_code=204, headers=headers)
    return Response(content=image, media_type="image/png", headers=headers)


@router.post("/login/logout", response_model=LoginLogoutResponse)
async def logout_login(db: Session = Depends(get_db)) -> LoginLogoutResponse:
    """
    功能：执行 logout_login 的核心业务逻辑。
    参数：
    - db：输入参数。
    返回值：
    - LoginLogoutResponse：函数处理结果。
    """
    success, message = collector.logout()

    session = db.execute(select(UserSession).where(UserSession.session_id == "local")).scalar_one_or_none()
    if session is None:
        session = UserSession(session_id="local")
        db.add(session)

    session.is_logged_in = False
    session.message = message
    db.commit()

    return LoginLogoutResponse(success=success, message=message)
