from types import TracebackType
from typing import Self
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from helpdesk.adapters.outbound.persistence.analytics import SqlTicketAnalytics
from helpdesk.adapters.outbound.persistence.queries import SqlLogQueries, SqlTicketQueries
from helpdesk.adapters.outbound.persistence.repositories import (
    SqlAuditRepository,
    SqlAuthSessionRepository,
    SqlCategoryRepository,
    SqlRoleRepository,
    SqlTicketRepository,
    SqlUserRepository,
)
from helpdesk.application.ports import (
    AuditRepository,
    AuthSessionRepository,
    CategoryRepository,
    LogQueries,
    RoleRepository,
    TicketAnalytics,
    TicketQueries,
    TicketRepository,
    UserRepository,
)


class SqlAlchemyUnitOfWork:
    """Una transacción por caso de uso. Si no se llama a commit(), se hace rollback."""

    users: UserRepository
    roles: RoleRepository
    categories: CategoryRepository
    tickets: TicketRepository
    ticket_queries: TicketQueries
    sessions: AuthSessionRepository
    audit: AuditRepository
    logs: LogQueries
    analytics: TicketAnalytics

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], tz: ZoneInfo) -> None:
        self._factory = session_factory
        self._tz = tz
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> Self:
        session = self._factory()
        self._session = session
        self.users = SqlUserRepository(session)
        self.roles = SqlRoleRepository(session)
        self.categories = SqlCategoryRepository(session)
        self.tickets = SqlTicketRepository(session)
        self.ticket_queries = SqlTicketQueries(session, self._tz)
        self.sessions = SqlAuthSessionRepository(session)
        self.audit = SqlAuditRepository(session)
        self.logs = SqlLogQueries(session, self._tz)
        self.analytics = SqlTicketAnalytics(session, self._tz)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._session is not None
        try:
            if self._session.in_transaction():
                await self._session.rollback()
        finally:
            await self._session.close()
            self._session = None

    async def commit(self) -> None:
        assert self._session is not None
        await self._session.commit()

    async def rollback(self) -> None:
        assert self._session is not None
        await self._session.rollback()
