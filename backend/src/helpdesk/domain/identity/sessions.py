from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

# Si dos pestañas del mismo usuario refrescan casi al mismo tiempo, la segunda llega con el
# refresh token recién rotado. Dentro de esta ventana no se considera robo de token.
REUSE_GRACE = timedelta(seconds=30)


@dataclass
class AuthSession:
    """Un refresh token emitido. Todas las rotaciones de un mismo login comparten `family_id`,
    que es también el `sid` del JWT de acceso."""

    id: UUID
    family_id: UUID
    user_id: UUID
    token_hash: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    replaced_by: UUID | None = None
    ip: str | None = None
    user_agent: str | None = None

    @classmethod
    def start(
        cls,
        *,
        user_id: UUID,
        token_hash: str,
        ttl: timedelta,
        now: datetime,
        family_id: UUID | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> "AuthSession":
        return cls(
            id=uuid4(),
            family_id=family_id or uuid4(),
            user_id=user_id,
            token_hash=token_hash,
            created_at=now,
            expires_at=now + ttl,
            ip=ip,
            user_agent=user_agent,
        )

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def rotated_recently(self, now: datetime) -> bool:
        return (
            self.replaced_by is not None
            and self.revoked_at is not None
            and now - self.revoked_at <= REUSE_GRACE
        )

    def revoke(self, now: datetime, *, replaced_by: UUID | None = None) -> None:
        if self.revoked_at is None:
            self.revoked_at = now
            self.replaced_by = replaced_by
