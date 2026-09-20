from __future__ import annotations

import smtplib
from email.message import EmailMessage

from recrbro.config import (
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_TLS,
    SMTP_USERNAME,
)
from recrbro.models import JobOffer


def send_search_results(email: str, offers: list[JobOffer]) -> str | None:
    if not SMTP_HOST:
        return "SMTP is not configured; results are available in the dashboard only."
    message = EmailMessage()
    message["Subject"] = f"Your RecrBro shortlist: {len(offers)} offers"
    message["From"] = SMTP_FROM
    message["To"] = email
    lines = [
        "Your scheduled RecrBro search is complete.",
        "",
        *[
            f"{index}. {offer.title} — {offer.company}\n{offer.url}"
            for index, offer in enumerate(offers, start=1)
        ],
    ]
    message.set_content("\n\n".join(lines))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as client:
        if SMTP_USE_TLS:
            client.starttls()
        if SMTP_USERNAME:
            client.login(SMTP_USERNAME, SMTP_PASSWORD or "")
        client.send_message(message)
    return None
