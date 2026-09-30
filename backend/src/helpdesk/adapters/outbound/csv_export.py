"""Serializa un TabularExport a CSV en streaming.

- BOM UTF-8 para que Excel abra bien los acentos.
- Neutraliza inyección de fórmulas (CSV injection): celdas que inician con = + - @ tab o CR.
- Fechas en la zona horaria del negocio.
"""

import csv
import io
from collections.abc import AsyncIterator, Sequence
from datetime import date, datetime
from zoneinfo import ZoneInfo

from helpdesk.application.dto import Cell, TabularExport

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
BOM = "﻿"


def sanitize_cell(value: Cell, tz: ZoneInfo) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(tz).strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "Sí" if value else "No"
    text = str(value)
    if text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def _line(values: Sequence[str]) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\r\n").writerow(values)
    return buffer.getvalue()


async def stream_csv(export: TabularExport, tz: ZoneInfo) -> AsyncIterator[str]:
    yield BOM + _line(export.headers)
    async for row in export.rows:
        yield _line([sanitize_cell(v, tz) for v in row])


def csv_filename(export: TabularExport, now: datetime, tz: ZoneInfo) -> str:
    return f"{export.filename_prefix}_{now.astimezone(tz):%Y%m%d_%H%M}.csv"
