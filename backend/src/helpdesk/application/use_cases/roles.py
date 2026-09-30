from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from uuid import UUID

from helpdesk.application.ports import UnitOfWork
from helpdesk.application.use_cases._common import UseCase, audit, require
from helpdesk.domain.audit.entities import AuditAction, RequestContext
from helpdesk.domain.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from helpdesk.domain.identity.entities import Role, User
from helpdesk.domain.identity.permissions import ALL_PERMISSIONS, PERMISSION_INFO, Permission

ADMIN_ROLE = "admin"
# Permisos que un administrador no puede quitarle a su propio rol (evita dejarse fuera).
SELF_LOCKOUT_GUARD = frozenset({Permission.ROLES_MANAGE, Permission.USERS_MANAGE})


@dataclass(frozen=True)
class PermissionInfo:
    code: Permission
    group: str
    description: str


@dataclass(frozen=True)
class RoleWithUsage:
    role: Role
    user_count: int


def _parse_permissions(codes: Iterable[str]) -> frozenset[Permission]:
    try:
        return frozenset(Permission(c) for c in codes)
    except ValueError as exc:
        raise ValidationError(f"Permiso desconocido: {exc}") from exc


async def _get_role(uow: UnitOfWork, role_id: UUID) -> Role:
    role = await uow.roles.get(role_id)
    if role is None:
        raise NotFoundError("El rol no existe.")
    return role


class ListPermissions(UseCase):
    async def execute(self, actor: User) -> Sequence[PermissionInfo]:
        require(actor, Permission.ROLES_MANAGE)
        return [
            PermissionInfo(code=p, group=PERMISSION_INFO[p][0], description=PERMISSION_INFO[p][1])
            for p in Permission
        ]


class ListRoles(UseCase):
    async def execute(self, actor: User) -> Sequence[RoleWithUsage]:
        # Quien administra usuarios necesita la lista para asignar roles.
        if not (actor.can(Permission.ROLES_MANAGE) or actor.can(Permission.USERS_MANAGE)):
            raise PermissionDeniedError()
        async with self._uow() as uow:
            roles = await uow.roles.list()
            return [RoleWithUsage(r, await uow.users.count_by_role(r.id)) for r in roles]


class CreateRole(UseCase):
    async def execute(
        self,
        actor: User,
        *,
        name: str,
        description: str,
        permissions: Iterable[str],
        single_tab_session: bool,
        ctx: RequestContext,
    ) -> Role:
        require(actor, Permission.ROLES_MANAGE)
        now = self._clock.now()
        role = Role.create(
            name=name,
            description=description,
            permissions=_parse_permissions(permissions),
            single_tab_session=single_tab_session,
        )
        async with self._uow() as uow:
            if await uow.roles.get_by_name(role.name):
                raise ConflictError("Ya existe un rol con ese nombre.")
            await uow.roles.add(role)
            await audit(
                uow,
                AuditAction.ROLE_CREATED,
                actor=actor,
                entity_type="role",
                entity_id=role.id,
                ctx=ctx,
                now=now,
                name=role.name,
                permissions=sorted(role.permissions),
                single_tab_session=single_tab_session,
            )
            await uow.commit()
            return role


class UpdateRole(UseCase):
    async def execute(
        self,
        actor: User,
        role_id: UUID,
        *,
        ctx: RequestContext,
        name: str | None = None,
        description: str | None = None,
        permissions: Iterable[str] | None = None,
        single_tab_session: bool | None = None,
    ) -> Role:
        require(actor, Permission.ROLES_MANAGE)
        now = self._clock.now()
        async with self._uow() as uow:
            role = await _get_role(uow, role_id)
            if name is not None and name.strip().lower() != role.name:
                role.rename(name)
                other = await uow.roles.get_by_name(role.name)
                if other and other.id != role.id:
                    raise ConflictError("Ya existe un rol con ese nombre.")
            if description is not None:
                role.description = description.strip()
            if permissions is not None:
                new_perms = _parse_permissions(permissions)
                if role.is_system and role.name == ADMIN_ROLE and new_perms != ALL_PERMISSIONS:
                    raise ValidationError("El rol admin siempre conserva todos los permisos.")
                if role.id == actor.role.id and not new_perms >= SELF_LOCKOUT_GUARD:
                    raise ValidationError(
                        "No puedes quitar la administración de usuarios o roles a tu propio rol."
                    )
                role.permissions = new_perms
            if single_tab_session is not None:
                role.single_tab_session = single_tab_session
            await uow.roles.save(role)
            await audit(
                uow,
                AuditAction.ROLE_UPDATED,
                actor=actor,
                entity_type="role",
                entity_id=role.id,
                ctx=ctx,
                now=now,
                name=role.name,
                permissions=sorted(role.permissions),
                single_tab_session=role.single_tab_session,
            )
            await uow.commit()
            return role


class DeleteRole(UseCase):
    async def execute(self, actor: User, role_id: UUID, ctx: RequestContext) -> None:
        require(actor, Permission.ROLES_MANAGE)
        now = self._clock.now()
        async with self._uow() as uow:
            role = await _get_role(uow, role_id)
            if role.is_system:
                raise ValidationError("Los roles del sistema no se pueden eliminar.")
            if await uow.users.count_by_role(role.id) > 0:
                raise ConflictError("El rol tiene usuarios asignados; reasígnalos primero.")
            await uow.roles.delete(role.id)
            await audit(
                uow,
                AuditAction.ROLE_DELETED,
                actor=actor,
                entity_type="role",
                entity_id=role.id,
                ctx=ctx,
                now=now,
                name=role.name,
            )
            await uow.commit()
