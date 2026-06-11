"""
BLPAPI related endpoints
"""

import logging
import asyncio
from fastapi import (
    APIRouter, 
    Request, 
    HTTPException, 
    Query, 
    WebSocket, 
    WebSocketDisconnect,
)

from app.services.blpapi_relay.bql_via_excel import excel_bql

logger = logging.getLogger(__name__)


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

    
@router.get("/refdata")
async def get_refdata(
    request: Request,
    tickers: list[str] = Query(["AAPL US Equity"]), 
    fields: list[str] = Query(["PX_LAST"]),
):
    refdata_handler = request.app.state.refdata_handler
    try:
        data = await refdata_handler.get_refdata(tickers, fields)
        return {"status": "success", "data": data}
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Timeout querying Bloomberg API")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@router.websocket("/mktdata")
async def mktdata(
    request: Request,
    websocket: WebSocket,
    tickers: list[str] = Query(["IBM US Equity"]),
    fields: list[str] = Query(["LAST_PRICE"]),
    # Pass below control first, for most usecases we don't need this and it's more complex to manage
    # options: str | None =  Query(None, description="Examples: interval=1, interval=0.5&delayed"),
):
    await websocket.accept()
    logger.info(f"New WebSocket established for {tickers} with fields: {fields}")

    # Bind running asyncio loop to subscription_handler
    mktdata_handler = request.app.state.mktdata_handler
    mktdata_handler.loop = asyncio.get_running_loop()
    await mktdata_handler.connect(websocket, tickers, fields)

    try:
        while True:
            await websocket.receive_text() 
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected")
    finally:
        await mktdata_handler.disconnect(websocket, tickers)


@router.get("/bql")
async def bql(
    query: str,
    excel_relay: bool = True,
):
    logger.debug(f"BQL Query received: {query}")
    
    if not excel_relay:
        raise HTTPException(status_code=400, detail="Direct BQL API is disabled.")
    
    try:
        data = await excel_bql(query)
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Excel Relay internal error: {str(e)}")
    

@router.get("/xbbg")
async def test():

    ...