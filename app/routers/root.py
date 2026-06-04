from fastapi import APIRouter, Response, status


router = APIRouter(
    prefix="",
    tags=["Root"],
)


@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=status.HTTP_204_NO_CONTENT)