from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from recrbro import db, services
from recrbro.api import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "test.db")
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def accept_job_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    def assess(
        _profile: object, results_by_url: dict[str, dict]
    ) -> dict[str, services.JobAssessment]:
        return {
            url: services.JobAssessment(
                candidate_id=index,
                is_active=True,
                location_matches=True,
                reason="Test fixture accepts the offer.",
            )
            for index, url in enumerate(results_by_url)
        }

    monkeypatch.setattr(services, "_assess_job_results", assess)


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
    assert "target_roles" not in response.json()
    assert response.json()["minimum_salary"] == 20000


def test_search_query_uses_criteria_without_target_role(client: TestClient) -> None:
    profile = db.get_profile(2)

    assert profile is not None
    assert services.build_search_query(profile) == (
        '"Python" Poland remote hybrid B2B employment hiring'
    )


def test_free_search_is_limited_and_ranked(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    accept_job_analysis: None,
) -> None:
    monkeypatch.setattr(
        services,
        "_resolve_linkedin_page",
        lambda url: (
            "job",
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
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    accept_job_analysis: None,
) -> None:
    monkeypatch.setattr(
        services,
        "_resolve_linkedin_page",
        lambda url: (
            "job",
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
        "non-detail, inactive, location-mismatched, or unverifiable offers were removed"
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

    assert services._resolve_linkedin_page(reported_url) == (
        "collection",
        "https://www.linkedin.com/jobs/senior-php-developer-jobs",
        "",
    )


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

    assert services._resolve_linkedin_page(
        "https://linkedin.com/jobs/view/4457269750"
    ) == (
        "job",
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
                b"Not currently <strong>accepting</strong> applications"
                b"</figcaption></figure>"
            )

    monkeypatch.setattr(services, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    resolved = services._resolve_linkedin_page(
        "https://www.linkedin.com/jobs/view/3834648737/"
    )

    assert resolved is not None
    result_type, url, page_content = resolved
    assert result_type == "job"
    assert url == "https://www.linkedin.com/jobs/view/3834648737"
    assert not services._is_active_offer(
        {
            "url": url,
            "raw_content": "Tavily snippet without an inactive marker.",
            "linkedin_page_content": page_content,
        }
    )


def test_ai_assesses_activity_and_requested_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeStructuredModel:
        def invoke(self, messages: list[tuple[str, str]]) -> dict:
            captured["messages"] = messages
            return {
                "parsed": services.JobAssessmentBatch(
                    assessments=[
                        services.JobAssessment(
                            candidate_id=0,
                            is_active=False,
                            location_matches=True,
                            reason="Applications are not being accepted.",
                        ),
                        services.JobAssessment(
                            candidate_id=1,
                            is_active=True,
                            location_matches=False,
                            reason="Remote work is restricted to the United States.",
                        ),
                    ]
                ),
                "raw": SimpleNamespace(
                    usage_metadata={"input_tokens": 1000, "output_tokens": 100}
                ),
            }

    class FakeChatOpenAI:
        def __init__(self, **kwargs: object):
            captured["model_kwargs"] = kwargs

        def with_structured_output(
            self, schema: type, **kwargs: object
        ) -> FakeStructuredModel:
            assert schema is services.JobAssessmentBatch
            captured["structured_kwargs"] = kwargs
            return FakeStructuredModel()

    recorded_usage: list[dict[str, object]] = []
    monkeypatch.setattr(services, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(services, "ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr(
        services, "record_usage", lambda **kwargs: recorded_usage.append(kwargs)
    )
    profile = db.get_profile(2)
    assert profile is not None
    results = {
        "https://www.linkedin.com/jobs/view/1": {
            "title": "PHP Developer - Poland",
            "linkedin_page_content": "Applications for this vacancy have ended.",
        },
        "https://www.linkedin.com/jobs/view/2": {
            "title": "Remote PHP Developer - United States",
            "linkedin_page_content": "Remote within the United States only.",
        },
    }

    assessments = services._assess_job_results(profile, results)

    assert captured["model_kwargs"] == {
        "model": "gpt-5-nano",
        "reasoning_effort": "low",
    }
    assert not assessments["https://www.linkedin.com/jobs/view/1"].is_active
    assert not assessments["https://www.linkedin.com/jobs/view/2"].location_matches
    assert '"requested_location": "Poland"' in captured["messages"][1][1]
    assert recorded_usage == [
        {
            "user_id": 2,
            "operation": "job_validation",
            "model": "gpt-5-nano",
            "input_tokens": 1000,
            "output_tokens": 100,
            "cost_usd": 9e-05,
        }
    ]


def test_search_excludes_ai_rejected_offers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeTavilyClient:
        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search(self, **_: object) -> dict:
            return {
                "results": [
                    {
                        "title": "PHP Developer - Closed Company",
                        "url": "https://www.linkedin.com/jobs/view/3001",
                        "content": "Applications for this vacancy have ended.",
                        "raw_content": "Applications for this vacancy have ended.",
                    },
                    {
                        "title": "Remote PHP Developer - United States",
                        "url": "https://www.linkedin.com/jobs/view/3002",
                        "content": "This remote role is available within the US.",
                        "raw_content": "This remote role is available within the US.",
                    },
                ]
            }

    monkeypatch.setattr(services, "TAVILY_API_KEY", "test-key")
    monkeypatch.setattr(services, "TavilyClient", FakeTavilyClient)
    monkeypatch.setattr(
        services,
        "_resolve_linkedin_page",
        lambda url: ("job", services._canonical_linkedin_job_url(url), "Apply"),
    )
    monkeypatch.setattr(
        services,
        "_assess_job_results",
        lambda _profile, results_by_url: {
            url: services.JobAssessment(
                candidate_id=index,
                is_active=index != 0,
                location_matches=index != 1,
                reason="Rejected by AI validation.",
            )
            for index, url in enumerate(results_by_url)
        },
    )

    response = client.post("/api/users/2/search", json={"max_results": 10})

    assert response.status_code == 200
    assert response.json()["offers"] == []
    assert "2 non-detail, inactive, location-mismatched" in response.json()["warning"]


def test_empty_location_accepts_any_ai_location_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStructuredModel:
        def invoke(self, _messages: list[tuple[str, str]]) -> dict:
            return {
                "parsed": services.JobAssessmentBatch(
                    assessments=[
                        services.JobAssessment(
                            candidate_id=0,
                            is_active=True,
                            location_matches=False,
                            reason="Model returned a restrictive location decision.",
                        )
                    ]
                ),
                "raw": SimpleNamespace(usage_metadata={}),
            }

    class FakeChatOpenAI:
        def __init__(self, **_kwargs: object):
            pass

        def with_structured_output(
            self, _schema: type, **_kwargs: object
        ) -> FakeStructuredModel:
            return FakeStructuredModel()

    monkeypatch.setattr(services, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(services, "ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr(services, "record_usage", lambda **_kwargs: None)
    profile = db.get_profile(2)
    assert profile is not None
    profile.location = ""

    assessments = services._assess_job_results(
        profile,
        {
            "https://www.linkedin.com/jobs/view/1": {
                "title": "Remote PHP Developer - United States",
                "linkedin_page_content": "Remote within the United States only.",
            }
        },
    )

    assert assessments["https://www.linkedin.com/jobs/view/1"].location_matches


def test_collections_fill_only_missing_slots_when_requested(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    accept_job_analysis: None,
) -> None:
    class FakeTavilyClient:
        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search(self, **_: object) -> dict:
            return {
                "results": [
                    {
                        "title": "Python Developer - Active Company",
                        "url": "https://www.linkedin.com/jobs/view/2001",
                        "content": "Python role in Poland.",
                        "raw_content": "Apply now for this Python role.",
                    },
                    {
                        "title": "Python Developer jobs",
                        "url": "https://www.linkedin.com/jobs/python-developer-jobs",
                        "content": "Browse Python developer jobs.",
                    },
                ]
            }

    def resolve(url: str):
        if "/view/" in url:
            return (
                "job",
                "https://www.linkedin.com/jobs/view/2001",
                "Apply now for this Python role.",
            )
        return (
            "collection",
            "https://www.linkedin.com/jobs/python-developer-jobs",
            "Browse matching jobs.",
        )

    monkeypatch.setattr(services, "TAVILY_API_KEY", "test-key")
    monkeypatch.setattr(services, "TavilyClient", FakeTavilyClient)
    monkeypatch.setattr(services, "_resolve_linkedin_page", resolve)

    response = client.post(
        "/api/users/2/search",
        json={"max_results": 3, "include_collections_if_needed": True},
    )

    assert response.status_code == 200
    offers = response.json()["offers"]
    assert [offer["result_type"] for offer in offers] == ["job", "collection"]
    assert offers[-1]["score"] == 0
