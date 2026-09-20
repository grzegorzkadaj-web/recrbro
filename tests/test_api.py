from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from recrbro import db, services
from recrbro.api import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "test.db")
    with TestClient(app) as test_client:
        yield test_client


def test_seeds_free_and_premium_users(client: TestClient) -> None:
    response = client.get("/api/users")

    assert response.status_code == 200
    assert [(user["name"], user["plan"]) for user in response.json()] == [
        ("Free demo", "free"),
        ("Premium demo", "premium"),
    ]


def test_free_user_cannot_upload_cv(client: TestClient) -> None:
    response = client.post(
        "/api/users/1/cv",
        files={"file": ("cv.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert response.status_code == 403
    assert "Premium" in response.json()["detail"]


def test_profile_can_be_updated(client: TestClient) -> None:
    payload = {
        "target_roles": ["AI Engineer"],
        "core_skills": ["Python", "LangChain"],
        "other_skills": ["Docker"],
        "languages": ["English"],
        "location": "Warsaw",
        "work_modes": ["remote"],
        "minimum_salary": 20000,
        "contract_types": ["B2B"],
        "excluded_companies": ["Example Corp"],
    }

    response = client.put("/api/users/2/profile", json=payload)

    assert response.status_code == 200
    assert response.json()["target_roles"] == ["AI Engineer"]
    assert response.json()["minimum_salary"] == 20000


def test_free_search_is_limited_and_ranked(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        services,
        "_resolve_job_url",
        lambda url: (
            services._canonical_linkedin_job_url(url),
            "Apply now for this open role.",
        ),
    )

    class FakeTavilyClient:
        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search(self, **_: object) -> dict:
            return {
                "results": [
                    {
                        "title": f"Python Developer - Company {index}",
                        "url": f"https://www.linkedin.com/jobs/view/{index}",
                        "content": "Remote Python role in Poland with a B2B contract.",
                        "raw_content": (
                            "No longer accepting applications"
                            if index == 0
                            else "Apply now. Remote Python role in Poland with a B2B contract."
                        ),
                    }
                    for index in range(10)
                ]
            }

    monkeypatch.setattr(services, "TAVILY_API_KEY", "test-key")
    monkeypatch.setattr(services, "TavilyClient", FakeTavilyClient)

    response = client.post("/api/users/1/search", json={"max_results": 25})

    assert response.status_code == 200
    offers = response.json()["offers"]
    assert len(offers) == 5
    assert offers[0]["score"] > 0
    assert "Python" in offers[0]["matched_skills"]
    assert all(not offer["url"].endswith("/0") for offer in offers)


def test_search_extracts_page_content_before_active_filtering(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        services,
        "_resolve_job_url",
        lambda url: (
            services._canonical_linkedin_job_url(url),
            "Apply now for this open role.",
        ),
    )

    class FakeTavilyClient:
        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search(self, **_: object) -> dict:
            return {
                "results": [
                    {
                        "title": "Python Developer - Closed Company",
                        "url": "https://www.linkedin.com/jobs/view/1001",
                        "content": "Python role in Poland.",
                    },
                    {
                        "title": "Python Developer - Active Company",
                        "url": "https://www.linkedin.com/jobs/view/1002",
                        "content": "Python role in Poland.",
                    },
                ]
            }

        def extract(self, **_: object) -> dict:
            return {
                "results": [
                    {
                        "url": "https://www.linkedin.com/jobs/view/1001",
                        "raw_content": "No longer accepting applications",
                    },
                    {
                        "url": "https://www.linkedin.com/jobs/view/1002",
                        "raw_content": "Apply now for this Python role.",
                    },
                ]
            }

    monkeypatch.setattr(services, "TAVILY_API_KEY", "test-key")
    monkeypatch.setattr(services, "TavilyClient", FakeTavilyClient)

    response = client.post("/api/users/2/search", json={"max_results": 10})

    assert response.status_code == 200
    offers = response.json()["offers"]
    assert [offer["company"] for offer in offers] == ["Active Company"]
    assert (
        "non-detail, closed, or unverifiable offers were removed"
        in response.json()["warning"]
    )


def test_resolved_collection_page_is_not_a_job_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reported_url = (
        "https://www.linkedin.com/jobs/view/"
        "gymdesk-mid-level-php-developer-for-b2b-saas-at-"
        "online-jobs-philippines-work-at-home-4457269750"
    )

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def geturl(self) -> str:
            return (
                "https://www.linkedin.com/jobs/senior-php-developer-jobs"
                "?trk=expired_jd_redirect"
            )

        def read(self, _: int) -> bytes:
            return b""

    monkeypatch.setattr(services, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    assert services._resolve_job_url(reported_url) is None


def test_resolved_job_url_is_canonicalized(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def geturl(self) -> str:
            return (
                "https://pl.linkedin.com/jobs/view/python-developer-4457269750?trk=jobs"
            )

        def read(self, _: int) -> bytes:
            return b"Apply now for this Python role."

    monkeypatch.setattr(services, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    assert services._resolve_job_url("https://linkedin.com/jobs/view/4457269750") == (
        "https://www.linkedin.com/jobs/view/4457269750",
        "Apply now for this Python role.",
    )


def test_detail_page_with_closed_banner_is_inactive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def geturl(self) -> str:
            return "https://www.linkedin.com/jobs/view/3834648737/"

        def read(self, _: int) -> bytes:
            return (
                b'<figure class="closed-job">'
                b'<figcaption class="closed-job__flavor--closed">'
                b"No longer accepting applications</figcaption></figure>"
            )

    monkeypatch.setattr(services, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    resolved = services._resolve_job_url(
        "https://www.linkedin.com/jobs/view/3834648737/"
    )

    assert resolved is not None
    url, page_content = resolved
    assert url == "https://www.linkedin.com/jobs/view/3834648737"
    assert not services._is_active_offer(
        {
            "url": url,
            "raw_content": "Tavily snippet without an inactive marker.",
            "linkedin_page_content": page_content,
        }
    )
