from fastapi import APIRouter, Response, status
from app.services.left import analyze_leveraged_etf


router = APIRouter(
    prefix="",
    tags=["Root"],
)


@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/letf")
def letf_analysis(
    letf_ticker: str = "7709.HK",
    underlying_ticker: str = "000660.KS",
    leverage: float = 2.0,
    start_date: str | None = None,
    end_date: str | None = None,
    ref_currency: str = "HKD",
):
    result = analyze_leveraged_etf(
        letf_ticker, underlying_ticker, leverage,
        start_date, end_date, ref_currency,
    )
    return result