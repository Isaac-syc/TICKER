"""Esquema inicial: identidad (RBAC), tickets, sesiones y bitácora.

Revision ID: 0001
Revises:
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime(timezone=True)
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    # --- identidad / RBAC --------------------------------------------------------------------
    op.create_table(
        "permissions",
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("group_name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_permissions"),
    )
    op.create_table(
        "roles",
        sa.Column("id", UUID, nullable=False),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("single_tab_session", sa.Boolean(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", UUID, nullable=False),
        sa.Column("permission_code", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], name="fk_role_permissions_role_id_roles", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["permission_code"],
            ["permissions.code"],
            name="fk_role_permissions_permission_code_permissions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_code", name="pk_role_permissions"),
    )
    op.create_table(
        "users",
        sa.Column("id", UUID, nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role_id", UUID, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", TS, nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], name="fk_users_role_id_roles", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_role_id", "users", ["role_id"])

    # --- tickets ---------------------------------------------------------------------------------
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_categories"),
        sa.UniqueConstraint("name", name="uq_categories_name"),
    )
    op.execute(sa.schema.CreateSequence(sa.Sequence("ticket_number_seq", start=1)))
    op.create_table(
        "tickets",
        sa.Column("id", UUID, nullable=False),
        sa.Column(
            "number",
            sa.BigInteger(),
            server_default=sa.text("nextval('ticket_number_seq')"),
            nullable=False,
        ),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("requester_id", UUID, nullable=False),
        sa.Column("assignee_id", UUID, nullable=True),
        sa.Column("due_at", TS, nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.Column("resolved_at", TS, nullable=True),
        sa.Column("closed_at", TS, nullable=True),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_tickets_category_id_categories",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requester_id"],
            ["users.id"],
            name="fk_tickets_requester_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assignee_id"], ["users.id"], name="fk_tickets_assignee_id_users", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tickets"),
        sa.UniqueConstraint("number", name="uq_tickets_number"),
    )
    op.execute("ALTER SEQUENCE ticket_number_seq OWNED BY tickets.number")
    for column in ("status", "created_at", "requester_id", "assignee_id", "resolved_at"):
        op.create_index(f"ix_tickets_{column}", "tickets", [column])

    op.create_table(
        "ticket_events",
        sa.Column("id", UUID, nullable=False),
        sa.Column("ticket_id", UUID, nullable=False),
        sa.Column("actor_id", UUID, nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("from_status", sa.String(16), nullable=True),
        sa.Column("to_status", sa.String(16), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name="fk_ticket_events_ticket_id_tickets",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name="fk_ticket_events_actor_id_users", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ticket_events"),
    )
    op.create_index("ix_ticket_events_ticket_id", "ticket_events", ["ticket_id"])

    # --- sesiones y bitácora -------------------------------------------------------------------
    op.create_table(
        "auth_sessions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("family_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("revoked_at", TS, nullable=True),
        sa.Column("replaced_by", UUID, nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_auth_sessions_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_auth_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
    )
    op.create_index("ix_auth_sessions_family_id", "auth_sessions", ["family_id"])
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])

    op.create_table(
        "login_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("user_id", UUID, nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(32), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_login_events_user_id_users", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_login_events"),
    )
    for column in ("email", "user_id", "created_at"):
        op.create_index(f"ix_login_events_{column}", "login_events", [column])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("actor_id", UUID, nullable=True),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name="fk_audit_logs_actor_id_users", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
    )
    for column in ("action", "actor_id", "created_at"):
        op.create_index(f"ix_audit_logs_{column}", "audit_logs", [column])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("login_events")
    op.drop_table("auth_sessions")
    op.drop_table("ticket_events")
    op.drop_table("tickets")
    op.execute("DROP SEQUENCE IF EXISTS ticket_number_seq")
    op.drop_table("categories")
    op.drop_table("users")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("permissions")
