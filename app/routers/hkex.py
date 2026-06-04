"""
HKEX related endpoints
"""

from fastapi import APIRouter

from app.services.hkss import get_hkss_data


router = APIRouter(
    prefix="/hkex",
    tags=["HKEX"],
)


@router.get("/short-sell-turnover")
async def get_short_sell_turnover():
    data = await get_hkss_data()
    return {"data": data}