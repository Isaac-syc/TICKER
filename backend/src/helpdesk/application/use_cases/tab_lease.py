"""Regla de "una sola pestaña" para roles con `single_tab_session`.

El front usa Web Locks para detectar pestañas duplicadas en el mismo navegador; este módulo es la
fuente de verdad del lado del servidor y además cubre otros navegadores o dispositivos.
"""

from dataclasses import dataclass

from helpdesk.application.ports import Clock, TabLease, TabLeaseStore, UnitOfWorkFactory
from helpdesk.application.use_cases._common import UseCase, audit
from helpdesk.domain.audit.entities import AuditAction, RequestContext
from helpdesk.domain.errors import TabConflictError, ValidationError
from helpdesk.domain.identity.entities import Principal

TAB_CONFLICT_MESSAGE = "Tu sesión está activa en otra pestaña o dispositivo."


@dataclass(frozen=True)
class TabStatus:
    required: bool
    granted: bool
    other_device: bool = False


def _validate_tab_id(tab_id: str | None) -> str:
    if not tab_id or not 8 <= len(tab_id) <= 64:
        raise ValidationError("Identificador de pestaña inválido.")
    return tab_id


class _TabUseCase(UseCase):
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock, leases: TabLeaseStore) -> None:
        super().__init__(uow_factory, clock)
        self._leases = leases

    def _lease(self, principal: Principal, tab_id: str) -> TabLease:
        return TabLease(
            tab_id=tab_id, session_id=principal.session_id, acquired_at=self._clock.now()
        )


class ClaimTab(_TabUseCase):
    """Reclama o renueva el lease. También sirve como heartbeat."""

    async def execute(self, principal: Principal, tab_id: str | None) -> TabStatus:
        if not principal.user.role.single_tab_session:
            return TabStatus(required=False, granted=True)
        tab = _validate_tab_id(tab_id)
        holder = await self._leases.acquire(principal.user.id, self._lease(principal, tab))
        if holder is None:
            return TabStatus(required=True, granted=True)
        return TabStatus(
            required=True, granted=False, other_device=holder.session_id != principal.session_id
        )


class EnsureActiveTab(_TabUseCase):
    """Guardia que corre en cada petición de negocio de un rol restringido."""

    async def execute(self, principal: Principal, tab_id: str | None) -> None:
        if not principal.user.role.single_tab_session:
            return
        if not tab_id:
            raise TabConflictError("Falta el identificador de pestaña (X-Tab-Id).")
        holder = await self._leases.acquire(principal.user.id, self._lease(principal, tab_id))
        if holder is not None:
            raise TabConflictError(TAB_CONFLICT_MESSAGE)


class TakeoverTab(_TabUseCase):
    """ "Usar aquí": mueve la sesión a esta pestaña. Si la anterior era de otro navegador o
    dispositivo, se revoca aquella sesión para cumplir la regla de sesión única."""

    async def execute(
        self, principal: Principal, tab_id: str | None, ctx: RequestContext
    ) -> TabStatus:
        if not principal.user.role.single_tab_session:
            return TabStatus(required=False, granted=True)
        tab = _validate_tab_id(tab_id)
        previous = await self._leases.takeover(principal.user.id, self._lease(principal, tab))
        other_device = previous is not None and previous.session_id != principal.session_id
        now = self._clock.now()
        async with self._uow() as uow:
            if previous is not None and other_device:
                await uow.sessions.revoke_family(previous.session_id, now)
            await audit(
                uow,
                AuditAction.SESSION_TAKEOVER,
                actor=principal.user,
                entity_type="session",
                entity_id=principal.session_id,
                ctx=ctx,
                now=now,
                previous_tab=previous.tab_id if previous else None,
                other_device=other_device,
            )
            await uow.commit()
        return TabStatus(required=True, granted=True, other_device=other_device)


class ReleaseTab(_TabUseCase):
    async def execute(self, principal: Principal, tab_id: str | None) -> None:
        if principal.user.role.single_tab_session and tab_id:
            await self._leases.release(principal.user.id, tab_id)
