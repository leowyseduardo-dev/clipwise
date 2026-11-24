"""Authenticated public entry point; the desktop app keeps its local behaviour."""

import asyncio
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import accounts, billing, mailer, paypal_billing, seed
from .workers import Engines

# The hosted process shares the engine's .env so one file configures both.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

log = logging.getLogger("uvicorn.error")


def origin():
    raw = os.environ.get("CLIPFORGE_PUBLIC_ORIGIN", "").rstrip("/")
    parts = urlparse(raw)
    if (
        (
            parts.scheme != "https"
            and not (
                parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1"}
            )
        )
        or not parts.hostname
        or parts.path
        or parts.query
        or parts.fragment
        or parts.username
    ):
        raise RuntimeError(
            "Define CLIPFORGE_PUBLIC_ORIGIN como origen HTTPS o loopback."
        )
    return raw


@asynccontextmanager
async def lifespan(app):
    origin()
    accounts.init()
    seed.admin()
    app.state.engines = Engines()
    app.state.http = httpx.AsyncClient(
        timeout=httpx.Timeout(180, connect=8), trust_env=False
    )
    try:
        await asyncio.to_thread(paypal_billing.bootstrap)
    except Exception as exc:  # PayPal outages must not stop the engine.
        log.warning("PayPal setup skipped: %s", exc)
    yield
    await app.state.http.aclose()
    await app.state.engines.close()


app = FastAPI(
    title="Clipwise Cloud",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.middleware("http")
async def same_origin(request, call_next):
    if (
        request.method not in {"GET", "HEAD", "OPTIONS"}
        and request.url.path
        not in {"/api/account/webhook", "/api/billing/paypal/webhook"}
    ):
        if request.headers.get("origin") != origin():
            return JSONResponse({"detail": "Origen de solicitud no válido."}, 403)
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


def person(request):
    identity = accounts.principal(request.cookies.get("cf_session"))
    identity["plan"] = paypal_billing.reconcile_team(
        identity["team"], identity["plan"]
    )
    return identity


class Login(BaseModel):
    email: str = Field(
        min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    )
    password: str = Field(min_length=8, max_length=256)


class Register(Login):
    name: str = Field(default="", max_length=80)
    accept_terms: bool = False


class Forgot(BaseModel):
    email: str = Field(
        min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    )


class Reset(BaseModel):
    token: str = Field(min_length=16, max_length=256)
    password: str = Field(min_length=8, max_length=256)


@app.post("/api/account/register")
def register(payload: Register, request: Request):
    return sign_in("register", payload, request, payload.name)


@app.post("/api/account/login")
def login(payload: Login, request: Request):
    return sign_in("login", payload, request)


@app.post("/api/account/forgot")
def forgot(payload: Forgot, request: Request):
    ip = request.client.host if request.client else "unknown"
    accounts.rate_limit("ip:" + ip, 40)
    accounts.rate_limit("forgot:" + payload.email.strip().lower(), 5)
    token = accounts.request_reset(payload.email)
    if token:
        mailer.send_reset(payload.email.strip().lower(), origin() + "/?reset=" + token)
    return {"ok": True}


@app.post("/api/account/reset")
def reset(payload: Reset, request: Request):
    ip = request.client.host if request.client else "unknown"
    accounts.rate_limit("reset:" + ip, 20)
    accounts.reset_password(payload.token, payload.password)
    return {"ok": True}


def sign_in(action: str, payload: Login, request: Request, name: str = ""):
    ip = request.client.host if request.client else "unknown"
    accounts.rate_limit("ip:" + ip, 40)
    accounts.rate_limit(action + ":" + payload.email.strip().lower(), 15)
    token = accounts.account(
        payload.email, payload.password, action == "register", name
    )
    response = JSONResponse({"ok": True})
    response.set_cookie(
        "cf_session",
        token,
        httponly=True,
        secure=origin().startswith("https:"),
        samesite="lax",
        max_age=604800,
    )
    return response


@app.post("/api/account/logout")
def logout(request: Request):
    with accounts.connection() as conn:
        conn.execute(
            "DELETE FROM sessions WHERE token=?",
            (accounts.digest(request.cookies.get("cf_session", "")),),
        )
    response = JSONResponse({"ok": True})
    response.delete_cookie("cf_session")
    return response


@app.get("/api/account")
def info(request: Request):
    if not request.cookies.get("cf_session"):
        return {"hosted": True, "signed_in": False}
    i = person(request)
    with accounts.connection() as conn:
        used = conn.execute(
            "SELECT coalesce(sum(units),0) FROM charges WHERE team_id=? AND period=?",
            (i["team"], accounts.period()),
        ).fetchone()[0]
        teams = [
            dict(r)
            for r in conn.execute(
                "SELECT t.id,t.name FROM members m JOIN teams t ON t.id=m.team_id WHERE m.user_id=?",
                (i["user"],),
            )
        ]
        members = [
            dict(r)
            for r in conn.execute(
                "SELECT u.email,m.role FROM members m JOIN users u ON u.id=m.user_id WHERE m.team_id=?",
                (i["team"],),
            )
        ]
    admin_emails = {
        x.strip().lower()
        for x in os.getenv("ADMIN_EMAILS", "").split(",")
        if x.strip()
    }
    subscription = accounts.subscription(i["team"])
    return {
        "hosted": True,
        "signed_in": True,
        "email": i["email"],
        "name": i.get("name") or "",
        "team": i["team"],
        "role": i["role"],
        "plan": i["plan"],
        "used": used,
        "limit": accounts.PLANS[i["plan"]][0],
        "teams": teams,
        "members": members,
        "plans": accounts.PLANS,
        "billing": bool(
            os.getenv("STRIPE_SECRET_KEY") and os.getenv("STRIPE_WEBHOOK_SECRET")
        ),
        "paypal_me": os.getenv("PAYPAL_ME_URL", "").strip(),
        "paypal": paypal_billing.public_config(),
        "subscription": subscription,
        "admin": i["email"].lower() in admin_emails,
    }


@app.get("/api/public/config")
def public_config():
    return {
        "paypal_me": os.getenv("PAYPAL_ME_URL", "").strip(),
        "paypal": paypal_billing.public_config(),
    }


class Member(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    role: Literal["editor", "viewer"] = "editor"


@app.put("/api/account/member")
def member(payload: Member, request: Request):
    i = person(request)
    if i["role"] != "owner":
        raise HTTPException(403, "Solo el propietario administra miembros.")
    with accounts.connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        user = conn.execute(
            "SELECT id FROM users WHERE email=?", (payload.email.lower().strip(),)
        ).fetchone()
        if not user or user[0] == i["user"]:
            raise HTTPException(400, "Introduce otra cuenta registrada.")
        exists = conn.execute(
            "SELECT 1 FROM members WHERE user_id=? AND team_id=?", (user[0], i["team"])
        ).fetchone()
        count = conn.execute(
            "SELECT COUNT(*) FROM members WHERE team_id=?", (i["team"],)
        ).fetchone()[0]
        if not exists and count >= accounts.PLANS[i["plan"]][1]:
            raise HTTPException(
                403, "El equipo alcanzó el límite de miembros de su plan."
            )
        conn.execute(
            "INSERT INTO members VALUES (?,?,?) ON CONFLICT(user_id,team_id) DO UPDATE SET role=excluded.role",
            (user[0], i["team"], payload.role),
        )
    return {"ok": True}


@app.delete("/api/account/member")
def remove_member(email: str, request: Request):
    i = person(request)
    if i["role"] != "owner":
        raise HTTPException(403, "Se requiere permiso de propietario.")
    with accounts.connection() as conn:
        conn.execute(
            "DELETE FROM members WHERE team_id=? AND role!='owner' AND user_id IN (SELECT id FROM users WHERE email=?)",
            (i["team"], email.strip().lower()),
        )
    return {"ok": True}


@app.put("/api/account/team/{team}")
def switch(team: str, request: Request):
    token = accounts.digest(request.cookies.get("cf_session", ""))
    with accounts.connection() as conn:
        updated = conn.execute(
            "UPDATE sessions SET team_id=? WHERE token=? AND EXISTS(SELECT 1 FROM members WHERE user_id=sessions.user_id AND team_id=?) AND expires>unixepoch()",
            (team, token, team),
        )
        if not updated.rowcount:
            raise HTTPException(403, "Equipo inaccesible.")
    return {"ok": True}


@app.post("/api/account/billing/{plan}")
def pay(plan: Literal["Creator", "Studio", "portal"], request: Request):
    i = person(request)
    manual = os.getenv("PAYPAL_ME_URL", "").strip()
    stripe = os.getenv("STRIPE_SECRET_KEY") and os.getenv("STRIPE_WEBHOOK_SECRET")
    if manual and not stripe:
        raise HTTPException(
            409,
            "El pago con PayPal es automático. Suscríbete desde Mi cuenta → Plan.",
        )
    return {"url": billing.checkout(i, plan, origin())}


@app.post("/api/account/webhook")
async def webhook(request: Request):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 1024 * 1024:
            raise HTTPException(413, "Evento demasiado grande.")
    await asyncio.to_thread(
        billing.event, bytes(data), request.headers.get("stripe-signature", "")
    )
    return {"received": True}


class PayPalActivate(BaseModel):
    subscription_id: str = Field(min_length=3, max_length=128)


@app.post("/api/billing/paypal/activate")
def paypal_activate(payload: PayPalActivate, request: Request):
    return paypal_billing.activate(person(request), payload.subscription_id)


@app.post("/api/billing/paypal/cancel")
def paypal_cancel(request: Request):
    return paypal_billing.cancel(person(request))


@app.post("/api/billing/paypal/webhook")
async def paypal_webhook(request: Request):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 1024 * 1024:
            raise HTTPException(413, "Evento demasiado grande.")
    return await asyncio.to_thread(
        paypal_billing.webhook, bytes(data), request.headers
    )


def _admin(request):
    i = person(request)
    admin_emails = {
        x.strip().lower()
        for x in os.getenv("ADMIN_EMAILS", "").split(",")
        if x.strip()
    }
    if i["email"].lower() not in admin_emails:
        raise HTTPException(403, "Acceso de administrador requerido.")
    return i


@app.post("/api/admin/paypal/setup")
def admin_paypal_setup(request: Request):
    _admin(request)
    return paypal_billing.bootstrap()


@app.get("/api/admin/overview")
def admin_overview(request: Request):
    _admin(request)
    with accounts.connection() as conn:
        users = conn.execute("SELECT count(*) FROM users").fetchone()[0]
        teams = conn.execute("SELECT count(*) FROM teams").fetchone()[0]
        by_plan = {
            r[0]: r[1]
            for r in conn.execute(
                "SELECT plan, count(*) FROM teams GROUP BY plan"
            ).fetchall()
        }
        used = conn.execute(
            "SELECT coalesce(sum(units),0) FROM charges WHERE period=?",
            (accounts.period(),),
        ).fetchone()[0]
        failed_jobs = 0
    return {
        "users": users,
        "teams": teams,
        "by_plan": by_plan,
        "clips_this_month": used,
        "plans": accounts.PLANS,
    }


@app.get("/api/admin/teams")
def admin_teams(request: Request):
    _admin(request)
    with accounts.connection() as conn:
        rows = conn.execute(
            """
            SELECT t.id, t.name, t.plan,
                   coalesce((
                       SELECT u.email FROM members m JOIN users u ON u.id=m.user_id
                       WHERE m.team_id=t.id AND m.role='owner' LIMIT 1
                   ), '') AS owner,
                   (SELECT count(*) FROM members m WHERE m.team_id=t.id) AS members,
                   coalesce((
                       SELECT sum(units) FROM charges c
                       WHERE c.team_id=t.id AND c.period=?
                   ), 0) AS used
            FROM teams t
            ORDER BY t.name COLLATE NOCASE, t.id
            """,
            (accounts.period(),),
        ).fetchall()
    return {"teams": [dict(row) for row in rows]}


class AdminPlan(BaseModel):
    team: str = Field(min_length=1, max_length=64)
    plan: Literal["Starter", "Creator", "Studio"]


@app.post("/api/admin/plan")
def admin_plan(payload: AdminPlan, request: Request):
    _admin(request)
    with accounts.connection() as conn:
        updated = conn.execute(
            "UPDATE teams SET plan=? WHERE id=?", (payload.plan, payload.team)
        )
        if not updated.rowcount:
            raise HTTPException(404, "Equipo no encontrado.")
        conn.execute(
            "UPDATE subscriptions SET status='MANUAL', updated_at=? WHERE team_id=?",
            (int(time.time()), payload.team),
        )
    return {"ok": True, "team": payload.team, "plan": payload.plan}


@app.post("/api/admin/suspend")
def admin_suspend(email: str, request: Request):
    _admin(request)
    with accounts.connection() as conn:
        conn.execute(
            "DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE email=?)",
            (email.strip().lower(),),
        )
    return {"ok": True}


ID = r"[0-9a-f]{12,64}"
ROUTES = re.compile(
    rf"(?:health|options|publishing/(?:callback|settings|connections|oauth/(?:youtube|tiktok)/(?:start|status|disconnect)|records/{ID})|jobs(?:/{ID}(?:/(?:download\.zip|cancel|retry))?)?|clips/{ID}(?:/(?:publish|description|copy|publication\.txt|edit|video\.mp4|source\.mp4|thumb\.jpg|frame\.jpg|subtitles(?:\.srt)?|render|browser-render))?|studio/(?:logo|dna|presets|calendar(?:/{ID})?|jobs/{ID}(?:/(?:week|duplicate|usage|youtube-stats))?|clips/{ID}/(?:editorial|hooks|strategy|battle|favorite)))"
)
BILLABLE = re.compile(
    r"(?:^jobs$|/(?:retry|battle|hooks|edit|subtitles|render|description)$)"
)


@app.api_route(
    "/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"]
)
async def engine(path: str, request: Request):
    i = person(request)
    if not ROUTES.fullmatch(path):
        raise HTTPException(404, "Esta función no está habilitada en este servidor.")
    write = request.method not in {"HEAD", "GET"}
    if (
        path.startswith("publishing/")
        and (path == "publishing/callback" or write or path.endswith("/status"))
        and i["role"] != "owner"
    ):
        raise HTTPException(403, "Solo el propietario puede conectar cuentas sociales.")
    if path == "publishing/settings" and write:
        raise HTTPException(
            403, "El administrador del servidor configura las credenciales de OAuth."
        )
    if write and i["role"] == "viewer":
        raise HTTPException(403, "Tu acceso al equipo es de lectura.")
    if (
        write
        and i["plan"] == "Starter"
        and (path.endswith("/battle") or path == "studio/presets")
    ):
        raise HTTPException(403, "Esta función requiere el plan Creator o Studio.")
    port = await request.app.state.engines.get(i["team"])
    cap = (
        int(os.getenv("CLIPFORGE_CLOUD_UPLOAD_MB", "512")) * 1048576 + 2 * 1048576
        if path == "jobs" or path.endswith("/browser-render")
        else (3 * 1048576 if path == "studio/logo" else 1024 * 1024)
    )
    length = request.headers.get("content-length", "0")
    if write and (
        "transfer-encoding" in request.headers
        or not length.isdigit()
        or int(length) > cap
    ):
        raise HTTPException(413, "Tamaño de solicitud ausente o superior al límite.")
    local = f"http://127.0.0.1:{port}/api/{path}"
    charge = None
    if write and BILLABLE.search(path):
        charge = accounts.reserve(
            i, 1, new_job=path == "jobs" or path.endswith("/retry")
        )
    headers = {
        k: v
        for k, v in request.headers.items()
        if k in {"content-type", "content-length", "range", "if-range"}
    }
    headers["x-Clipwise-creator"] = i["user"]
    client = request.app.state.http
    try:
        upstream = await client.send(
            client.build_request(
                request.method,
                local,
                params=request.query_params,
                headers=headers,
                content=request.stream() if write else None,
            ),
            stream=True,
        )
    except httpx.HTTPError:
        # The worker may have accepted a job before a transport failure. Keep the
        # receipt for reconciliation rather than silently granting duplicate work.
        raise HTTPException(502, "Se perdió la conexión con el motor.")
    if charge:
        if (
            upstream.status_code >= 400
            or upstream.headers.get("x-Clipwise-reused") == "1"
        ):
            accounts.refund(charge)
        else:
            try:
                payload = json.loads(await upstream.aread())
                resource = payload.get("id") or path
                accounts.accepted(charge, resource)
                return JSONResponse(payload, status_code=upstream.status_code)
            finally:
                await upstream.aclose()

    async def body():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()

    allowed = {
        "content-type",
        "content-disposition",
        "content-range",
        "accept-ranges",
        "content-length",
        "content-encoding",
        "x-clipwise-source-offset",
        "access-control-expose-headers",
    }
    return StreamingResponse(
        body(),
        status_code=upstream.status_code,
        headers={k: v for k, v in upstream.headers.items() if k in allowed},
    )


web = Path(__file__).resolve().parents[2] / "web" / "dist"
if web.is_dir():
    app.mount("/", StaticFiles(directory=web, html=True), name="web")
