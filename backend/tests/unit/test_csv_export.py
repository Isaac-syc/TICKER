from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from helpdesk.adapters.outbound.csv_export import BOM, csv_filename, sanitize_cell, stream_csv
from helpdesk.application.dto import Cell, TabularExport

TZ = ZoneInfo("America/Mexico_City")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('=HYPERLINK("http://x")', '\'=HYPERLINK("http://x")'),
        ("+52 55", "'+52 55"),
        ("-1+1", "'-1+1"),
        ("@SUM(A1)", "'@SUM(A1)"),
        ("Normal", "Normal"),
        (None, ""),
        (True, "Sí"),
        (datetime(2026, 9, 1, 18, 30, tzinfo=UTC), "2026-09-01 12:30"),
    ],
)
def test_sanitize_cell(value: Cell, expected: str) -> None:
    assert sanitize_cell(value, TZ) == expected


async def test_stream_csv_has_bom_headers_and_quotes() -> None:
    async def rows() -> AsyncIterator[Sequence[Cell]]:
        yield ("TCK-000001", "Impresora, piso 2", "Árbol")

    export = TabularExport("tickets", ("Código", "Título", "Categoría"), rows())
    chunks = [c async for c in stream_csv(export, TZ)]
    assert chunks[0].startswith(BOM + "Código,Título,Categoría")
    assert chunks[1] == 'TCK-000001,"Impresora, piso 2",Árbol\r\n'
    assert csv_filename(export, datetime(2026, 9, 1, 18, 0, tzinfo=UTC), TZ) == (
        "tickets_20260901_1200.csv"
    )
