from __future__ import annotations

import base64
import hashlib
import json
import secrets
from urllib.request import Request, urlopen

from recrbro.config import (
    FRONTEND_ORIGIN,
    P24_API_KEY,
    P24_CRC,
    P24_MERCHANT_ID,
    P24_POS_ID,
    P24_SANDBOX,
    PUBLIC_API_URL,
)
from recrbro.db import complete_payment, create_payment, get_payment
from recrbro.models import CheckoutResponse, User

PREMIUM_PRICE_GROSZ = 5000


def _base_url() -> str:
    return (
        "https://sandbox.przelewy24.pl"
        if P24_SANDBOX
        else "https://secure.przelewy24.pl"
    )


def _require_config() -> tuple[int, int, str, str]:
    if not all((P24_MERCHANT_ID, P24_POS_ID, P24_API_KEY, P24_CRC)):
        raise RuntimeError("Przelewy24 checkout is not configured.")
    return int(P24_MERCHANT_ID), int(P24_POS_ID), P24_API_KEY, P24_CRC


def _sign(values: dict[str, object]) -> str:
    return hashlib.sha384(
        json.dumps(values, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _request(method: str, path: str, payload: dict[str, object]) -> dict:
    _, pos_id, api_key, _ = _require_config()
    credentials = base64.b64encode(f"{pos_id}:{api_key}".encode()).decode()
    request = Request(
        f"{_base_url()}{path}",
        method=method,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        },
    )
    with urlopen(request, timeout=20) as response:
        result = json.load(response)
    if result.get("error"):
        raise RuntimeError(str(result["error"]))
    return result


def create_checkout(user: User, method: str) -> CheckoutResponse:
    merchant_id, pos_id, _, crc = _require_config()
    session_id = secrets.token_urlsafe(24)
    sign = _sign(
        {
            "sessionId": session_id,
            "merchantId": merchant_id,
            "amount": PREMIUM_PRICE_GROSZ,
            "currency": "PLN",
            "crc": crc,
        }
    )
    payload: dict[str, object] = {
        "merchantId": merchant_id,
        "posId": pos_id,
        "sessionId": session_id,
        "amount": PREMIUM_PRICE_GROSZ,
        "currency": "PLN",
        "description": "RecrBro AI credits",
        "email": user.email,
        "country": "PL",
        "language": "pl",
        "urlReturn": f"{FRONTEND_ORIGIN}/?payment=returned",
        "urlStatus": f"{PUBLIC_API_URL}/api/payments/przelewy24/status",
        "sign": sign,
    }
    response = _request("POST", "/api/v1/transaction/register", payload)
    token = response.get("data", {}).get("token")
    if not token:
        raise RuntimeError("Przelewy24 did not return a checkout token.")
    payment_id = create_payment(user.id, session_id, PREMIUM_PRICE_GROSZ, method)
    return CheckoutResponse(
        payment_id=payment_id,
        redirect_url=f"{_base_url()}/trnRequest/{token}",
    )


def verify_status(payload: dict[str, object]) -> None:
    merchant_id, pos_id, _, crc = _require_config()
    session_id = str(payload["sessionId"])
    order_id = int(payload["orderId"])
    amount = int(payload["amount"])
    currency = str(payload["currency"])
    payment = get_payment(session_id)
    if payment is None:
        raise ValueError("Unknown Przelewy24 payment session.")
    if amount != payment["amount_grosz"] or currency != "PLN":
        raise ValueError("Przelewy24 payment amount or currency does not match.")
    expected = _sign(
        {
            "merchantId": merchant_id,
            "posId": pos_id,
            "sessionId": session_id,
            "amount": amount,
            "originAmount": int(payload.get("originAmount", amount)),
            "currency": currency,
            "orderId": order_id,
            "methodId": int(payload["methodId"]),
            "statement": str(payload["statement"]),
            "crc": crc,
        }
    )
    if not secrets.compare_digest(str(payload.get("sign", "")), expected):
        raise ValueError("Invalid Przelewy24 notification signature.")
    verification = {
        "merchantId": merchant_id,
        "posId": pos_id,
        "sessionId": session_id,
        "amount": amount,
        "currency": currency,
        "orderId": order_id,
        "sign": _sign(
            {
                "sessionId": session_id,
                "orderId": order_id,
                "amount": amount,
                "currency": currency,
                "crc": crc,
            }
        ),
    }
    _request("PUT", "/api/v1/transaction/verify", verification)
    complete_payment(session_id, order_id)
