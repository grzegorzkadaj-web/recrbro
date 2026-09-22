from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from recrbro.config import CURRENCY_RATE_CACHE_MINUTES, CURRENCY_RATE_URL

_cached_rate: tuple[float, datetime] | None = None


def eur_usd_rate() -> float:
    global _cached_rate

    now = datetime.now(timezone.utc)
    if _cached_rate is not None and now - _cached_rate[1] < timedelta(
        minutes=CURRENCY_RATE_CACHE_MINUTES
    ):
        return _cached_rate[0]

    request = Request(
        CURRENCY_RATE_URL,
        headers={"Accept": "application/json", "User-Agent": "RecrBro/0.1"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"Could not load the current EUR/USD rate: {error}"
        ) from error

    if payload.get("base") != "EUR" or payload.get("quote") != "USD":
        raise RuntimeError("Currency service returned an unexpected currency pair.")
    try:
        rate = float(payload["rate"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            "Currency service returned an invalid EUR/USD rate."
        ) from error
    if rate <= 0:
        raise RuntimeError("Currency service returned a non-positive EUR/USD rate.")

    _cached_rate = (rate, now)
    return rate


def usd_to_eur(amount_usd: float, rate: float | None = None) -> float:
    current_rate = rate if rate is not None else eur_usd_rate()
    return amount_usd / current_rate
