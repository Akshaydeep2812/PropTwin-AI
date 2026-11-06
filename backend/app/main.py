from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.middleware import SlowAPIMiddleware

from app.api import admin, auth, blockchain, dashboard, health, market, notifications, properties, twins, users, valuations, verification
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, register_request_logging
from app.core.rate_limit import limiter
from app.workers.runner import Worker

settings = get_settings()
configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    worker = Worker() if settings.worker_enabled else None
    if worker:
        worker.start()
    yield
    if worker:
        worker.stop()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="API for property analytics, software-based digital twins, and tamper-evident records.",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)
register_request_logging(app)
register_exception_handlers(app)

for router in (
    health.router,
    auth.router,
    users.router,
    valuations.history_router,
    twins.property_router,
    twins.router,
    properties.router,
    properties.favorites_router,
    verification.router,
    valuations.router,
    blockchain.router,
    dashboard.router,
    market.router,
    notifications.router,
    valuations.admin_router,
    admin.router,
):
    app.include_router(router, prefix="/api/v1")
