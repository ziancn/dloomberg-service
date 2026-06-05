from fastapi import APIRouter, Request


router = APIRouter(
    prefix="/status",
    tags=["Status"]
)


@router.get("")
def get_status(request: Request):
    return {
        "status": "ok",
        "blpapi": request.app.state.readiness.blpapi
    }