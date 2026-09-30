"""Modelos ORM. Son detalle de infraestructura: el dominio nunca los ve (ver mappers.py)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    Sequence,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {  # noqa: RUF012
        datetime: DateTime(timezone=True),
        UUID: PgUUID(as_uuid=True),
        dict[str, Any]: JSONB,
    }


# Numeración legible de tickets (TCK-000123) independiente del UUID.
ticket_number_seq = Sequence("ticket_number_seq", start=1, metadata=Base.metadata)


class PermissionModel(Base):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    group_name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(255))


class RolePermissionModel(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_code: Mapped[str] = mapped_column(
        ForeignKey("permissions.code", ondelete="CASCADE"), primary_key=True
    )


class RoleModel(Base):
    __tablename__ = "roles"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    single_tab_session: Mapped[bool] = mapped_column(Boolean, default=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    permission_links: Mapped[list[RolePermissionModel]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    role: Mapped[RoleModel] = relationship(lazy="joined")


class CategoryModel(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class TicketModel(Base):
    __tablename__ = "tickets"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    id: Mapped[UUID] = mapped_column(primary_key=True)
    number: Mapped[int] = mapped_column(
        BigInteger, ticket_number_seq, server_default=ticket_number_seq.next_value(), unique=True
    )
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"))
    priority: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    requester_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    assignee_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    due_at: Mapped[datetime]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    resolved_at: Mapped[datetime | None]
    closed_at: Mapped[datetime | None]

    __table_args__ = (
        Index("ix_tickets_status", "status"),
        Index("ix_tickets_created_at", "created_at"),
        Index("ix_tickets_requester_id", "requester_id"),
        Index("ix_tickets_assignee_id", "assignee_id"),
        Index("ix_tickets_resolved_at", "resolved_at"),
    )


class TicketEventModel(Base):
    __tablename__ = "ticket_events"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    type: Mapped[str] = mapped_column(String(32))
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str | None] = mapped_column(String(16))
    comment: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime]


class AuthSessionModel(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    family_id: Mapped[UUID] = mapped_column(index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    replaced_by: Mapped[UUID | None]
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))


class LoginEventModel(Base):
    __tablename__ = "login_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), index=True)
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    success: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(String(32))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(index=True)


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    actor_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", default=dict)
    ip: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(index=True)
