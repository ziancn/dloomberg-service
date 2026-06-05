import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .config import settings
from .routers import (
    root,
    status,
    hkex,
    blp,
)

from .readiness import Readiness
from .services.blpapi_relay.session_manager import SessionManager
from .services.blpapi_relay.modules.refdata_handler import RefDataHandler
from .services.blpapi_relay.modules.status_monitor import StatusMonitor



@asynccontextmanager
async def lifespan(app: FastAPI):
    # == Start up ==
    sm = SessionManager()

    refdata_handler = RefDataHandler()
    sm.register_module(refdata_handler)

    readiness = Readiness()
    status_monitor = StatusMonitor(readiness)
    sm.register_module(status_monitor)


    # -- --
    app.state.readiness = readiness
    app.state.blp_session_manager = sm

    yield
    # == Shut down ==
    print("Shutting down the application...")


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


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT)