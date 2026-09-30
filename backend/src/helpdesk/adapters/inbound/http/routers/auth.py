from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status
from fastapi.responses import JSONResponse

from helpdesk.adapters.inbound.http.deps import (
    ActivePrincipal,
    ContainerDep,
    Ctx,
    CurrentPrincipal,
    SettingsDep,
    TabIdHeader,
    require_csrf_header,
)
from helpdesk.adapters.inbound.http.errors import error_response
from helpdesk.adapters.inbound.http.routers._shared import ERRORS, me_out
from helpdesk.adapters.inbound.http.schemas import (
    ChangePasswordIn,
    LoginIn,
    MeOut,
    TabStatusOut,
    TokenOut,
)
from helpdesk.application.use_cases.auth import AuthResult
from helpdesk.config import Settings
from helpdesk.domain.errors import AuthenticationError

router = APIRouter(prefix="/auth", tags=["auth"], responses=ERRORS)

REFRESH_COOKIE = "hd_refresh"
COOKIE_PATH = "/api/v1/auth"
RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE)]


def _set_refresh_cookie(response: Response, result: AuthResult, settings: Settings) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        result.refresh_token,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        path=COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def _token_out(result: AuthResult) -> TokenOut:
    return TokenOut(
        access_token=result.access.token,
        expires_in=result.access.expires_in,
        user=me_out(result.user),
    )


@router.post("/login", response_model=TokenOut, summary="Iniciar sesión")
async def login(
    body: LoginIn, response: Response, c: ContainerDep, settings: SettingsDep, ctx: Ctx
) -> TokenOut:
    result = await c.login.execute(body.email, body.password, ctx)
    _set_refresh_cookie(response, result, settings)
    response.headers["Cache-Control"] = "no-store"
    return _token_out(result)


@router.post(
    "/refresh",
    response_model=TokenOut,
    summary="Rotar refresh token y obtener un nuevo access token",
    dependencies=[Depends(require_csrf_header)],
)
async def refresh(
    response: Response,
    c: ContainerDep,
    settings: SettingsDep,
    ctx: Ctx,
    refresh_token: RefreshCookie = None,
) -> TokenOut | JSONResponse:
    try:
        if not refresh_token:
            raise AuthenticationError("No hay sesión activa.", code="no_session")
        result = await c.refresh.execute(refresh_token, ctx)
    except AuthenticationError as exc:
        failed = error_response(status.HTTP_401_UNAUTHORIZED, exc.code, exc.message)
        failed.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
        return failed
    _set_refresh_cookie(response, result, settings)
    response.headers["Cache-Control"] = "no-store"
    return _token_out(result)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cerrar sesión (revoca la familia de refresh tokens)",
    dependencies=[Depends(require_csrf_header)],
)
async def logout(
    c: ContainerDep, ctx: Ctx, tab_id: TabIdHeader = None, refresh_token: RefreshCookie = None
) -> Response:
    await c.logout.execute(refresh_token, tab_id, ctx)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
    return response


@router.get("/me", response_model=MeOut, summary="Usuario actual")
async def me(principal: CurrentPrincipal) -> MeOut:
    return me_out(principal.user)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT, summary="Cambiar mi contraseña")
async def change_password(
    body: ChangePasswordIn, principal: ActivePrincipal, c: ContainerDep, ctx: Ctx
) -> None:
    await c.change_password.execute(principal, body.current_password, body.new_password, ctx)


# --- pestaña única ------------------------------------------------------------------------------
@router.post(
    "/tab-lease",
    response_model=TabStatusOut,
    summary="Reclamar/renovar la pestaña activa (heartbeat)",
)
async def claim_tab(
    principal: CurrentPrincipal, c: ContainerDep, tab_id: TabIdHeader = None
) -> TabStatusOut:
    return TabStatusOut.model_validate(await c.claim_tab.execute(principal, tab_id))


@router.post(
    "/tab-lease/takeover",
    response_model=TabStatusOut,
    summary='"Usar aquí": mover la sesión a esta pestaña',
)
async def takeover_tab(
    principal: CurrentPrincipal, c: ContainerDep, ctx: Ctx, tab_id: TabIdHeader = None
) -> TabStatusOut:
    return TabStatusOut.model_validate(await c.takeover_tab.execute(principal, tab_id, ctx))


@router.post(
    "/tab-lease/release",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Liberar la pestaña (al cerrarla)",
)
async def release_tab(
    principal: CurrentPrincipal, c: ContainerDep, tab_id: TabIdHeader = None
) -> None:
    await c.release_tab.execute(principal, tab_id)
