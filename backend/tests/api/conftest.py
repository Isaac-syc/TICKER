"""Pruebas de API end-to-end contra PostgreSQL y Redis reales.

Se activan con TEST_DATABASE_URL (BD desechable: se recrea el esquema) y TEST_REDIS_URL.
Ejemplo con el stack de Docker: ver `make test-api` o el job `backend` del CI.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from helpdesk.adapters.inbound.cli.seed import run_seed
from helpdesk.adapters.inbound.http.app import create_app
from helpdesk.config import Settings
from helpdesk.container import Container

DB_URL = os.environ.get("TEST_DATABASE_URL")
REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")
BACKEND_DIR = Path(__file__).resolve().parents[2]

if not DB_URL:
    collect_ignore_glob = ["test_*.py"]

PASSWORDS = {
    "admin": "Admin#Test2026",
    "user": "Usuario#Test2026",
    "observer": "Observador#Test2026",
}
EMAILS = {
    "admin": "admin@helpdesk.test",
    "user": "usuario@helpdesk.test",
    "observer": "observador@helpdesk.test",
}


def test_settings() -> Settings:
    assert DB_URL
    return Settings(
        app_env="test",
        database_url=DB_URL,
        redis_url=REDIS_URL,
        jwt_secret=SecretStr("test-secret-" + "x" * 40),
        cookie_secure=False,
        log_json=False,
        login_max_attempts=3,
        seed_admin_password=SecretStr(PASSWORDS["admin"]),
        seed_user_password=SecretStr(PASSWORDS["user"]),
        seed_observer_password=SecretStr(PASSWORDS["observer"]),
        seed_demo_data=True,
    )


async def _reset_database(url: str) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()


def _alembic(*args: str) -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    getattr(command, args[0])(cfg, *args[1:])


@pytest.fixture(scope="session")
async def app() -> AsyncIterator[FastAPI]:
    settings = test_settings()
    os.environ["DATABASE_URL"] = settings.database_url
    await _reset_database(settings.database_url)
    # Se prueba el ciclo completo de migraciones: subir, bajar y volver a subir.
    await asyncio.to_thread(_alembic, "upgrade", "head")
    await asyncio.to_thread(_alembic, "downgrade", "base")
    await asyncio.to_thread(_alembic, "upgrade", "head")
    await run_seed(settings)

    container = Container(settings)
    await container.redis.flushdb()
    application = create_app(lambda: container, settings)
    application.state.container = container  # ASGITransport no ejecuta el lifespan
    application.state.settings = settings
    yield application
    await container.redis.flushdb()
    await container.aclose()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@dataclass
class Session:
    client: httpx.AsyncClient
    token: str
    me: dict[str, object]
    tab_id: str | None = None

    @property
    def headers(self) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self.token}"}
        if self.tab_id:
            h["X-Tab-Id"] = self.tab_id
        return h

    async def get(self, url: str, **kw: object) -> httpx.Response:
        return await self.client.get(url, headers=self.headers, **kw)  # type: ignore[arg-type]

    async def post(self, url: str, **kw: object) -> httpx.Response:
        return await self.client.post(url, headers=self.headers, **kw)  # type: ignore[arg-type]

    async def patch(self, url: str, **kw: object) -> httpx.Response:
        return await self.client.patch(url, headers=self.headers, **kw)  # type: ignore[arg-type]

    async def delete(self, url: str) -> httpx.Response:
        return await self.client.delete(url, headers=self.headers)


async def login(client: httpx.AsyncClient, who: str, password: str | None = None) -> Session:
    email = EMAILS.get(who, who)
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password or PASSWORDS[who]}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    return Session(client=client, token=body["access_token"], me=body["user"])
