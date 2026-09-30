"""Catálogo de permisos.

Los permisos son capacidades del código (por eso viven aquí); los roles son datos que agrupan
permisos. Un rol nuevo creado desde la UI funciona sin tocar código porque toda la autorización
se evalúa por permiso, nunca por nombre de rol.
"""

from enum import StrEnum


class Permission(StrEnum):
    TICKETS_CREATE = "tickets:create"
    TICKETS_READ_OWN = "tickets:read_own"
    TICKETS_READ_ALL = "tickets:read_all"
    TICKETS_WORK = "tickets:work"
    TICKETS_MANAGE = "tickets:manage"
    TICKETS_COMMENT = "tickets:comment"
    DASHBOARD_VIEW = "dashboard:view"
    EXPORT_CSV = "export:csv"
    USERS_MANAGE = "users:manage"
    ROLES_MANAGE = "roles:manage"
    LOGS_VIEW = "logs:view"


PERMISSION_INFO: dict[Permission, tuple[str, str]] = {
    # permiso: (grupo, descripción)
    Permission.TICKETS_CREATE: ("Tickets", "Crear tickets"),
    Permission.TICKETS_READ_OWN: ("Tickets", "Ver tickets propios y asignados"),
    Permission.TICKETS_READ_ALL: ("Tickets", "Ver todos los tickets"),
    Permission.TICKETS_WORK: ("Tickets", "Atender tickets asignados (cambiar estatus)"),
    Permission.TICKETS_MANAGE: (
        "Tickets",
        "Administrar tickets (asignar, editar y mover cualquiera)",
    ),
    Permission.TICKETS_COMMENT: ("Tickets", "Comentar tickets"),
    Permission.DASHBOARD_VIEW: ("Analítica", "Ver dashboard"),
    Permission.EXPORT_CSV: ("Analítica", "Exportar a CSV"),
    Permission.USERS_MANAGE: ("Administración", "Administrar usuarios"),
    Permission.ROLES_MANAGE: ("Administración", "Administrar roles y permisos"),
    Permission.LOGS_VIEW: ("Administración", "Ver bitácora (inicios de sesión y auditoría)"),
}

ALL_PERMISSIONS: frozenset[Permission] = frozenset(Permission)
