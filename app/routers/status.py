from fastapi import APIRouter


router = APIRouter(
    prefix="/status",
    tags=["Status"]
)


@router.get("/")
def get_status():
    return {"status": "ok"}


@router.get("/bloomberg")
def get_bloomberg_status():
    return {"status": "ok"}