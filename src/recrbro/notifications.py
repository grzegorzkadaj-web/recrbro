from __future__ import annotations

from urllib.parse import quote

import requests

from recrbro.config import (
    MAILGUN_API_BASE_URL,
    MAILGUN_API_KEY,
    MAILGUN_DOMAIN,
    MAILGUN_FROM,
)
from recrbro.models import JobOffer


def send_search_results(email: str, offers: list[JobOffer]) -> str | None:
    api_key = MAILGUN_API_KEY
    domain = MAILGUN_DOMAIN
    sender = MAILGUN_FROM
    if not any((api_key, domain, sender)):
        return "Mailgun is not configured; results are available in the dashboard only."
    if not api_key or not domain or not sender:
        raise ValueError(
            "MAILGUN_API_KEY, MAILGUN_DOMAIN, and MAILGUN_FROM must be configured."
        )

    lines = [
        "Your scheduled RecrBro search is complete.",
        "",
        *[
            f"{index}. {offer.title} — {offer.company}\n{offer.url}"
            for index, offer in enumerate(offers, start=1)
        ],
    ]
    encoded_domain = quote(domain, safe="")
    response = requests.post(
        f"{MAILGUN_API_BASE_URL}/v3/{encoded_domain}/messages",
        auth=("api", api_key),
        data={
            "from": sender,
            "to": email,
            "subject": f"Your RecrBro shortlist: {len(offers)} offers",
            "text": "\n\n".join(lines),
        },
        timeout=20,
    )
    response.raise_for_status()
    return None
