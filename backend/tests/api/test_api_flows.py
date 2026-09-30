import httpx
import pytest

from tests.api.conftest import login

pytestmark = pytest.mark.db

API = "/api/v1"


async def first_category(s: object) -> int:
    r = await s.get(f"{API}/catalog/categories")  # type: ignore[attr-defined]
    assert r.status_code == 200
    return int(r.json()[0]["id"])


async def test_health(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/health/ready")
    assert r.status_code == 200
    assert r.json()["checks"] == {"database": "ok", "redis": "ok"}
    assert r.headers["x-request-id"]


async def test_login_errors_are_generic_and_logged(client: httpx.AsyncClient) -> None:
    r = await client.post(f"{API}/auth/login", json={"email": "nadie@x.mx", "password": "x"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "authentication_failed"

    admin = await login(client, "admin")
    logs = await admin.get(f"{API}/logs/logins", params={"success": "false"})
    assert logs.status_code == 200
    assert any(e["email"] == "nadie@x.mx" for e in logs.json()["items"])


async def test_protected_endpoints_require_token(client: httpx.AsyncClient) -> None:
    r = await client.get(f"{API}/tickets")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "not_authenticated"


async def test_refresh_rotation_with_cookie_and_csrf(client: httpx.AsyncClient) -> None:
    await login(client, "user")
    no_csrf = await client.post(f"{API}/auth/refresh")
    assert no_csrf.status_code == 403
    r = await client.post(f"{API}/auth/refresh", headers={"X-Requested-With": "helpdesk"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == "usuario@helpdesk.test"

    out = await client.post(f"{API}/auth/logout", headers={"X-Requested-With": "helpdesk"})
    assert out.status_code == 204
    again = await client.post(f"{API}/auth/refresh", headers={"X-Requested-With": "helpdesk"})
    assert again.status_code == 401


async def test_ticket_lifecycle(client: httpx.AsyncClient) -> None:
    user = await login(client, "user")
    admin = await login(client, "admin")
    category = await first_category(user)

    created = await user.post(
        f"{API}/tickets",
        json={
            "title": "VPN se desconecta",
            "description": "Cada 10 minutos se cae la VPN en casa.",
            "category_id": category,
            "priority": "HIGH",
        },
    )
    assert created.status_code == 201, created.text
    ticket_id = created.json()["id"]
    assert created.json()["code"].startswith("TCK-")

    detail = (await user.get(f"{API}/tickets/{ticket_id}")).json()
    assert detail["allowed_transitions"] == ["CANCELLED"]
    assert detail["can_assign"] is False

    assignees = (await admin.get(f"{API}/catalog/assignees")).json()
    user_id = user.me["id"]
    assert any(a["id"] == user_id for a in assignees)
    r = await admin.post(f"{API}/tickets/{ticket_id}/assign", json={"assignee_id": user_id})
    assert r.status_code == 200, r.text

    r = await user.post(f"{API}/tickets/{ticket_id}/transitions", json={"status": "IN_PROGRESS"})
    assert r.status_code == 200, r.text
    r = await user.post(f"{API}/tickets/{ticket_id}/transitions", json={"status": "RESOLVED"})
    assert r.status_code == 422  # requiere comentario
    r = await user.post(
        f"{API}/tickets/{ticket_id}/transitions",
        json={"status": "RESOLVED", "comment": "Se actualizó el cliente VPN"},
    )
    assert r.status_code == 200
    r = await user.post(f"{API}/tickets/{ticket_id}/transitions", json={"status": "CLOSED"})
    body = r.json()
    assert body["ticket"]["status"] == "CLOSED"
    types = [e["type"] for e in body["events"]]
    assert types == ["CREATED", "ASSIGNED", "STATUS_CHANGED", "STATUS_CHANGED", "STATUS_CHANGED"]

    r = await user.post(f"{API}/tickets/{ticket_id}/transitions", json={"status": "OPEN"})
    assert r.status_code == 409

    listed = await user.get(f"{API}/tickets", params={"search": "VPN", "status": ["CLOSED"]})
    assert listed.json()["total"] >= 1


async def test_observer_is_read_only_and_single_tab(client: httpx.AsyncClient) -> None:
    obs = await login(client, "observer")
    assert obs.me["role"]["single_tab_session"] is True  # type: ignore[index]

    r = await obs.get(f"{API}/tickets")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "tab_conflict"

    obs.tab_id = "tab-primera-0001"
    claim = await obs.post(f"{API}/auth/tab-lease")
    assert claim.json() == {"required": True, "granted": True, "other_device": False}
    assert (await obs.get(f"{API}/tickets")).status_code == 200

    create = await obs.post(
        f"{API}/tickets",
        json={"title": "No debería", "description": "El observador no crea", "category_id": 1},
    )
    assert create.status_code == 403

    # segunda pestaña: bloqueada hasta que haga "Usar aquí"
    second = await login(client, "observer")
    second.tab_id = "tab-segunda-0002"
    blocked = await second.post(f"{API}/auth/tab-lease")
    assert blocked.json()["granted"] is False
    assert blocked.json()["other_device"] is True
    assert (await second.get(f"{API}/tickets")).status_code == 409

    taken = await second.post(f"{API}/auth/tab-lease/takeover")
    assert taken.json()["granted"] is True
    assert (await second.get(f"{API}/tickets")).status_code == 200
    # la primera quedó fuera (y su sesión de otro "dispositivo" fue revocada)
    assert (await obs.get(f"{API}/tickets")).status_code in (401, 409)

    await second.post(f"{API}/auth/tab-lease/release")


async def test_csv_export_and_dashboard(client: httpx.AsyncClient) -> None:
    admin = await login(client, "admin")
    r = await admin.get(f"{API}/tickets/export.csv", params={"priority": ["HIGH"]})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.content.startswith("﻿".encode())
    lines = r.content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("Código,Título,Estatus")
    assert len(lines) > 1

    dash = await admin.get(f"{API}/dashboard")
    assert dash.status_code == 200
    data = dash.json()
    assert data["scope"] == "all"
    assert data["kpis"]["total"] >= 200
    assert len(data["trend"]) == 30
    assert {x["key"] for x in data["by_status"]} >= {"OPEN", "CLOSED"}

    user = await login(client, "user")
    own = (await user.get(f"{API}/dashboard")).json()
    assert own["scope"] == "own"
    assert own["kpis"]["total"] < data["kpis"]["total"]


async def test_admin_manages_users_and_roles(client: httpx.AsyncClient) -> None:
    admin = await login(client, "admin")
    perms = (await admin.get(f"{API}/roles/permissions")).json()
    assert {"code": "tickets:create", "group": "Tickets", "description": "Crear tickets"} in perms

    role = await admin.post(
        f"{API}/roles",
        json={
            "name": "tecnico",
            "description": "Atiende tickets",
            "permissions": ["tickets:read_all", "tickets:work", "tickets:comment"],
        },
    )
    assert role.status_code == 201, role.text
    role_id = role.json()["id"]

    created = await admin.post(
        f"{API}/users",
        json={
            "email": "tecnico@helpdesk.test",
            "full_name": "Tomás Técnico",
            "role_id": role_id,
            "password": "Tecnico#2026!",
        },
    )
    assert created.status_code == 201, created.text
    tech_id = created.json()["id"]

    tech = await login(client, "tecnico@helpdesk.test", "Tecnico#2026!")
    assert set(tech.me["permissions"]) == {"tickets:read_all", "tickets:work", "tickets:comment"}  # type: ignore[arg-type]
    assert (await tech.get(f"{API}/tickets")).status_code == 200
    assert (await tech.get(f"{API}/users")).status_code == 403

    # no se puede borrar un rol con usuarios
    assert (await admin.delete(f"{API}/roles/{role_id}")).status_code == 409

    off = await admin.patch(f"{API}/users/{tech_id}", json={"is_active": False})
    assert off.json()["is_active"] is False
    assert (await tech.get(f"{API}/tickets")).status_code == 401

    audit = (await admin.get(f"{API}/logs/audit", params={"action": "role.created"})).json()
    assert audit["items"][0]["metadata"]["name"] == "tecnico"

    users_csv = await admin.get(f"{API}/users/export.csv")
    assert "tecnico@helpdesk.test" in users_csv.content.decode("utf-8-sig")
