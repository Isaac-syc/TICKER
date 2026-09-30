import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from helpdesk.application.ports import AccessClaims, AccessToken
from helpdesk.domain.errors import AuthenticationError
from helpdesk.domain.identity.entities import User

ALGORITHM = "HS256"


class Argon2PasswordHasher:
    def __init__(self) -> None:
        self._hasher = PasswordHash((Argon2Hasher(),))

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            return self._hasher.verify(password, password_hash)
        except Exception:  # hash corrupto o de otro algoritmo
            return False


class JwtTokenService:
    def __init__(self, secret: str, issuer: str, access_ttl: timedelta) -> None:
        self._secret = secret
        self._issuer = issuer
        self._ttl = access_ttl

    def issue_access(self, user: User, session_id: UUID) -> AccessToken:
        now = datetime.now(UTC)
        payload = {
            "sub": str(user.id),
            "sid": str(session_id),
            "typ": "access",
            "iss": self._issuer,
            "iat": now,
            "nbf": now,
            "exp": now + self._ttl,
            # Claims informativos para el front; el back siempre recarga permisos de la BD.
            "role": user.role.name,
            "perms": sorted(user.permissions),
            "stt": user.role.single_tab_session,
        }
        token = jwt.encode(payload, self._secret, algorithm=ALGORITHM)
        return AccessToken(token=token, expires_in=int(self._ttl.total_seconds()))

    def decode_access(self, token: str) -> AccessClaims:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[ALGORITHM],
                issuer=self._issuer,
                options={"require": ["exp", "sub", "sid", "iss"]},
            )
            if payload.get("typ") != "access":
                raise AuthenticationError("Token inválido.")
            return AccessClaims(user_id=UUID(payload["sub"]), session_id=UUID(payload["sid"]))
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationError("El token expiró.", code="token_expired") from exc
        except (jwt.PyJWTError, ValueError) as exc:
            raise AuthenticationError("Token inválido.") from exc

    def new_refresh_token(self) -> str:
        return secrets.token_urlsafe(48)

    def hash_refresh_token(self, token: str) -> str:
        # El refresh token es aleatorio de alta entropía: SHA-256 basta (no es una contraseña).
        return hashlib.sha256(token.encode()).hexdigest()
