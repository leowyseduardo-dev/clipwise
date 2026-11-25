"""Hosted control plane. Desktop SQLite databases are never opened here."""

from __future__ import annotations
import hashlib
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError

PLANS = {
    "Starter": (20, 1, 1),
    "Creator": (120, 2, 3),
    "Studio": (400, 5, 8),
}
VALID_PLANS = tuple(PLANS)
FREE_DAILY_CLIPS = 2


def normalize_plan(name: str | None) -> str:
    """Old databases defaulted new teams to 'Free'; map anything stale to Starter."""
    return name if name in PLANS else "Starter"
ph = PasswordHasher()
dummy = ph.hash(secrets.token_urlsafe(32))
SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,name TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS teams(id TEXT PRIMARY KEY,name TEXT NOT NULL,plan TEXT NOT NULL DEFAULT 'Starter',customer TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS members(user_id TEXT REFERENCES users,team_id TEXT REFERENCES teams,role TEXT NOT NULL,PRIMARY KEY(user_id,team_id));
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT REFERENCES users,team_id TEXT REFERENCES teams,expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS charges(id TEXT PRIMARY KEY,team_id TEXT REFERENCES teams,actor TEXT REFERENCES users,period TEXT NOT NULL,units INTEGER NOT NULL,created INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS usage_period ON charges(team_id,period);
CREATE TABLE IF NOT EXISTS admissions(id TEXT PRIMARY KEY,team TEXT NOT NULL,stamp INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS charge_resources(charge TEXT PRIMARY KEY REFERENCES charges ON DELETE CASCADE,resource TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS throttle(bucket TEXT PRIMARY KEY,stamp INTEGER NOT NULL,hits INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS password_resets(token TEXT PRIMARY KEY,user_id TEXT REFERENCES users,expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS subscriptions(id TEXT PRIMARY KEY,team_id TEXT NOT NULL,plan TEXT NOT NULL,plan_id TEXT NOT NULL,status TEXT NOT NULL,renews_at TEXT,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS subscriptions_team ON subscriptions(team_id, updated_at DESC);
"""


def home():
    raw = os.environ.get("CLIPFORGE_CLOUD_DIR")
    if not raw:
        raise RuntimeError("Define CLIPFORGE_CLOUD_DIR para el servidor multiusuario.")
    return Path(raw).resolve()


@contextmanager
def connection():
    conn = sqlite3.connect(home() / "accounts.sqlite3", timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init():
    home().mkdir(parents=True, exist_ok=True)
    with connection() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        if "name" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN name TEXT NOT NULL DEFAULT ''")
        # Legacy databases used "Free"; the public tier is now called Starter.
        conn.execute("UPDATE teams SET plan='Starter' WHERE plan NOT IN (?,?,?)", VALID_PLANS)


def digest(s):
    return hashlib.sha256(s.encode()).hexdigest()


def rate_limit(key, limit):
    now = int(time.time())
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM throttle WHERE stamp < ?", (now - 900,))
        row = conn.execute(
            "SELECT hits FROM throttle WHERE bucket=?", (digest(key),)
        ).fetchone()
        if row and row[0] >= limit:
            raise HTTPException(429, "Demasiados intentos. Inténtalo más tarde.")
        conn.execute(
            "INSERT INTO throttle VALUES (?,?,1) ON CONFLICT(bucket) DO UPDATE SET hits=hits+1",
            (digest(key), now),
        )


def account(email, password, register, name=""):
    email = email.strip().lower()
    name = (name or "").strip()[:80]
    with connection() as conn:
        if register:
            uid, team = uuid4().hex, uuid4().hex
            try:
                conn.execute(
                    "INSERT INTO users(id,email,password,name) VALUES (?,?,?,?)",
                    (uid, email, ph.hash(password), name),
                )
            except sqlite3.IntegrityError:
                raise HTTPException(409, "No se pudo registrar esta cuenta.")
            conn.execute(
                "INSERT INTO teams(id,name,plan) VALUES (?,?,'Starter')",
                (team, name or email.split("@")[0][:80]),
            )
            conn.execute("INSERT INTO members VALUES (?,?,'owner')", (uid, team))
        else:
            row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            try:
                ph.verify(row["password"] if row else dummy, password)
            except (VerifyMismatchError, InvalidHashError):
                raise HTTPException(401, "Correo o contraseña incorrectos.")
            if not row:
                raise HTTPException(401, "Correo o contraseña incorrectos.")
            uid = row["id"]
            team = conn.execute(
                "SELECT team_id FROM members WHERE user_id=? ORDER BY role='owner' DESC,team_id LIMIT 1",
                (uid,),
            ).fetchone()[0]
        token = secrets.token_urlsafe(48)
        now = int(time.time())
        conn.execute("DELETE FROM sessions WHERE expires<?", (now,))
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?,?)",
            (digest(token), uid, team, now + 7 * 86400),
        )
        return token


def request_reset(email):
    email = email.strip().lower()
    with connection() as conn:
        row = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if not row:
            return None
        now = int(time.time())
        token = secrets.token_urlsafe(32)
        conn.execute(
            "DELETE FROM password_resets WHERE user_id=? OR expires<?", (row["id"], now)
        )
        conn.execute(
            "INSERT INTO password_resets(token,user_id,expires) VALUES (?,?,?)",
            (digest(token), row["id"], now + 3600),
        )
        return token


def reset_password(token, password):
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT user_id FROM password_resets WHERE token=? AND expires>?",
            (digest(token), int(time.time())),
        ).fetchone()
        if not row:
            raise HTTPException(400, "El enlace no es válido o ha caducado.")
        conn.execute(
            "UPDATE users SET password=? WHERE id=?",
            (ph.hash(password), row["user_id"]),
        )
        conn.execute("DELETE FROM sessions WHERE user_id=?", (row["user_id"],))
        conn.execute("DELETE FROM password_resets WHERE user_id=?", (row["user_id"],))


def drop_reset(token):
    with connection() as conn:
        conn.execute("DELETE FROM password_resets WHERE token=?", (digest(token),))


def principal(token):
    if not token:
        raise HTTPException(401, "Inicia sesión.")
    with connection() as conn:
        row = conn.execute(
            """SELECT u.id AS user,u.email,u.name AS name,s.team_id AS team,m.role,t.name,t.plan,t.customer
          FROM sessions s JOIN users u ON u.id=s.user_id JOIN teams t ON t.id=s.team_id
          JOIN members m ON m.team_id=s.team_id AND m.user_id=s.user_id
          WHERE s.token=? AND s.expires>?""",
            (digest(token), int(time.time())),
        ).fetchone()
    if not row:
        raise HTTPException(401, "La sesión ha caducado.")
    identity = dict(row)
    if identity["plan"] not in PLANS:
        with connection() as conn:
            conn.execute(
                "UPDATE teams SET plan='Starter' WHERE id=? AND plan NOT IN (?,?,?)",
                (identity["team"], *VALID_PLANS),
            )
        identity["plan"] = "Starter"
    if identity["role"] != "owner":
        with connection() as conn:
            seats = conn.execute(
                "SELECT user_id FROM members WHERE team_id=? ORDER BY role='owner' DESC,rowid LIMIT ?",
                (identity["team"], PLANS[identity["plan"]][1]),
            ).fetchall()
        if identity["user"] not in {r[0] for r in seats}:
            raise HTTPException(
                403, "El plan actual no incluye tu plaza en este equipo."
            )
    return identity


def set_plan(team, plan):
    if plan not in PLANS:
        raise ValueError(f"Plan desconocido: {plan}")
    with connection() as conn:
        conn.execute("UPDATE teams SET plan=? WHERE id=?", (plan, team))


def save_subscription(subscription_id, team, plan, plan_id, status, renews_at):
    now = int(time.time())
    with connection() as conn:
        conn.execute(
            """INSERT INTO subscriptions(id,team_id,plan,plan_id,status,renews_at,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 team_id=excluded.team_id,
                 plan=excluded.plan,
                 plan_id=excluded.plan_id,
                 status=excluded.status,
                 renews_at=excluded.renews_at,
                 updated_at=excluded.updated_at""",
            (subscription_id, team, plan, plan_id, status, renews_at, now, now),
        )


def update_subscription(subscription_id, status, renews_at=None):
    with connection() as conn:
        if renews_at is None:
            conn.execute(
                "UPDATE subscriptions SET status=?, updated_at=? WHERE id=?",
                (status, int(time.time()), subscription_id),
            )
        else:
            conn.execute(
                "UPDATE subscriptions SET status=?, renews_at=?, updated_at=? WHERE id=?",
                (status, renews_at, int(time.time()), subscription_id),
            )


def subscription(team):
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM subscriptions WHERE team_id=? ORDER BY updated_at DESC, rowid DESC LIMIT 1",
            (team,),
        ).fetchone()
    return dict(row) if row else None


def subscription_by_id(subscription_id):
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM subscriptions WHERE id=?", (subscription_id,)
        ).fetchone()
    return dict(row) if row else None


def period():
    return datetime.now(timezone.utc).strftime("%Y-%m")


def day_period():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def reserve(identity, units, *, new_job=False):
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        plan = conn.execute(
            "SELECT plan FROM teams WHERE id=?", (identity["team"],)
        ).fetchone()[0]
        if plan not in PLANS:
            plan = "Starter"
            conn.execute(
                "UPDATE teams SET plan='Starter' WHERE id=?", (identity["team"],)
            )
        if plan == "Starter":
            day_start = int(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
            used_day = conn.execute(
                "SELECT coalesce(sum(units),0) FROM charges WHERE team_id=? AND created>=?",
                (identity["team"], day_start),
            ).fetchone()[0]
            if used_day + units > FREE_DAILY_CLIPS:
                raise HTTPException(402, "Has alcanzado el límite diario de clips del plan Starter.")
        used = conn.execute(
            "SELECT coalesce(sum(units),0) FROM charges WHERE team_id=? AND period=?",
            (identity["team"], period()),
        ).fetchone()[0]
        if used + units > PLANS[plan][0]:
            raise HTTPException(402, "El equipo agotó los créditos del mes.")
        charge = uuid4().hex
        if new_job:
            now = int(time.time())
            conn.execute("DELETE FROM admissions WHERE stamp<?", (now - 1800,))
            inflight = conn.execute(
                "SELECT count(*) FROM admissions WHERE team=?", (identity["team"],)
            ).fetchone()[0]
            workspace_db = home() / "workspaces" / identity["team"] / "Clipwise.db"
            if workspace_db.is_file():
                from contextlib import closing

                with closing(sqlite3.connect(workspace_db, timeout=5)) as worker:
                    inflight += worker.execute(
                        "SELECT count(*) FROM jobs WHERE status IN ('queued','processing')"
                    ).fetchone()[0]
            if inflight >= PLANS[plan][2]:
                raise HTTPException(
                    429, "Tu plan alcanzó el máximo de proyectos simultáneos."
                )
            conn.execute(
                "INSERT INTO admissions VALUES(?,?,?)", (charge, identity["team"], now)
            )
        conn.execute(
            "INSERT INTO charges VALUES (?,?,?,?,?,?)",
            (
                charge,
                identity["team"],
                identity["user"],
                period(),
                units,
                int(time.time()),
            ),
        )
    return charge


def refund(charge):
    with connection() as conn:
        conn.execute("DELETE FROM admissions WHERE id=?", (charge,))
        conn.execute("DELETE FROM charges WHERE id=?", (charge,))


def accepted(charge, resource):
    with connection() as conn:
        conn.execute("DELETE FROM admissions WHERE id=?", (charge,))
        if resource:
            conn.execute(
                "INSERT OR IGNORE INTO charge_resources VALUES(?,?)", (charge, resource)
            )
