"""PayPal Subscriptions: catalog, activation, cancellation and webhooks.

The browser only receives the public client ID and the plan IDs. The client
secret never leaves this process. A subscription is activated only after the
server verifies it directly with PayPal and checks that its ``custom_id``
matches the authenticated team.
"""

from __future__ import annotations

import base64
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import HTTPException

from . import accounts

PLAN_PRICES = {"Creator": "5.00", "Studio": "10.00"}
PLAN_TITLES = {"Creator": "Clipwise Creator", "Studio": "Clipwise Studio"}
PLAN_DESCRIPTIONS = {
    "Creator": "120 clips al mes, 1080p sin marca de agua forzada, 3 proyectos simultaneos, 2 plazas de equipo.",
    "Studio": "400 clips al mes, 1080p sin marca de agua forzada, 8 proyectos simultaneos, 5 plazas de equipo.",
}
WEBHOOK_EVENTS = [
    "BILLING.SUBSCRIPTION.ACTIVATED",
    "BILLING.SUBSCRIPTION.UPDATED",
    "BILLING.SUBSCRIPTION.CANCELLED",
    "BILLING.SUBSCRIPTION.EXPIRED",
    "BILLING.SUBSCRIPTION.SUSPENDED",
    "BILLING.SUBSCRIPTION.PAYMENT.FAILED",
    "PAYMENT.SALE.COMPLETED",
]
_TOKEN = {"value": "", "expires": 0.0}


def mode() -> str:
    value = os.getenv("PAYPAL_MODE", "live").strip().lower()
    return "sandbox" if value == "sandbox" else "live"


def api_base() -> str:
    return (
        "https://api-m.sandbox.paypal.com"
        if mode() == "sandbox"
        else "https://api-m.paypal.com"
    )


def client_id() -> str:
    return os.getenv("PAYPAL_CLIENT_ID", "").strip()


def client_secret() -> str:
    return os.getenv("PAYPAL_CLIENT_SECRET", "").strip()


def configured() -> bool:
    return bool(client_id() and client_secret())


def _catalog_path() -> Path:
    return accounts.home() / "paypal_catalog.json"


def _read_catalog() -> dict:
    path = _catalog_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_catalog(data: dict) -> None:
    path = _catalog_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp.replace(path)


def catalog() -> dict:
    """Resolve the product/plan IDs from env first, then the local catalog file."""
    env_product = os.getenv("PAYPAL_PRODUCT_ID", "").strip()
    env_plans = {
        "Creator": os.getenv("PAYPAL_CREATOR_PLAN_ID", "").strip(),
        "Studio": os.getenv("PAYPAL_STUDIO_PLAN_ID", "").strip(),
    }
    if env_product and all(env_plans.values()):
        stored = _read_catalog()
        return {
            "product_id": env_product,
            "plans": env_plans,
            "webhook_id": os.getenv("PAYPAL_WEBHOOK_ID", "").strip()
            or str(stored.get("webhook_id") or ""),
        }
    stored = _read_catalog()
    stored_plans = stored.get("plans") if isinstance(stored.get("plans"), dict) else {}
    return {
        "product_id": env_product or str(stored.get("product_id") or ""),
        "plans": {
            name: env_plans[name] or str(stored_plans.get(name) or "")
            for name in PLAN_PRICES
        },
        "webhook_id": os.getenv("PAYPAL_WEBHOOK_ID", "").strip()
        or str(stored.get("webhook_id") or ""),
    }


def _save_catalog(product_id: str, plans: dict, webhook_id: str = "") -> None:
    stored = _read_catalog()
    stored["product_id"] = product_id
    stored["plans"] = plans
    if webhook_id:
        stored["webhook_id"] = webhook_id
    _write_catalog(stored)


def plan_for(plan_id: str) -> str:
    plans = catalog().get("plans", {})
    return next((name for name, value in plans.items() if value == plan_id), "")


def token() -> str:
    if not configured():
        raise HTTPException(503, "PayPal no esta configurado en el servidor.")
    now = time.time()
    if _TOKEN["value"] and now < _TOKEN["expires"] - 60:
        return _TOKEN["value"]
    basic = base64.b64encode(
        (client_id() + ":" + client_secret()).encode("utf-8")
    ).decode("ascii")
    try:
        response = httpx.post(
            api_base() + "/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            headers={
                "Authorization": "Basic " + basic,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=20,
            trust_env=False,
        )
        response.raise_for_status()
        data = response.json()
        _TOKEN["value"] = str(data["access_token"])
        _TOKEN["expires"] = now + int(data.get("expires_in", 30000))
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise HTTPException(
            502, "PayPal no pudo autenticar la solicitud."
        ) from exc
    return _TOKEN["value"]


def api(
    path: str,
    *,
    method: str = "GET",
    data=None,
    request_id: str = "",
):
    headers = {
        "Authorization": "Bearer " + token(),
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    if request_id:
        headers["PayPal-Request-Id"] = request_id
    try:
        response = httpx.request(
            method,
            api_base() + path,
            headers=headers,
            json=data,
            timeout=30,
            trust_env=False,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(502, "PayPal no respondio a la solicitud.") from exc
    if response.status_code >= 400:
        detail = ""
        try:
            body = response.json()
            detail = str(body.get("message") or body.get("error_description") or "")
        except ValueError:
            pass
        raise HTTPException(
            502,
            "PayPal rechazo la solicitud."
            + (" " + detail if detail else ""),
        )
    if response.status_code == 204 or not response.content:
        return {}
    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(502, "PayPal devolvio una respuesta no valida.") from exc


def ensure_catalog() -> dict:
    """Create the Clipwise product and the two monthly plans if they are missing."""
    current = catalog()
    if not configured():
        return current
    if current.get("product_id") and all(current.get("plans", {}).values()):
        return current

    product_id = str(current.get("product_id") or "")
    if not product_id:
        products = api("/v1/catalogs/products?page_size=20").get("products", [])
        found = next(
            (item for item in products if item.get("name") == "Clipwise"), None
        )
        product_id = str(found["id"]) if found else ""
        if not product_id:
            created = api(
                "/v1/catalogs/products",
                method="POST",
                data={
                    "name": "Clipwise",
                    "description": "Clipwise - clips verticales automaticos con IA",
                    "type": "SERVICE",
                    "category": "SOFTWARE",
                },
                request_id="clipwise-product-v1",
            )
            product_id = str(created["id"])

    plans = dict(current.get("plans", {}))
    existing = api(
        "/v1/billing/plans?page_size=20&product_id=" + quote(product_id, safe="")
    ).get("plans", [])
    for name, price in PLAN_PRICES.items():
        if plans.get(name):
            continue
        title = PLAN_TITLES[name]
        found = next((item for item in existing if item.get("name") == title), None)
        if found:
            plans[name] = str(found["id"])
            continue
        created = api(
            "/v1/billing/plans",
            method="POST",
            data={
                "product_id": product_id,
                "name": title,
                "description": PLAN_DESCRIPTIONS[name],
                "status": "ACTIVE",
                "billing_cycles": [
                    {
                        "frequency": {
                            "interval_unit": "MONTH",
                            "interval_count": 1,
                        },
                        "tenure_type": "REGULAR",
                        "sequence": 1,
                        "total_cycles": 0,
                        "pricing_scheme": {
                            "fixed_price": {
                                "value": price,
                                "currency_code": "USD",
                            }
                        },
                    }
                ],
                "payment_preferences": {
                    "auto_bill_outstanding": True,
                    "setup_fee_failure_action": "CONTINUE",
                    "payment_failure_threshold": 3,
                },
            },
            request_id="clipwise-" + name.lower() + "-v1",
        )
        plans[name] = str(created["id"])
    _save_catalog(product_id, plans, str(current.get("webhook_id") or ""))
    return {"product_id": product_id, "plans": plans}


def public_config() -> dict:
    data = catalog()
    return {
        "configured": configured(),
        "client_id": client_id() if configured() else "",
        "mode": mode(),
        "currency": "USD",
        "plans": data.get("plans", {}),
    }


def _public_url() -> str:
    value = os.getenv("PAYPAL_PUBLIC_URL", "").strip().rstrip("/")
    if value.startswith("https://") and "localhost" not in value and "127.0.0.1" not in value:
        return value
    return ""


def webhook_id() -> str:
    return str(catalog().get("webhook_id") or "").strip()


def ensure_webhook() -> str:
    """Register the Clipwise webhook when a public HTTPS URL is configured."""
    current = webhook_id()
    if current:
        return current
    if not configured():
        return ""
    public = _public_url()
    if not public:
        return ""
    url = public + "/api/billing/paypal/webhook"
    wanted = [{"name": name} for name in WEBHOOK_EVENTS]
    hooks = api("/v1/notifications/webhooks").get("webhooks", [])
    found = next((item for item in hooks if item.get("url") == url), None)
    if found:
        existing = {
            str(item.get("name"))
            for item in found.get("event_types", [])
            if isinstance(item, dict)
        }
        merged = list(found.get("event_types", []))
        for item in wanted:
            if item["name"] not in existing:
                merged.append(item)
        if len(merged) != len(found.get("event_types", [])):
            api(
                "/v1/notifications/webhooks/" + quote(str(found["id"]), safe=""),
                method="PATCH",
                data=[{"op": "replace", "path": "/event_types", "value": merged}],
            )
        hook_id = str(found["id"])
    else:
        created = api(
            "/v1/notifications/webhooks",
            method="POST",
            data={"url": url, "event_types": wanted},
        )
        hook_id = str(created["id"])
    stored = catalog()
    _save_catalog(
        str(stored.get("product_id") or ""),
        dict(stored.get("plans", {})),
        hook_id,
    )
    return hook_id


def bootstrap() -> dict:
    return {"catalog": ensure_catalog(), "webhook_id": ensure_webhook()}


def subscription_details(subscription_id: str) -> dict:
    return api("/v1/billing/subscriptions/" + quote(subscription_id, safe=""))


def _cancel_remote(subscription_id: str, reason: str) -> None:
    """Cancel at PayPal before changing local state.

    A transient PayPal/API failure must not leave a subscription billing in the
    background while Clipwise tells the customer it is cancelled.
    """
    details = subscription_details(subscription_id)
    status = str(details.get("status") or "").upper()
    if status in {"CANCELLED", "EXPIRED"}:
        return
    try:
        api(
            "/v1/billing/subscriptions/" + quote(subscription_id, safe="") + "/cancel",
            method="POST",
            data={"reason": reason},
        )
    except HTTPException as exc:
        # A concurrent request may have already cancelled it.
        try:
            details = subscription_details(subscription_id)
        except HTTPException:
            raise exc
        if str(details.get("status") or "").upper() in {"CANCELLED", "EXPIRED"}:
            return
        raise


def _activate_remote(subscription_id: str) -> None:
    api(
        "/v1/billing/subscriptions/" + quote(subscription_id, safe="") + "/activate",
        method="POST",
        data={},
    )


def activate(person: dict, subscription_id: str) -> dict:
    if person["role"] != "owner":
        raise HTTPException(
            403, "Solo la persona propietaria puede administrar el plan."
        )
    subscription_id = subscription_id.strip()
    if not subscription_id or len(subscription_id) > 128:
        raise HTTPException(400, "Suscripcion de PayPal no valida.")
    details = subscription_details(subscription_id)
    if str(details.get("custom_id") or "") != person["team"]:
        raise HTTPException(
            403, "La suscripcion no pertenece a este equipo."
        )
    plan_id = str(details.get("plan_id") or "")
    plan = plan_for(plan_id)
    if not plan:
        raise HTTPException(
            400, "El plan de PayPal no corresponde a Clipwise."
        )
    status = str(details.get("status") or "").upper()
    if status == "APPROVAL_PENDING":
        raise HTTPException(
            409,
            "PayPal todavia no confirmo la suscripcion. Completa el pago y "
            "recarga esta pantalla.",
        )
    if status == "APPROVED":
        # The buyer approved but PayPal has not started the billing cycle.
        # Activate it explicitly instead of granting a paid plan without a
        # confirmed subscription.
        try:
            _activate_remote(subscription_id)
        except HTTPException as exc:
            try:
                details = subscription_details(subscription_id)
            except HTTPException:
                raise exc
            status = str(details.get("status") or "").upper()
            if status != "ACTIVE":
                raise exc
        else:
            details = subscription_details(subscription_id)
            status = str(details.get("status") or "").upper()
            if status == "APPROVED":
                status = "ACTIVE"
    if status != "ACTIVE":
        raise HTTPException(
            409,
            "PayPal todavia no confirmo la suscripcion (estado "
            + (status or "desconocido")
            + ").",
        )
    billing = details.get("billing_info") or {}
    renews_at = billing.get("next_billing_time")
    previous = accounts.subscription(person["team"])
    if (
        previous
        and previous.get("id") != subscription_id
        and str(previous.get("status") or "").upper() in {"ACTIVE", "APPROVED"}
    ):
        _cancel_remote(str(previous["id"]), "Cambio de plan en Clipwise")
        accounts.update_subscription(str(previous["id"]), "CANCELLED")
    accounts.save_subscription(
        subscription_id, person["team"], plan, plan_id, status, renews_at
    )
    accounts.set_plan(person["team"], plan)
    return {
        "ok": True,
        "plan": plan,
        "status": status,
        "renews_at": renews_at,
    }


def cancel(person: dict) -> dict:
    if person["role"] != "owner":
        raise HTTPException(
            403, "Solo la persona propietaria puede administrar el plan."
        )
    current = accounts.subscription(person["team"])
    if not current or str(current.get("status") or "").upper() not in {
        "ACTIVE",
        "APPROVED",
        "SUSPENDED",
        "PAYMENT_FAILED",
    }:
        raise HTTPException(404, "No hay una suscripcion activa.")
    _cancel_remote(str(current["id"]), "Cancelada por el cliente")
    renews_at = current.get("renews_at")
    accounts.update_subscription(str(current["id"]), "CANCELLED", renews_at)
    if not renews_at:
        accounts.set_plan(person["team"], "Starter")
    return {
        "ok": True,
        "status": "CANCELLED",
        "active_until": renews_at,
        "plan": person["plan"] if renews_at else "Starter",
    }


def _parse_time(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def reconcile_team(team: str, current_plan: str) -> str:
    """Downgrade a cancelled subscription once its paid period has ended."""
    current = accounts.subscription(team)
    if not current:
        return current_plan
    status = str(current.get("status") or "").upper()
    if status in {"ACTIVE", "APPROVED", "MANUAL", "PAYMENT_FAILED"}:
        return current_plan
    if status == "CANCELLED":
        until = _parse_time(current.get("renews_at"))
        if until and until > datetime.now(timezone.utc):
            return current_plan
    if current_plan != "Starter":
        accounts.set_plan(team, "Starter")
        return "Starter"
    return current_plan


def _handle_event(event: dict) -> None:
    event_type = str(event.get("event_type") or "")
    resource = event.get("resource") or {}
    if not isinstance(resource, dict):
        return
    subscription_id = ""
    if event_type.startswith("BILLING.SUBSCRIPTION."):
        subscription_id = str(resource.get("id") or "")
    elif event_type == "PAYMENT.SALE.COMPLETED":
        subscription_id = str(resource.get("billing_agreement_id") or "")
    if not subscription_id:
        return

    stored = accounts.subscription_by_id(subscription_id)
    team = str(resource.get("custom_id") or (stored or {}).get("team_id") or "")
    if not team:
        try:
            details = subscription_details(subscription_id)
            team = str(details.get("custom_id") or "")
        except HTTPException:
            return
    if not team:
        return

    if event_type == "BILLING.SUBSCRIPTION.ACTIVATED":
        plan_id = str(resource.get("plan_id") or (stored or {}).get("plan_id") or "")
        plan = plan_for(plan_id)
        if not plan:
            return
        billing = resource.get("billing_info") or {}
        renews_at = billing.get("next_billing_time") or (stored or {}).get("renews_at")
        accounts.save_subscription(
            subscription_id, team, plan, plan_id, "ACTIVE", renews_at
        )
        accounts.set_plan(team, plan)
    elif event_type == "BILLING.SUBSCRIPTION.UPDATED":
        plan_id = str(resource.get("plan_id") or (stored or {}).get("plan_id") or "")
        plan = plan_for(plan_id)
        if not plan:
            return
        status = str(resource.get("status") or "ACTIVE").upper()
        # A webhook without a local subscription can only add access. It must
        # never create a row that a later reconciliation uses to remove it.
        if status not in {"ACTIVE", "APPROVED"} and not stored:
            return
        billing = resource.get("billing_info") or {}
        renews_at = billing.get("next_billing_time") or (stored or {}).get("renews_at")
        accounts.save_subscription(subscription_id, team, plan, plan_id, status, renews_at)
        if status in {"ACTIVE", "APPROVED"}:
            accounts.set_plan(team, plan)
    elif event_type == "BILLING.SUBSCRIPTION.CANCELLED":
        if not stored:
            return
        billing = resource.get("billing_info") or {}
        renews_at = billing.get("next_billing_time") or stored.get("renews_at")
        accounts.update_subscription(subscription_id, "CANCELLED", renews_at)
        if not renews_at:
            accounts.set_plan(team, "Starter")
    elif event_type in {
        "BILLING.SUBSCRIPTION.EXPIRED",
        "BILLING.SUBSCRIPTION.SUSPENDED",
    }:
        if not stored:
            return
        status = event_type.rsplit(".", 1)[-1]
        accounts.update_subscription(subscription_id, status)
        accounts.set_plan(team, "Starter")
    elif event_type == "BILLING.SUBSCRIPTION.PAYMENT.FAILED":
        if not stored:
            return
        accounts.update_subscription(subscription_id, "PAYMENT_FAILED")
    elif event_type == "PAYMENT.SALE.COMPLETED":
        try:
            details = subscription_details(subscription_id)
        except HTTPException:
            return
        plan_id = str(details.get("plan_id") or (stored or {}).get("plan_id") or "")
        plan = plan_for(plan_id)
        if not plan:
            return
        billing = details.get("billing_info") or {}
        renews_at = billing.get("next_billing_time") or (stored or {}).get("renews_at")
        accounts.save_subscription(
            subscription_id, team, plan, plan_id, "ACTIVE", renews_at
        )
        accounts.set_plan(team, plan)


def webhook(raw: bytes, headers) -> dict:
    try:
        event = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(400, "Evento de PayPal no valido.") from exc
    if not isinstance(event, dict):
        raise HTTPException(400, "Evento de PayPal no valido.")
    hook_id = webhook_id()
    if not hook_id:
        if os.getenv("PAYPAL_WEBHOOK_INSECURE") == "1":
            _handle_event(event)
            return {"received": True, "verified": False}
        raise HTTPException(
            503,
            "Falta PAYPAL_WEBHOOK_ID. Configura el webhook en PayPal o define "
            "PAYPAL_PUBLIC_URL y ejecuta el setup.",
        )
    payload = {
        "auth_algo": headers.get("paypal-auth-algo", ""),
        "cert_url": headers.get("paypal-cert-url", ""),
        "transmission_id": headers.get("paypal-transmission-id", ""),
        "transmission_sig": headers.get("paypal-transmission-sig", ""),
        "transmission_time": headers.get("paypal-transmission-time", ""),
        "webhook_id": hook_id,
        "webhook_event": event,
    }
    try:
        response = httpx.post(
            api_base() + "/v1/notifications/verify-webhook-signature",
            headers={
                "Authorization": "Bearer " + token(),
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=25,
            trust_env=False,
        )
        result = response.json() if response.content else {}
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            502, "No se pudo verificar el webhook con PayPal."
        ) from exc
    if response.status_code >= 400 or result.get("verification_status") != "SUCCESS":
        raise HTTPException(400, "Firma de webhook no valida.")
    _handle_event(event)
    return {"received": True, "verified": True}
