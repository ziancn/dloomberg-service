"""
SFC (Hong Kong Securities and Futures Commission) related endpoints
"""

import logging

from fastapi import APIRouter, Query
from app.services.sfc import search_licensee

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/sfc",
    tags=["SFC"],
)


@router.get("/search")
def search_sfc_licensee(
    keyword: str = Query(..., description="Search keyword (name or ceref)"),
    licstatus: str = Query("active", description="License status: 'active' or 'all'"),
    searchby: str = Query("individual", description="Search by: 'individual', 'corporation', or 'ceref'"),
):
    logger.info(f"SFC search: keyword={keyword}, licstatus={licstatus}, searchby={searchby}")
    return search_licensee(
        keyword=keyword,
        licstatus=licstatus,
        searchby=searchby,
    )