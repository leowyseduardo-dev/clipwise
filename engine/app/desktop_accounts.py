"""Local account layer for the Windows/portable Clipwise build.

The desktop app keeps its FFmpeg/Whisper engine local, but reuses the hosted
account schema so the login, plan, team and admin panels are the same code that
runs on the public site. Credentials are stored as Argon2 hashes in the local
data directory; no PayPal secret is bundled into the portable app.
"""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from . import db

_DATA_ROOT = Path(
    os.getenv("DATA_DIR")
    or os.getenv("CLIPFORGE_CLOUD_DIR")
    or (Path(__file__).resolve().parents[2] / "engine" / "data")
)
os.environ.setdefault("CLIPFORGE_CLOUD_DIR", str(_DATA_ROOT / "accounts"))

from cloud import accounts  # noqa: E402

OWNER_EMAIL = "LeowysGarcia@gmail.com"
OWNER_PASSWORD = "Leowys123"
OWNER_NAME = "Leowys"
COOKIE = "cf_session"
AUTO_COOKIE = "cf_autologin"
SESSION_MAX_AGE = 7 * 86400


def init() -> None:
    """Create the local account DB and make sure the owner account exists."""
    accounts.init()
    email = OWNER_EMAIL.strip().lower()
    with accounts.connection() as conn:
        row = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
    if row:
        return
    accounts.account(OWNER_EMAIL, OWNER_PASSWORD, True, OWNER_NAME)
    with accounts.connection() as conn:
        uid = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()[0]
        conn.execute(
            "UPDATE teams SET plan='Studio' WHERE id IN "
            "(SELECT team_id FROM members WHERE user_id=? AND role='owner')",
            (uid,),
        )


def _admin_emails() -> set[str]:
    return {
        item.strip().lower()
        for item in os.getenv("ADMIN_EMAILS", "").split(",")
        if item.strip()
    } | {OWNER_EMAIL.strip().lower()}


def is_admin(identity: dict[str, Any]) -> bool:
    return str(identity.get("email") or "").strip().lower() in _admin_emails()


def require_admin(identity: dict[str, Any]) -> None:
    if not is_admin(identity):
        raise HTTPException(403, "Solo el administrador puede hacer eso.")


def principal(request: Request) -> dict[str, Any]:
    return accounts.principal(request.cookies.get(COOKIE))


async def payload(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception as exc:
        raise HTTPException(400, "Cuerpo JSON inválido.") from exc
    if not isinstance(data, dict):
        raise HTTPException(400, "Cuerpo JSON inválido.")
    return data


def should_auto_login(request: Request) -> bool:
    return (
        not request.cookies.get(COOKIE)
        and request.cookies.get(AUTO_COOKIE) != "0"
        and os.getenv("CLIPFORGE_DESKTOP_AUTOLOGIN", "1") != "0"
    )


def auto_login() -> str:
    return accounts.account(OWNER_EMAIL, OWNER_PASSWORD, False)


def set_cookies(response: JSONResponse, token: str) -> JSONResponse:
    response.set_cookie(
        COOKIE, token, httponly=True, samesite="lax", max_age=SESSION_MAX_AGE
    )
    response.set_cookie(AUTO_COOKIE, "1", max_age=SESSION_MAX_AGE)
    return response


def logout_response() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE)
    response.set_cookie(AUTO_COOKIE, "0", max_age=SESSION_MAX_AGE)
    return response


def discard_session(token: str) -> None:
    with accounts.connection() as conn:
        conn.execute(
            "DELETE FROM sessions WHERE token=?", (accounts.digest(token or ""),)
        )


def _local_usage() -> int:
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        with closing(db._connect()) as conn:
            return int(
                conn.execute(
                    "SELECT count(*) FROM clips WHERE substr(created_at,1,7)=?",
                    (period,),
                ).fetchone()[0]
            )
    except sqlite3.Error:
        return 0


def info(identity: dict[str, Any]) -> dict[str, Any]:
    plan = accounts.normalize_plan(identity.get("plan"))
    with accounts.connection() as conn:
        teams = [
            dict(row)
            for row in conn.execute(
                """SELECT t.id, t.name FROM members m JOIN teams t ON t.id=m.team_id
                   WHERE m.user_id=? ORDER BY t.name COLLATE NOCASE, t.id""",
                (identity["user"],),
            )
        ]
        members = [
            dict(row)
            for row in conn.execute(
                """SELECT u.email, m.role FROM members m JOIN users u ON u.id=m.user_id
                   WHERE m.team_id=?""",
                (identity["team"],),
            )
        ]
    return {
        "hosted": False,
        "desktop": True,
        "signed_in": True,
        "email": identity.get("email") or "",
        "name": identity.get("name") or "",
        "team": identity.get("team") or "",
        "role": identity.get("role") or "",
        "plan": plan,
        "used": _local_usage(),
        "limit": accounts.PLANS[plan][0],
        "teams": teams,
        "members": members,
        "plans": accounts.PLANS,
        "billing": False,
        "paypal_me": "",
        "paypal": {
            "configured": False,
            "client_id": "",
            "mode": "live",
            "currency": "USD",
            "plans": {},
        },
        "subscription": accounts.subscription(identity["team"]),
        "admin": is_admin(identity),
    }


def overview() -> dict[str, Any]:
    with accounts.connection() as conn:
        users = conn.execute("SELECT count(*) FROM users").fetchone()[0]
        teams = conn.execute("SELECT count(*) FROM teams").fetchone()[0]
        by_plan = {
            row[0]: row[1]
            for row in conn.execute("SELECT plan, count(*) FROM teams GROUP BY plan")
        }
    return {
        "users": users,
        "teams": teams,
        "by_plan": by_plan,
        "clips_this_month": _local_usage(),
        "plans": accounts.PLANS,
    }


def teams() -> dict[str, Any]:
    used = _local_usage()
    with accounts.connection() as conn:
        rows = conn.execute(
            """
            SELECT t.id, t.name, t.plan,
                   coalesce((
                       SELECT u.email FROM members m JOIN users u ON u.id=m.user_id
                       WHERE m.team_id=t.id AND m.role='owner' LIMIT 1
                   ), '') AS owner,
                   (SELECT count(*) FROM members m WHERE m.team_id=t.id) AS members
            FROM teams t ORDER BY t.name COLLATE NOCASE, t.id
            """
        ).fetchall()
    return {"teams": [{**dict(row), "used": used} for row in rows]}


def set_plan(team: str, plan: str) -> dict[str, Any]:
    if plan not in accounts.PLANS:
        raise HTTPException(422, "Plan desconocido.")
    with accounts.connection() as conn:
        if not conn.execute("SELECT 1 FROM teams WHERE id=?", (team,)).fetchone():
            raise HTTPException(404, "Equipo no encontrado.")
    accounts.set_plan(team, plan)
    with accounts.connection() as conn:
        conn.execute(
            "UPDATE subscriptions SET status='MANUAL', updated_at=? WHERE team_id=?",
            (int(time.time()), team),
        )
    return {"ok": True, "team": team, "plan": plan}


def suspend(email: str) -> dict[str, Any]:
    with accounts.connection() as conn:
        conn.execute(
            "DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE email=?)",
            (email.strip().lower(),),
        )
    return {"ok": True}


def reset_link(email: str, origin: str) -> dict[str, str]:
    token = accounts.request_reset(email)
    if not token:
        raise HTTPException(404, "Cuenta no encontrada.")
    return {"url": origin.rstrip("/") + "/?reset=" + token}


def add_member(identity: dict[str, Any], email: str, role: str) -> dict[str, Any]:
    if identity.get("role") != "owner":
        raise HTTPException(403, "Solo el propietario administra miembros.")
    if role not in {"editor", "viewer"}:
        raise HTTPException(422, "Rol no válido.")
    with accounts.connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        user = conn.execute(
            "SELECT id FROM users WHERE email=?", (email.strip().lower(),)
        ).fetchone()
        if not user or user[0] == identity["user"]:
            raise HTTPException(400, "Introduce otra cuenta registrada.")
        exists = conn.execute(
            "SELECT 1 FROM members WHERE user_id=? AND team_id=?",
            (user[0], identity["team"]),
        ).fetchone()
        count = conn.execute(
            "SELECT COUNT(*) FROM members WHERE team_id=?", (identity["team"],)
        ).fetchone()[0]
        plan = accounts.normalize_plan(identity.get("plan"))
        if not exists and count >= accounts.PLANS[plan][1]:
            raise HTTPException(403, "El equipo alcanzó el límite de miembros de su plan.")
        conn.execute(
            "INSERT INTO members VALUES (?,?,?) "
            "ON CONFLICT(user_id,team_id) DO UPDATE SET role=excluded.role",
            (user[0], identity["team"], role),
        )
    return {"ok": True}


def remove_member(identity: dict[str, Any], email: str) -> dict[str, Any]:
    if identity.get("role") != "owner":
        raise HTTPException(403, "Se requiere permiso de propietario.")
    with accounts.connection() as conn:
        conn.execute(
            "DELETE FROM members WHERE team_id=? AND role!='owner' "
            "AND user_id IN (SELECT id FROM users WHERE email=?)",
            (identity["team"], email.strip().lower()),
        )
    return {"ok": True}


def switch_team(request: Request, team: str) -> dict[str, Any]:
    token = accounts.digest(request.cookies.get(COOKIE, ""))
    with accounts.connection() as conn:
        updated = conn.execute(
            """UPDATE sessions SET team_id=? WHERE token=?
               AND EXISTS(SELECT 1 FROM members WHERE user_id=sessions.user_id AND team_id=?)
               AND expires>?""",
            (team, token, team, int(time.time())),
        )
        if not updated.rowcount:
            raise HTTPException(403, "Equipo inaccesible.")
    return {"ok": True}
