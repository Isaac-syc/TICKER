from collections.abc import Callable
from dataclasses import dataclass

import pytest

from helpdesk.domain.identity.entities import Role, User
from helpdesk.domain.identity.permissions import ALL_PERMISSIONS, Permission
from helpdesk.domain.tickets.sla import SlaPolicy
from tests.unit.fakes import (
    FakeClock,
    FakeLeaseStore,
    FakeLimiter,
    FakeTokens,
    FakeUnitOfWork,
    PlainHasher,
    Store,
)

P = Permission


def make_roles() -> dict[str, Role]:
    return {
        "admin": Role.create(
            name="admin", description="", permissions=ALL_PERMISSIONS, is_system=True
        ),
        "usuario": Role.create(
            name="usuario",
            description="",
            permissions={
                P.TICKETS_CREATE,
                P.TICKETS_READ_OWN,
                P.TICKETS_WORK,
                P.TICKETS_COMMENT,
                P.DASHBOARD_VIEW,
                P.EXPORT_CSV,
            },
            is_system=True,
        ),
        "observador": Role.create(
            name="observador",
            description="",
            permissions={P.TICKETS_READ_ALL, P.DASHBOARD_VIEW, P.EXPORT_CSV},
            single_tab_session=True,
            is_system=True,
        ),
    }


@dataclass
class World:
    store: Store
    clock: FakeClock
    roles: dict[str, Role]
    admin: User
    user: User
    tech: User
    observer: User
    hasher: PlainHasher
    tokens: FakeTokens
    limiter: FakeLimiter
    leases: FakeLeaseStore
    sla: SlaPolicy

    @property
    def uow(self) -> Callable[[], FakeUnitOfWork]:
        return lambda: FakeUnitOfWork(self.store)


@pytest.fixture
def world() -> World:
    store = Store()
    clock = FakeClock()
    roles = make_roles()
    for r in roles.values():
        store.roles[r.id] = r
    hasher = PlainHasher()

    def mk(email: str, name: str, role: str) -> User:
        u = User.register(
            email=email,
            full_name=name,
            password_hash=hasher.hash("Secreta#2026"),
            role=roles[role],
            now=clock.now(),
        )
        store.users[u.id] = u
        return u

    return World(
        store=store,
        clock=clock,
        roles=roles,
        admin=mk("admin@test.mx", "Ana Admin", "admin"),
        user=mk("user@test.mx", "Ulises User", "usuario"),
        tech=mk("tech@test.mx", "Tere Técnica", "usuario"),
        observer=mk("obs@test.mx", "Olga Obs", "observador"),
        hasher=hasher,
        tokens=FakeTokens(),
        limiter=FakeLimiter(max_attempts=3),
        leases=FakeLeaseStore(),
        sla=SlaPolicy(),
    )
