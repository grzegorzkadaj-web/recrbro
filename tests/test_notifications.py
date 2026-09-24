from __future__ import annotations

from types import SimpleNamespace

import pytest

from recrbro import notifications
from recrbro.models import JobOffer


@pytest.fixture
def offer() -> JobOffer:
    return JobOffer(
        title="Python Developer",
        company="Example",
        url="https://example.com/jobs/1",
        summary="Active Python role.",
        score=90,
    )


def test_sends_results_through_mailgun_api(
    monkeypatch: pytest.MonkeyPatch, offer: JobOffer
) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> SimpleNamespace:
        captured["url"] = url
        captured.update(kwargs)
        return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr(notifications, "MAILGUN_API_KEY", "test-api-key")
    monkeypatch.setattr(notifications, "MAILGUN_DOMAIN", "sandbox.example.mailgun.org")
    monkeypatch.setattr(
        notifications,
        "MAILGUN_FROM",
        "RecrBro <postmaster@sandbox.example.mailgun.org>",
    )
    monkeypatch.setattr(
        notifications, "MAILGUN_API_BASE_URL", "https://api.eu.mailgun.net"
    )
    monkeypatch.setattr(notifications.requests, "post", fake_post)

    warning = notifications.send_search_results("user@example.com", [offer])

    assert warning is None
    assert captured["url"] == (
        "https://api.eu.mailgun.net/v3/" "sandbox.example.mailgun.org/messages"
    )
    assert captured["auth"] == ("api", "test-api-key")
    assert captured["timeout"] == 20
    assert captured["data"] == {
        "from": "RecrBro <postmaster@sandbox.example.mailgun.org>",
        "to": "user@example.com",
        "subject": "Your RecrBro shortlist: 1 offers",
        "text": (
            "Your scheduled RecrBro search is complete.\n\n\n\n"
            "1. Python Developer — Example\nhttps://example.com/jobs/1"
        ),
    }


def test_rejects_incomplete_mailgun_configuration(
    monkeypatch: pytest.MonkeyPatch, offer: JobOffer
) -> None:
    monkeypatch.setattr(notifications, "MAILGUN_API_KEY", "test-api-key")
    monkeypatch.setattr(notifications, "MAILGUN_DOMAIN", None)
    monkeypatch.setattr(notifications, "MAILGUN_FROM", None)

    with pytest.raises(ValueError, match="must be configured"):
        notifications.send_search_results("user@example.com", [offer])


def test_returns_warning_when_mailgun_is_not_configured(
    monkeypatch: pytest.MonkeyPatch, offer: JobOffer
) -> None:
    monkeypatch.setattr(notifications, "MAILGUN_API_KEY", None)
    monkeypatch.setattr(notifications, "MAILGUN_DOMAIN", None)
    monkeypatch.setattr(notifications, "MAILGUN_FROM", None)

    warning = notifications.send_search_results("user@example.com", [offer])

    assert warning == (
        "Mailgun is not configured; results are available in the dashboard only."
    )
