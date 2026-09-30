"""Puertos (interfaces) que la aplicación necesita del mundo exterior.

Los adaptadores de salida (SQLAlchemy, Redis, JWT, argon2...) los implementan; las pruebas
unitarias usan implementaciones en memoria.
"""

from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from helpdesk.application.dto import (
    AuditFilters,
    AuditLogView,
    Category,
    DashboardData,
    DashboardQuery,
    LoginEventFilters,
    LoginEventView,
    Page,
    PageRequest,
    TicketEventView,
    TicketFilters,
    TicketListItem,
    TicketScope,
    UserFilters,
)
from helpdesk.domain.audit.entities import AuditEntry, LoginAttempt
from helpdesk.domain.identity.entities import Role, User
from helpdesk.domain.identity.permissions import Permission
from helpdesk.domain.identity.sessions import AuthSession
from helpdesk.domain.tickets.entities import Ticket

# --- Repositorios (lado de escritura) --------------------------------------------------------


class UserRepository(Protocol):
    async def get(self, user_id: UUID) -> User | None: ...
    async def get_by_email(self, email: str) -> User | None: ...
    async def add(self, user: User) -> None: ...
    async def save(self, user: User) -> None: ...
    async def list(self, filters: UserFilters, page: PageRequest) -> Page[User]: ...
    def iter_all(self, filters: UserFilters) -> AsyncIterator[User]: ...
    async def list_with_permission(self, permission: Permission) -> Sequence[User]: ...
    async def count_active_with_permission(self, permission: Permission) -> int: ...
    async def count_by_role(self, role_id: UUID) -> int: ...


class RoleRepository(Protocol):
    async def get(self, role_id: UUID) -> Role | None: ...
    async def get_by_name(self, name: str) -> Role | None: ...
    async def list(self) -> Sequence[Role]: ...
    async def add(self, role: Role) -> None: ...
    async def save(self, role: Role) -> None: ...
    async def delete(self, role_id: UUID) -> None: ...


class CategoryRepository(Protocol):
    async def list(self) -> Sequence[Category]: ...
    async def get(self, category_id: int) -> Category | None: ...


class TicketRepository(Protocol):
    async def get(self, ticket_id: UUID) -> Ticket | None: ...
    async def add(self, ticket: Ticket) -> None:
        """Persiste el ticket y sus eventos pendientes; asigna `ticket.number`."""
        ...

    async def save(self, ticket: Ticket) -> None: ...


class AuthSessionRepository(Protocol):
    async def get_by_token_hash(self, token_hash: str) -> AuthSession | None: ...
    async def add(self, session: AuthSession) -> None: ...
    async def save(self, session: AuthSession) -> None: ...
    async def revoke_family(self, family_id: UUID, now: datetime) -> None: ...
    async def revoke_all_for_user(self, user_id: UUID, now: datetime) -> None: ...
    async def is_family_active(self, family_id: UUID, now: datetime) -> bool: ...


class AuditRepository(Protocol):
    async def record(self, entry: AuditEntry) -> None: ...
    async def record_login(self, attempt: LoginAttempt) -> None: ...


# --- Consultas (lado de lectura) -------------------------------------------------------------


class TicketQueries(Protocol):
    async def list(
        self, filters: TicketFilters, scope: TicketScope, page: PageRequest, now: datetime
    ) -> Page[TicketListItem]: ...
    async def get_item(self, ticket_id: UUID, now: datetime) -> TicketListItem | None: ...
    async def get_description(self, ticket_id: UUID) -> str | None: ...
    async def events(self, ticket_id: UUID) -> Sequence[TicketEventView]: ...
    def iter_export(
        self, filters: TicketFilters, scope: TicketScope, now: datetime
    ) -> AsyncIterator[TicketListItem]: ...


class LogQueries(Protocol):
    async def login_events(
        self, filters: LoginEventFilters, page: PageRequest
    ) -> Page[LoginEventView]: ...
    def iter_login_events(self, filters: LoginEventFilters) -> AsyncIterator[LoginEventView]: ...
    async def audit_logs(self, filters: AuditFilters, page: PageRequest) -> Page[AuditLogView]: ...
    def iter_audit_logs(self, filters: AuditFilters) -> AsyncIterator[AuditLogView]: ...
    async def audit_actions(self) -> Sequence[str]: ...


class TicketAnalytics(Protocol):
    async def dashboard(self, query: DashboardQuery, now: datetime) -> DashboardData: ...


# --- Unidad de trabajo -----------------------------------------------------------------------


class UnitOfWork(Protocol):
    users: UserRepository
    roles: RoleRepository
    categories: CategoryRepository
    tickets: TicketRepository
    ticket_queries: TicketQueries
    sessions: AuthSessionRepository
    audit: AuditRepository
    logs: LogQueries
    analytics: TicketAnalytics

    async def __aenter__(self) -> Self: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


type UnitOfWorkFactory = Callable[[], UnitOfWork]


# --- Servicios ---------------------------------------------------------------------------------


class Clock(Protocol):
    def now(self) -> datetime: ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, password: str, password_hash: str) -> bool: ...


@dataclass(frozen=True)
class AccessToken:
    token: str
    expires_in: int


@dataclass(frozen=True)
class AccessClaims:
    user_id: UUID
    session_id: UUID


class TokenService(Protocol):
    def issue_access(self, user: User, session_id: UUID) -> AccessToken: ...
    def decode_access(self, token: str) -> AccessClaims:
        """Lanza AuthenticationError si el token es inválido o expiró."""
        ...

    def new_refresh_token(self) -> str: ...
    def hash_refresh_token(self, token: str) -> str: ...


class LoginRateLimiter(Protocol):
    async def is_locked(self, key: str) -> bool: ...
    async def register_failure(self, key: str) -> int: ...
    async def reset(self, key: str) -> None: ...


@dataclass(frozen=True)
class TabLease:
    tab_id: str
    session_id: UUID
    acquired_at: datetime


class TabLeaseStore(Protocol):
    """Lease con TTL que indica qué pestaña es la única activa de un usuario."""

    async def acquire(self, user_id: UUID, lease: TabLease) -> TabLease | None:
        """Toma el lease si está libre o renueva su TTL si ya es de esta pestaña.
        Devuelve el lease de la otra pestaña cuando no se pudo tomar; None si se obtuvo."""
        ...

    async def takeover(self, user_id: UUID, lease: TabLease) -> TabLease | None:
        """Fuerza el lease para esta pestaña y devuelve el anterior (si había)."""
        ...

    async def release(self, user_id: UUID, tab_id: str) -> None: ...
