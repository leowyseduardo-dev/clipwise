"""Server-owned Stripe customers, checkout and canonical subscription status."""

import hashlib
import hmac
import os
import time
import httpx
from fastapi import HTTPException
from . import accounts


def prices():
    return {
        p: os.getenv("STRIPE_PRICE_" + p.upper(), "")
        for p in accounts.PLANS
        if p != "Starter"
    }


def api(path, *, data=None, params=None, key=None):
    secret = os.getenv("STRIPE_SECRET_KEY")
    if not secret:
        raise HTTPException(503, "Falta STRIPE_SECRET_KEY en el servidor.")
    headers = {"Authorization": "Bearer " + secret}
    if key:
        headers["Idempotency-Key"] = key
    try:
        result = httpx.request(
            "POST" if data is not None else "GET",
            "https://api.stripe.com/v1/" + path,
            headers=headers,
            data=data,
            params=params,
            timeout=15,
        )
        result.raise_for_status()
        return result.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Stripe no pudo completar la solicitud.")


def checkout(person, plan, origin):
    if person["role"] != "owner":
        raise HTTPException(
            403, "Solo la persona propietaria puede administrar el plan."
        )
    if not os.getenv("STRIPE_WEBHOOK_SECRET"):
        raise HTTPException(503, "Falta STRIPE_WEBHOOK_SECRET en el servidor.")
    price = prices().get(plan)
    if plan != "portal" and not price:
        raise HTTPException(
            503, "Configura el identificador de precio de ese plan en Stripe."
        )
    customer = person["customer"]
    if not customer:
        if plan == "portal":
            raise HTTPException(
                409, "Este equipo aún no tiene una cuenta de facturación."
            )
        customer = api(
            "customers",
            data={"email": person["email"], "metadata[team]": person["team"]},
            key="customer-" + person["team"],
        )["id"]
        with accounts.connection() as conn:
            conn.execute(
                "UPDATE teams SET customer=? WHERE id=?", (customer, person["team"])
            )
    if plan == "portal" or person["plan"] != "Starter":
        return api(
            "billing_portal/sessions", data={"customer": customer, "return_url": origin}
        )["url"]
    return api(
        "checkout/sessions",
        data={
            "mode": "subscription",
            "customer": customer,
            "line_items[0][price]": price,
            "line_items[0][quantity]": "1",
            "success_url": origin + "/",
            "cancel_url": origin + "/",
        },
        key="checkout-"
        + person["team"]
        + "-"
        + plan
        + "-"
        + str(int(time.time()) // 1800),
    )["url"]


def event(body, header):
    import json

    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    parts = [p.split("=", 1) for p in header.split(",") if "=" in p]
    try:
        stamp = next(v for k, v in parts if k == "t")
        valid_time = abs(time.time() - int(stamp)) <= 300
    except (StopIteration, ValueError):
        valid_time = False
    if not secret or not valid_time:
        raise HTTPException(400, "Firma no válida.")
    expected = hmac.new(
        secret.encode(), stamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    if not any(hmac.compare_digest(expected, v) for k, v in parts if k == "v1"):
        raise HTTPException(400, "Firma no válida.")
    record = json.loads(body)
    if not record["type"].startswith("customer.subscription."):
        return
    customer = record["data"]["object"]["customer"]
    with accounts.connection() as conn:
        if not conn.execute(
            "SELECT 1 FROM teams WHERE customer=?", (customer,)
        ).fetchone():
            return
        # Serialize refreshes so late and repeated deliveries cannot restore an obsolete plan.
        conn.execute("BEGIN IMMEDIATE")
        active = api(
            "subscriptions",
            params={"customer": customer, "status": "all", "limit": 100},
        )
        known = {v: k for k, v in prices().items() if v}
        plans = [
            known[item["price"]["id"]]
            for s in active["data"]
            if s["status"] in {"active", "trialing"}
            for item in s["items"]["data"]
            if item["price"]["id"] in known
        ]
        plan = max(["Starter", *plans], key=lambda p: accounts.PLANS[p][0])
        conn.execute("UPDATE teams SET plan=? WHERE customer=?", (plan, customer))
