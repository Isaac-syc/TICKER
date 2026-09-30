import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from helpdesk.domain.errors import ValidationError
from helpdesk.domain.identity.permissions import Permission

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ROLE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,39}$")

MIN_PASSWORD_LENGTH = 10


def normalize_email(raw: str) -> str:
    email = raw.strip().lower()
    if not _EMAIL_RE.match(email) or len(email) > 254:
        raise ValidationError("Correo electrónico inválido.")
    return email


def validate_password(password: str) -> None:
    """Política mínima: longitud y variedad de caracteres."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres."
        )
    checks = [
        any(c.islower() for c in password),
        any(c.isupper() for c in password),
        any(c.isdigit() for c in password),
        any(not c.isalnum() for c in password),
    ]
    if sum(checks) < 3:
        raise ValidationError(
            "La contraseña debe combinar al menos 3 de: minúsculas, mayúsculas, números y símbolos."
        )


@dataclass
class Role:
    id: UUID
    name: str
    description: str
    permissions: frozenset[Permission]
    single_tab_session: bool = False
    is_system: bool = False

    @classmethod
    def create(
        cls,
        *,
        name: str,
        description: str,
        permissions: Iterable[Permission],
        single_tab_session: bool = False,
        is_system: bool = False,
    ) -> "Role":
        role = cls(
            id=uuid4(),
            name=cls._validate_name(name),
            description=description.strip(),
            permissions=frozenset(permissions),
            single_tab_session=single_tab_session,
            is_system=is_system,
        )
        return role

    @staticmethod
    def _validate_name(name: str) -> str:
        normalized = name.strip().lower()
        if not _ROLE_NAME_RE.match(normalized):
            raise ValidationError(
                "El nombre del rol debe tener 2-40 caracteres: minúsculas, números, '-' o '_'."
            )
        return normalized

    def rename(self, name: str) -> None:
        if self.is_system and name.strip().lower() != self.name:
            raise ValidationError("Los roles del sistema no se pueden renombrar.")
        self.name = self._validate_name(name)

    def has(self, permission: Permission) -> bool:
        return permission in self.permissions


@dataclass
class User:
    id: UUID
    email: str
    full_name: str
    password_hash: str
    role: Role
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None

    @classmethod
    def register(
        cls, *, email: str, full_name: str, password_hash: str, role: Role, now: datetime
    ) -> "User":
        return cls(
            id=uuid4(),
            email=normalize_email(email),
            full_name=cls._validate_name(full_name),
            password_hash=password_hash,
            role=role,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def _validate_name(full_name: str) -> str:
        name = " ".join(full_name.split())
        if not 2 <= len(name) <= 120:
            raise ValidationError("El nombre debe tener entre 2 y 120 caracteres.")
        return name

    def can(self, permission: Permission) -> bool:
        return self.is_active and self.role.has(permission)

    @property
    def permissions(self) -> frozenset[Permission]:
        return self.role.permissions if self.is_active else frozenset()

    def update_profile(self, *, email: str, full_name: str, now: datetime) -> None:
        self.email = normalize_email(email)
        self.full_name = self._validate_name(full_name)
        self.updated_at = now

    def change_role(self, role: Role, now: datetime) -> None:
        self.role = role
        self.updated_at = now

    def set_active(self, active: bool, now: datetime) -> None:
        self.is_active = active
        self.updated_at = now

    def set_password_hash(self, password_hash: str, now: datetime) -> None:
        self.password_hash = password_hash
        self.updated_at = now

    def record_login(self, now: datetime) -> None:
        self.last_login_at = now


@dataclass(frozen=True)
class Principal:
    """Identidad autenticada de una petición (usuario + sesión de login)."""

    user: User
    session_id: UUID
