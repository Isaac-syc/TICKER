from typing import Any

from fastapi.responses import StreamingResponse

from helpdesk.adapters.inbound.http.deps import Container
from helpdesk.adapters.inbound.http.schemas import ErrorOut, MeOut, PageOut, RoleRef
from helpdesk.adapters.outbound.csv_export import csv_filename, stream_csv
from helpdesk.application.dto import Page, TabularExport
from helpdesk.domain.identity.entities import User

ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorOut, "description": "No autenticado"},
    403: {"model": ErrorOut, "description": "Sin permiso"},
    409: {"model": ErrorOut, "description": "Conflicto (incluye TAB_CONFLICT)"},
    422: {"model": ErrorOut, "description": "Datos inválidos"},
}
CSV_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {"content": {"text/csv": {}}, "description": "Archivo CSV (UTF-8 con BOM)"}
}


def me_out(user: User) -> MeOut:
    return MeOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=RoleRef(
            id=user.role.id, name=user.role.name, single_tab_session=user.role.single_tab_session
        ),
        permissions=sorted(user.permissions),
        last_login_at=user.last_login_at,
    )


def page_out[T](page: Page[Any], item: type[T]) -> PageOut[T]:
    return PageOut[item](  # type: ignore[valid-type]
        items=[item.model_validate(i) for i in page.items],  # type: ignore[attr-defined]
        total=page.total,
        page=page.page,
        page_size=page.page_size,
        pages=page.pages,
    )


def csv_response(export: TabularExport, c: Container) -> StreamingResponse:
    filename = csv_filename(export, c.clock.now(), c.tz)
    return StreamingResponse(
        stream_csv(export, c.tz),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
