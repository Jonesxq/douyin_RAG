from __future__ import annotations

from fastapi import APIRouter

from app.schemas import LoginStartResponse, LoginStatusResponse
from app.services.douyin_collector import collector

router = APIRouter()


@router.post("/login/start", response_model=LoginStartResponse)
async def start_login() -> LoginStartResponse:
    started, message = collector.start_login()
    return LoginStartResponse(started=started, message=message)


@router.get("/login/status", response_model=LoginStatusResponse)
async def login_status() -> LoginStatusResponse:
    return LoginStatusResponse(status=collector.status, message=collector.message)
