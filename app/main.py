import uvicorn
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .config import settings
from .routers import (
    root,
    status,
    hkex,
    blp,
    sfc,
)

from .readiness import Readiness
from .services.blpapi_relay.session_manager import SessionManager
from .services.blpapi_relay.modules.refdata_handler import RefDataHandler
from .services.blpapi_relay.modules.status_monitor import StatusMonitor
from .services.blpapi_relay.modules.mktdata_handler import MktDataHandler


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # == Start up ==
    sm = SessionManager()

    refdata_handler = RefDataHandler()
    sm.register_module(refdata_handler)

    readiness = Readiness()
    status_monitor = StatusMonitor(readiness)
    sm.register_module(status_monitor)

    mktdata_handler = MktDataHandler()
    sm.register_module(mktdata_handler)


    # -- Binding --
    app.state.readiness = readiness
    app.state.blp_session_manager = sm
    app.state.refdata_handler = refdata_handler
    app.state.mktdata_handler = mktdata_handler

    # -- Create a blpapi session and send an async start request --
    while True:
        if sm.start_async():
            break


    yield


    # == Shut down ==
    logger.info("Shutting down the application...")
    sm.stop()


# Initialize with lifespan and configuration
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
)


# Include API routers
app.include_router(root.router)
app.include_router(status.router)
app.include_router(hkex.router)
app.include_router(blp.router)
app.include_router(sfc.router)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT)