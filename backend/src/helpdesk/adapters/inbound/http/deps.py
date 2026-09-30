from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from helpdesk.config import Settings
from helpdesk.domain.audit.entities import RequestContext
from helpdesk.domain.errors import AuthenticationError, PermissionDeniedError
from helpdesk.domain.identity.entities import Principal, User

if TYPE_CHECKING:
    # Solo para tipos: el adaptador no depende en runtime del composition root.
    from helpdesk.container import Container as Container
else:
    Container = Any

_bearer = HTTPBearer(auto_error=False, description="Access token JWT")


def get_container(request: Request) -> Container:
    return request.app.state.container  # type: ignore[no-any-return]


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def request_context(request: Request) -> RequestContext:
    # Nginx fija X-Real-IP; no se confía en X-Forwarded-For arbitrario del cliente.
    ip = request.headers.get("x-real-ip") or (request.client.host if request.client else None)
    return RequestContext(
        ip=ip,
        user_agent=(request.headers.get("user-agent") or "")[:512] or None,
        request_id=getattr(request.state, "request_id", None),
    )


ContainerDep = Annotated[Container, Depends(get_container)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
Ctx = Annotated[RequestContext, Depends(request_context)]
TabIdHeader = Annotated[str | None, Header(alias="X-Tab-Id", max_length=64)]


async def current_principal(
    c: ContainerDep,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    """Usuario autenticado, sin validar la pestaña (para /me, logout y el propio lease)."""
    if creds is None:
        raise AuthenticationError("Autenticación requerida.", code="not_authenticated")
    return await c.authenticate.execute(creds.credentials)


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


async def active_principal(
    principal: CurrentPrincipal, c: ContainerDep, tab_id: TabIdHeader = None
) -> Principal:
    """Usuario autenticado y, si su rol lo exige, operando desde la única pestaña activa."""
    await c.ensure_tab.execute(principal, tab_id)
    return principal


ActivePrincipal = Annotated[Principal, Depends(active_principal)]


async def current_actor(principal: ActivePrincipal) -> User:
    return principal.user


Actor = Annotated[User, Depends(current_actor)]


async def require_csrf_header(
    x_requested_with: Annotated[str | None, Header(alias="X-Requested-With")] = None,
) -> None:
    """Defensa CSRF para endpoints que usan la cookie de refresh: un formulario de otro sitio
    no puede enviar headers personalizados sin pasar por CORS (que no habilitamos)."""
    if x_requested_with != "helpdesk":
        raise PermissionDeniedError("Petición no permitida.")
