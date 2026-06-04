import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager

from .config import settings
from .routers import (
    root,
    status,
    hkex,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Perform any startup tasks here
    print("Starting up the application...")
    yield
    # Perform any shutdown tasks here
    print("Shutting down the application...")


# Initialize with lifespan and configuration
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)


# Include API routers
app.include_router(root.router)
app.include_router(status.router)
app.include_router(hkex.router)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT)