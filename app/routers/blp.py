"""
BLPAPI related endpoints
"""

from fastapi import APIRouter, Request


router = APIRouter(
    prefix="/blp",
    tags=["BLP"],
)


@router.get("/start")
async def start_blpapi_session(request: Request):
    sm = request.app.state.blp_session_manager
    return sm.start()


@router.get("/start-async")
async def start_blpapi_session(request: Request):
    sm = request.app.state.blp_session_manager
    return sm.start_async()