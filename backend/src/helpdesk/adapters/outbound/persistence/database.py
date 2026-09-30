from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(url: str, pool_size: int = 10, echo: bool = False) -> AsyncEngine:
    return create_async_engine(
        url, pool_size=pool_size, max_overflow=pool_size, pool_pre_ping=True, echo=echo
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
