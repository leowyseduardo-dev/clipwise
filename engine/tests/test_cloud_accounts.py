from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import time
import pytest

pytest.importorskip("argon2")
from fastapi import HTTPException
from fastapi.testclient import TestClient
from cloud import accounts, billing
from cloud.main import app

ORIGIN = "http://127.0.0.1"


@pytest.fixture
def cloud(monkeypatch, tmp_path):
    monkeypatch.setenv("CLIPFORGE_CLOUD_DIR", str(tmp_path))
    monkeypatch.setenv("CLIPFORGE_PUBLIC_ORIGIN", ORIGIN)
    for key in (
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "PAYPAL_ME_URL",
        "PAYPAL_CLIENT_ID",
        "PAYPAL_CLIENT_SECRET",
        "PAYPAL_MODE",
        "PAYPAL_PRODUCT_ID",
        "PAYPAL_CREATOR_PLAN_ID",
        "PAYPAL_STUDIO_PLAN_ID",
        "PAYPAL_PUBLIC_URL",
        "PAYPAL_WEBHOOK_ID",
        "PAYPAL_WEBHOOK_INSECURE",
        "ADMIN_EMAILS",
    ):
        monkeypatch.delenv(key, raising=False)
    with TestClient(app, base_url=ORIGIN, headers={"origin": ORIGIN}) as c:
        yield c


def register(c, email):
    return c.post(
        "/api/account/register",
        json={
            "email": email,
            "password": "a-unique-test-password",
            "accept_terms": True,
        },
    )


def test_auth_workspace_and_actual_separate_engines(cloud):
    c = cloud
    assert c.get("/api/jobs").status_code == 401
    assert register(c, "a@example.test").is_success
    first = c.get("/api/account").json()["team"]
    assert c.get("/api/jobs").json() == {"jobs": []}
    import sqlite3
    from contextlib import closing

    path = accounts.home() / "workspaces" / first / "Clipwise.db"
    with closing(sqlite3.connect(path)) as con, con:
        con.execute(
            """INSERT INTO jobs(id,created_at,updated_at,source_type,title,status)
             VALUES ('aaaaaaaaaaaaaaaa','now','now','upload','Solo en A','ready')"""
        )
    assert c.get("/api/jobs/aaaaaaaaaaaaaaaa").json()["title"] == "Solo en A"
    assert c.post("/api/account/logout").is_success
    assert register(c, "b@example.test").is_success
    assert c.get("/api/jobs").json()["jobs"] == []
    assert c.get("/api/jobs/aaaaaaaaaaaaaaaa").status_code == 404
    assert c.put("/api/account/team/" + first).status_code == 403
    assert (
        c.put("/api/studio/presets", json={"name": "a", "settings": {}}).status_code
        == 403
    )
    r = c.post("/api/jobs", data={"source_type": "upload"})
    assert r.status_code == 400 and c.get("/api/account").json()["used"] == 0
    assert c.post("/api/account/logout").is_success
    assert c.post(
        "/api/account/login",
        json={"email": "a@example.test", "password": "a-unique-test-password"},
    ).is_success


def test_roles_and_downgrade(cloud):
    c = cloud
    register(c, "viewer@example.test")
    c.post("/api/account/logout")
    register(c, "owner@example.test")
    team = c.get("/api/account").json()["team"]
    payload = {"email": "viewer@example.test", "role": "viewer"}
    assert c.put("/api/account/member", json=payload).status_code == 403
    with accounts.connection() as conn:
        conn.execute("UPDATE teams SET plan='Studio' WHERE id=?", (team,))
    assert c.put("/api/account/member", json=payload).is_success
    c.post("/api/account/logout")
    c.post(
        "/api/account/login",
        json={"email": payload["email"], "password": "a-unique-test-password"},
    )
    assert c.put("/api/account/team/" + team).is_success
    assert c.post("/api/jobs", data={"source_type": "upload"}).status_code == 403
    assert c.get("/api/account").json()["role"] == "viewer"
    assert c.delete("/api/account/member?email=owner@example.test").status_code == 403


def test_concurrent_credit_limit(cloud):
    register(cloud, "credits@example.test")
    identity = accounts.principal(cloud.cookies["cf_session"])

    def claim(_):
        try:
            return accounts.reserve(identity, 1)
        except HTTPException as e:
            return e.status_code

    with ThreadPoolExecutor(6) as pool:
        result = list(pool.map(claim, range(8)))
    assert result.count(402) == 6
    assert cloud.get("/api/account").json()["used"] == 2
    accounts.refund(next(v for v in result if isinstance(v, str)))
    assert cloud.get("/api/account").json()["used"] == 1


def test_signed_subscription_reconciliation_and_cancellation(cloud, monkeypatch):
    register(cloud, "billing@example.test")
    team = cloud.get("/api/account").json()["team"]
    with accounts.connection() as conn:
        conn.execute("UPDATE teams SET customer='cus_test' WHERE id=?", (team,))
    monkeypatch.setenv("STRIPE_PRICE_STUDIO", "test_price")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "test_signing_secret")
    data = {
        "data": [
            {"status": "active", "items": {"data": [{"price": {"id": "test_price"}}]}}
        ]
    }
    monkeypatch.setattr(billing, "api", lambda *args, **kwargs: data)
    body = json.dumps(
        {
            "type": "customer.subscription.updated",
            "data": {"object": {"customer": "cus_test"}},
        }
    ).encode()
    stamp = str(int(time.time()))
    sign = hmac.new(
        b"test_signing_secret", stamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    assert cloud.post("/api/account/webhook", content=body).status_code == 400
    for _ in range(2):
        assert cloud.post(
            "/api/account/webhook",
            content=body,
            headers={"stripe-signature": f"t={stamp},v1={sign}"},
        ).is_success
    assert cloud.get("/api/account").json()["plan"] == "Studio"
    data["data"] = []
    billing.event(body, f"t={stamp},v1={sign}")
    assert cloud.get("/api/account").json()["plan"] == "Starter"


def test_public_config_and_manual_paypal(cloud, monkeypatch):
    monkeypatch.setenv("PAYPAL_ME_URL", "https://paypal.me/clipwise")
    config = cloud.get("/api/public/config").json()
    assert config["paypal_me"] == "https://paypal.me/clipwise"
    assert config["paypal"] == {
        "configured": False,
        "client_id": "",
        "mode": "live",
        "currency": "USD",
        "plans": {"Creator": "", "Studio": ""},
    }
    register(cloud, "manual@example.test")
    account = cloud.get("/api/account").json()
    assert account["paypal_me"] == "https://paypal.me/clipwise"
    assert cloud.post("/api/account/billing/Creator").status_code == 409


def test_admin_lists_teams_and_sets_plan(cloud, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.test")
    register(cloud, "admin@example.test")
    admin_team = cloud.get("/api/account").json()["team"]
    cloud.post("/api/account/logout")
    register(cloud, "customer@example.test")
    customer_team = cloud.get("/api/account").json()["team"]
    assert cloud.get("/api/admin/teams").status_code == 403
    cloud.post("/api/account/logout")
    cloud.post(
        "/api/account/login",
        json={"email": "admin@example.test", "password": "a-unique-test-password"},
    )
    teams = cloud.get("/api/admin/teams").json()["teams"]
    assert {row["id"] for row in teams} == {admin_team, customer_team}
    customer = next(row for row in teams if row["id"] == customer_team)
    assert customer["owner"] == "customer@example.test"
    assert customer["plan"] == "Starter"
    assert customer["members"] == 1
    assert cloud.post(
        "/api/admin/plan", json={"team": customer_team, "plan": "Creator"}
    ).is_success
    assert cloud.post(
        "/api/admin/plan", json={"team": customer_team, "plan": "Enterprise"}
    ).status_code == 422
    assert cloud.post(
        "/api/admin/plan", json={"team": "missing", "plan": "Studio"}
    ).status_code == 404
    cloud.post("/api/account/logout")
    cloud.post(
        "/api/account/login",
        json={"email": "customer@example.test", "password": "a-unique-test-password"},
    )
    account = cloud.get("/api/account").json()
    assert account["plan"] == "Creator"
    assert account["limit"] == 120
    assert cloud.get("/api/admin/teams").status_code == 403
