"""Adaptadores en memoria: permiten probar casos de uso sin BD ni Redis (ventaja de la hexagonal)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any, Self
from uuid import UUID

from helpdesk.application.dto import Category, Page, PageRequest, UserFilters
from helpdesk.application.ports import AccessClaims, AccessToken, TabLease
from helpdesk.domain.audit.entities import AuditEntry, LoginAttempt
from helpdesk.domain.errors import AuthenticationError
from helpdesk.domain.identity.entities import Role, User
from helpdesk.domain.identity.permissions import Permission
from helpdesk.domain.identity.sessions import AuthSession
from helpdesk.domain.tickets.entities import Ticket, TicketEvent


class FakeClock:
    def __init__(self, now: datetime | None = None) -> None:
        self.current = now or datetime(2026, 9, 1, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, **kwargs: float) -> None:
        self.current += timedelta(**kwargs)


class PlainHasher:
    def hash(self, password: str) -> str:
        return f"hashed::{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        return password_hash == f"hashed::{password}"


class FakeTokens:
    def __init__(self) -> None:
        self._counter = 0

    def issue_access(self, user: User, session_id: UUID) -> AccessToken:
        return AccessToken(token=f"access::{user.id}::{session_id}", expires_in=900)

    def decode_access(self, token: str) -> AccessClaims:
        try:
            _, user_id, session_id = token.split("::")
            return AccessClaims(UUID(user_id), UUID(session_id))
        except ValueError as exc:
            raise AuthenticationError("Token inválido.") from exc

    def new_refresh_token(self) -> str:
        self._counter += 1
        return f"refresh-{self._counter}"

    def hash_refresh_token(self, token: str) -> str:
        return f"h({token})"


class FakeLimiter:
    def __init__(self, max_attempts: int = 3) -> None:
        self.max = max_attempts
        self.failures: dict[str, int] = {}

    async def is_locked(self, key: str) -> bool:
        return self.failures.get(key, 0) >= self.max

    async def register_failure(self, key: str) -> int:
        self.failures[key] = self.failures.get(key, 0) + 1
        return self.failures[key]

    async def reset(self, key: str) -> None:
        self.failures.pop(key, None)


class FakeLeaseStore:
    def __init__(self) -> None:
        self.leases: dict[UUID, TabLease] = {}

    async def acquire(self, user_id: UUID, lease: TabLease) -> TabLease | None:
        current = self.leases.get(user_id)
        if current is None or current.tab_id == lease.tab_id:
            self.leases[user_id] = lease
            return None
        return current

    async def takeover(self, user_id: UUID, lease: TabLease) -> TabLease | None:
        previous = self.leases.get(user_id)
        self.leases[user_id] = lease
        return previous if previous and previous.tab_id != lease.tab_id else None

    async def release(self, user_id: UUID, tab_id: str) -> None:
        if (current := self.leases.get(user_id)) and current.tab_id == tab_id:
            del self.leases[user_id]


@dataclass
class Store:
    users: dict[UUID, User] = field(default_factory=dict)
    roles: dict[UUID, Role] = field(default_factory=dict)
    tickets: dict[UUID, Ticket] = field(default_factory=dict)
    events: list[TicketEvent] = field(default_factory=list)
    sessions: dict[UUID, AuthSession] = field(default_factory=dict)
    audit: list[AuditEntry] = field(default_factory=list)
    logins: list[LoginAttempt] = field(default_factory=list)
    categories: dict[int, Category] = field(
        default_factory=lambda: {1: Category(1, "Hardware"), 2: Category(2, "Software")}
    )
    next_ticket_number: int = 1
    commits: int = 0


class _Users:
    def __init__(self, s: Store) -> None:
        self.s = s

    async def get(self, user_id: UUID) -> User | None:
        u = self.s.users.get(user_id)
        return replace(u, role=self.s.roles.get(u.role.id, u.role)) if u else None

    async def get_by_email(self, email: str) -> User | None:
        return next((replace(u) for u in self.s.users.values() if u.email == email), None)

    async def add(self, user: User) -> None:
        self.s.users[user.id] = replace(user)

    async def save(self, user: User) -> None:
        self.s.users[user.id] = replace(user)

    async def list(self, filters: UserFilters, page: PageRequest) -> Page[User]:
        items = list(self.s.users.values())
        return Page(items, len(items), page.page, page.page_size)

    async def iter_all(self, filters: UserFilters) -> AsyncIterator[User]:
        for u in list(self.s.users.values()):
            yield u

    def _current(self) -> list[User]:
        return [replace(u, role=self.s.roles.get(u.role.id, u.role)) for u in self.s.users.values()]

    async def list_with_permission(self, permission: Permission) -> Sequence[User]:
        return [u for u in self._current() if u.can(permission)]

    async def count_active_with_permission(self, permission: Permission) -> int:
        return len(await self.list_with_permission(permission))

    async def count_by_role(self, role_id: UUID) -> int:
        return sum(1 for u in self.s.users.values() if u.role.id == role_id)


class _Roles:
    def __init__(self, s: Store) -> None:
        self.s = s

    async def get(self, role_id: UUID) -> Role | None:
        r = self.s.roles.get(role_id)
        return replace(r) if r else None

    async def get_by_name(self, name: str) -> Role | None:
        return next((replace(r) for r in self.s.roles.values() if r.name == name), None)

    async def list(self) -> Sequence[Role]:
        return list(self.s.roles.values())

    async def add(self, role: Role) -> None:
        self.s.roles[role.id] = replace(role)

    async def save(self, role: Role) -> None:
        self.s.roles[role.id] = replace(role)

    async def delete(self, role_id: UUID) -> None:
        self.s.roles.pop(role_id, None)


class _Categories:
    def __init__(self, s: Store) -> None:
        self.s = s

    async def list(self) -> Sequence[Category]:
        return list(self.s.categories.values())

    async def get(self, category_id: int) -> Category | None:
        return self.s.categories.get(category_id)


class _Tickets:
    def __init__(self, s: Store) -> None:
        self.s = s

    async def get(self, ticket_id: UUID) -> Ticket | None:
        t = self.s.tickets.get(ticket_id)
        return replace(t, _pending_events=[]) if t else None

    async def add(self, ticket: Ticket) -> None:
        ticket.number = self.s.next_ticket_number
        self.s.next_ticket_number += 1
        await self.save(ticket)

    async def save(self, ticket: Ticket) -> None:
        self.s.events.extend(ticket.pull_events())
        self.s.tickets[ticket.id] = replace(ticket, _pending_events=[])


class _Sessions:
    def __init__(self, s: Store) -> None:
        self.s = s

    async def get_by_token_hash(self, token_hash: str) -> AuthSession | None:
        found = next((x for x in self.s.sessions.values() if x.token_hash == token_hash), None)
        return replace(found) if found else None

    async def add(self, session: AuthSession) -> None:
        self.s.sessions[session.id] = replace(session)

    async def save(self, session: AuthSession) -> None:
        self.s.sessions[session.id] = replace(session)

    async def revoke_family(self, family_id: UUID, now: datetime) -> None:
        for x in self.s.sessions.values():
            if x.family_id == family_id and x.revoked_at is None:
                x.revoked_at = now

    async def revoke_all_for_user(self, user_id: UUID, now: datetime) -> None:
        for x in self.s.sessions.values():
            if x.user_id == user_id and x.revoked_at is None:
                x.revoked_at = now

    async def is_family_active(self, family_id: UUID, now: datetime) -> bool:
        return any(
            x.family_id == family_id and x.revoked_at is None and x.expires_at > now
            for x in self.s.sessions.values()
        )


class _Audit:
    def __init__(self, s: Store) -> None:
        self.s = s

    async def record(self, entry: AuditEntry) -> None:
        self.s.audit.append(entry)

    async def record_login(self, attempt: LoginAttempt) -> None:
        self.s.logins.append(attempt)


class FakeUnitOfWork:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.users: Any = _Users(store)
        self.roles: Any = _Roles(store)
        self.categories: Any = _Categories(store)
        self.tickets: Any = _Tickets(store)
        self.sessions: Any = _Sessions(store)
        self.audit: Any = _Audit(store)
        self.ticket_queries: Any = None
        self.logs: Any = None
        self.analytics: Any = None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        self.store.commits += 1

    async def rollback(self) -> None:
        return None
