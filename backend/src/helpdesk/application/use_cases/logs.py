from collections.abc import AsyncIterator, Sequence

from helpdesk.application.dto import (
    AuditFilters,
    AuditLogView,
    Cell,
    LoginEventFilters,
    LoginEventView,
    Page,
    PageRequest,
    TabularExport,
)
from helpdesk.application.use_cases._common import UseCase, audit, require
from helpdesk.domain.audit.entities import AuditAction, RequestContext
from helpdesk.domain.identity.entities import User
from helpdesk.domain.identity.permissions import Permission

REASON_LABELS = {
    "invalid_credentials": "Credenciales inválidas",
    "inactive_user": "Usuario desactivado",
    "locked": "Bloqueado por intentos",
}


class ListLoginEvents(UseCase):
    async def execute(
        self, actor: User, filters: LoginEventFilters, page: PageRequest
    ) -> Page[LoginEventView]:
        require(actor, Permission.LOGS_VIEW)
        async with self._uow() as uow:
            return await uow.logs.login_events(filters, page)


class ListAuditLogs(UseCase):
    async def execute(
        self, actor: User, filters: AuditFilters, page: PageRequest
    ) -> Page[AuditLogView]:
        require(actor, Permission.LOGS_VIEW)
        async with self._uow() as uow:
            return await uow.logs.audit_logs(filters, page)


class ListAuditActions(UseCase):
    async def execute(self, actor: User) -> Sequence[str]:
        require(actor, Permission.LOGS_VIEW)
        async with self._uow() as uow:
            return await uow.logs.audit_actions()


class _ExportLogs(UseCase):
    async def _audit_export(self, actor: User, kind: str, ctx: RequestContext) -> None:
        async with self._uow() as uow:
            await audit(
                uow,
                AuditAction.LOGS_EXPORTED,
                actor=actor,
                entity_type="logs",
                entity_id=kind,
                ctx=ctx,
                now=self._clock.now(),
            )
            await uow.commit()


class ExportLoginEvents(_ExportLogs):
    HEADERS = ("Fecha", "Correo", "Usuario", "Resultado", "Motivo", "IP", "Navegador")

    async def execute(
        self, actor: User, filters: LoginEventFilters, ctx: RequestContext
    ) -> TabularExport:
        require(actor, Permission.LOGS_VIEW, Permission.EXPORT_CSV)
        await self._audit_export(actor, "logins", ctx)

        async def rows() -> AsyncIterator[Sequence[Cell]]:
            async with self._uow() as uow:
                async for e in uow.logs.iter_login_events(filters):
                    yield (
                        e.created_at,
                        e.email,
                        e.user_name or "",
                        "Exitoso" if e.success else "Fallido",
                        REASON_LABELS.get(e.reason or "", e.reason or ""),
                        e.ip or "",
                        e.user_agent or "",
                    )

        return TabularExport(filename_prefix="inicios-de-sesion", headers=self.HEADERS, rows=rows())


class ExportAuditLogs(_ExportLogs):
    HEADERS = ("Fecha", "Acción", "Actor", "Entidad", "ID entidad", "Detalle", "IP", "Request ID")

    async def execute(
        self, actor: User, filters: AuditFilters, ctx: RequestContext
    ) -> TabularExport:
        require(actor, Permission.LOGS_VIEW, Permission.EXPORT_CSV)
        await self._audit_export(actor, "audit", ctx)

        async def rows() -> AsyncIterator[Sequence[Cell]]:
            async with self._uow() as uow:
                async for e in uow.logs.iter_audit_logs(filters):
                    yield (
                        e.created_at,
                        e.action,
                        e.actor.full_name if e.actor else "Sistema",
                        e.entity_type,
                        e.entity_id or "",
                        ", ".join(f"{k}={v}" for k, v in e.metadata.items()),
                        e.ip or "",
                        e.request_id or "",
                    )

        return TabularExport(filename_prefix="auditoria", headers=self.HEADERS, rows=rows())
