from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import APIRouter, FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from helpdesk.adapters.inbound.http.deps import Container
from helpdesk.adapters.inbound.http.errors import register_error_handlers
from helpdesk.adapters.inbound.http.middleware import RequestContextMiddleware
from helpdesk.adapters.inbound.http.routers import admin, auth, dashboard, tickets
from helpdesk.adapters.inbound.http.schemas import HealthOut
from helpdesk.config import Settings

log = structlog.get_logger("helpdesk")

API_PREFIX = "/api/v1"


def _health_router() -> APIRouter:
    router = APIRouter(prefix="/api/health", tags=["health"])

    @router.get("/live", response_model=HealthOut)
    async def live() -> HealthOut:
        return HealthOut(status="ok")

    @router.get("/ready", response_model=HealthOut)
    async def ready(request: Request) -> HealthOut | JSONResponse:
        c: Container = request.app.state.container
        checks: dict[str, str] = {}
        try:
            async with c.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = f"error: {type(exc).__name__}"
        try:
            await c.redis.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            checks["redis"] = f"error: {type(exc).__name__}"
        healthy = all(v == "ok" for v in checks.values())
        body = HealthOut(status="ok" if healthy else "degraded", checks=checks)
        if healthy:
            return body
        return JSONResponse(body.model_dump(), status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

    return router


def create_app(container_factory: Callable[[], Container], settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = container_factory()
        app.state.container = container
        app.state.settings = settings
        log.info("startup", env=settings.app_env)
        try:
            yield
        finally:
            await container.aclose()
            log.info("shutdown")

    is_prod = settings.app_env == "prod"
    app = FastAPI(
        title="Helpdesk TI API",
        version="0.1.0",
        description="Seguimiento de tickets de TI. Arquitectura hexagonal + JWT.",
        lifespan=lifespan,
        docs_url=None if is_prod else "/api/docs",
        redoc_url=None,
        openapi_url=None if is_prod else "/api/openapi.json",
    )
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    app.include_router(_health_router())
    for module in (auth, tickets, dashboard, admin):
        app.include_router(module.router, prefix=API_PREFIX)
    return app
