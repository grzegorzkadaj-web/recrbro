from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from recrbro import api as api_module
from recrbro import db, services
from recrbro.api import app
from recrbro.config import _normalized_origins


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


def test_profile_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/profile")

    assert response.status_code == 401


def test_frontend_origins_are_normalized() -> None:
    assert _normalized_origins(
        " https://web.example.com/, https://preview.example.com, "
        "https://web.example.com "
    ) == ("https://web.example.com", "https://preview.example.com")


def test_registration_cors_preflight(client: TestClient) -> None:
    response = client.options(
        "/api/auth/register",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_user_can_register_and_access_own_profile(client: TestClient) -> None:
    registration = client.post(
        "/api/auth/register",
        json={
            "name": "Ada Candidate",
            "email": "ada@example.com",
            "password": "correct-horse-battery",
        },
    )

    assert registration.status_code == 201
    payload = registration.json()
    assert payload["user"]["plan"] == "premium"
    assert payload["user"]["credits_bought"] == 1
    assert payload["user"]["available_credits"] == 1

    response = client.get(
        "/api/profile",
        headers={"Authorization": f"Bearer {payload['token']}"},
    )

    assert response.status_code == 200
    assert response.json()["user_id"] == payload["user"]["id"]
    assert response.json()["core_skills"] == []


def test_free_account_search_is_queued(client: TestClient) -> None:
    registration = client.post(
        "/api/auth/register",
        json={
            "name": "Queue Tester",
            "email": "queue@example.com",
            "password": "correct-horse-battery",
        },
    ).json()
    headers = {"Authorization": f"Bearer {registration['token']}"}
    with db.connection() as database:
        database.execute(
            "UPDATE users SET plan = 'free', result_limit = 5 WHERE id = ?",
            (registration["user"]["id"],),
        )
    client.put(
        "/api/profile",
        headers=headers,
        json={
            "core_skills": ["Python"],
            "other_skills": [],
            "languages": ["English"],
            "location": "Poland",
            "work_modes": ["remote"],
            "minimum_salary": None,
            "contract_types": ["B2B"],
            "excluded_companies": [],
        },
    )

    response = client.post(
        "/api/searches",
        headers=headers,
        json={"max_results": 100},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["requested_results"] == 5

    second = client.post(
        "/api/searches",
        headers=headers,
        json={"max_results": 5},
    )

    first_time = datetime.fromisoformat(
        response.json()["available_at"].replace("Z", "+00:00")
    )
    second_time = datetime.fromisoformat(
        second.json()["available_at"].replace("Z", "+00:00")
    )
    assert second_time - first_time >= timedelta(minutes=60)


def test_agent_requires_authentication(client: TestClient) -> None:
    response = client.post("/agent", json={})

    assert response.status_code == 401


def test_email_failure_does_not_discard_completed_search(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    search_id = db.create_search(1, '"Python" Poland', requested_results=1)
    offer = services.JobOffer(
        title="Python Developer",
        company="Example",
        url="https://www.linkedin.com/jobs/view/123",
        summary="Active Python role.",
        score=90,
        matched_skills=["Python"],
        match_reasons=["Matches Python"],
    )
    monkeypatch.setattr(
        api_module,
        "search_jobs",
        lambda _profile, _limit: ('"Python" Poland', [offer], None),
    )
    monkeypatch.setattr(
        api_module,
        "send_search_results",
        lambda _email, _offers: (_ for _ in ()).throw(RuntimeError("SMTP offline")),
    )

    result = api_module._run_search(search_id)

    assert result.status == "complete"
    assert len(result.offers) == 1
    assert "Email delivery failed" in (result.warning or "")


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
    assert services.build_search_queries(profile, 100) == [
        '"Python" jobs Poland remote hybrid B2B employment hiring apply',
        '"Python" developer jobs Poland remote hybrid B2B employment hiring apply',
        '"Python" engineer jobs Poland remote hybrid B2B employment hiring apply',
        '"Python" specialist jobs Poland remote hybrid B2B employment hiring apply',
        '"Python" Poland remote hybrid B2B employment job opening apply',
    ]


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
        "non-detail, inactive, location-mismatched, excluded-company, or "
        "unverifiable offers were removed" in response.json()["warning"]
    )
    assert "Diagnostics:" in response.json()["warning"]


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


def test_ai_assessment_batches_candidates_and_retries_missing_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_ids: list[list[int]] = []

    class FakeStructuredModel:
        def invoke(self, messages: list[tuple[str, str]]) -> dict:
            payload = json.loads(messages[1][1])
            candidate_ids = [
                candidate["candidate_id"] for candidate in payload["candidates"]
            ]
            requested_ids.append(candidate_ids)
            returned_ids = candidate_ids
            if candidate_ids == [0, 1, 2, 3, 4]:
                returned_ids = [0, 1, 2, 3]
            return {
                "parsed": services.JobAssessmentBatch(
                    assessments=[
                        services.JobAssessment(
                            candidate_id=candidate_id,
                            is_active=True,
                            location_matches=True,
                            reason="Offer is active.",
                        )
                        for candidate_id in returned_ids
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
    results = {
        f"https://www.linkedin.com/jobs/view/{candidate_id}": {
            "title": f"Job {candidate_id}",
            "linkedin_page_content": "Applications are open.",
        }
        for candidate_id in range(7)
    }

    assessments = services._assess_job_results(profile, results)

    assert requested_ids == [[0, 1, 2, 3, 4], [4], [5, 6]]
    assert len(assessments) == 7


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
    assert "1 inactive, 1 location mismatches" in response.json()["warning"]


def test_search_uses_tavily_content_when_direct_fetch_is_blocked(
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
                        "url": "https://www.linkedin.com/jobs/view/4001",
                        "content": "Python role in Poland.",
                        "raw_content": "Apply now for this active Python role in Poland.",
                    }
                ]
            }

    monkeypatch.setattr(services, "TAVILY_API_KEY", "test-key")
    monkeypatch.setattr(services, "TavilyClient", FakeTavilyClient)
    monkeypatch.setattr(services, "_resolve_linkedin_page", lambda _url: None)

    response = client.post("/api/users/2/search", json={"max_results": 3})

    assert response.status_code == 200
    assert len(response.json()["offers"]) == 1
    assert any(
        reason.startswith("Status verified from Tavily content")
        for reason in response.json()["offers"][0]["match_reasons"]
    )
    assert "1 Tavily-content fallbacks" in response.json()["warning"]


def test_search_merges_results_from_focused_queries(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    accept_job_analysis: None,
) -> None:
    search_calls: list[dict[str, object]] = []

    class FakeTavilyClient:
        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search(self, **kwargs: object) -> dict:
            search_calls.append(kwargs)
            index = len(search_calls)
            return {
                "results": [
                    {
                        "title": f"Python Developer - Company {index}",
                        "url": f"https://www.linkedin.com/jobs/view/50{index}",
                        "content": "Python role in Poland.",
                        "raw_content": "Apply now for this active Python role.",
                    }
                ]
            }

    monkeypatch.setattr(services, "TAVILY_API_KEY", "test-key")
    monkeypatch.setattr(services, "TavilyClient", FakeTavilyClient)
    monkeypatch.setattr(
        services,
        "_resolve_linkedin_page",
        lambda url: (
            "job",
            services._canonical_linkedin_job_url(url),
            "Apply now for this active Python role.",
        ),
    )

    response = client.post("/api/users/2/search", json={"max_results": 5})

    assert response.status_code == 200
    assert len(search_calls) == 2
    assert len(response.json()["offers"]) == 2
    assert all(
        call["max_results"] == 10
        and call["search_depth"] == "advanced"
        and "include_domains" not in call
        and "include_domains_mode" not in call
        for call in search_calls
    )


def test_tavily_errors_return_service_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeTavilyClient:
        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search(self, **_: object) -> dict:
            raise services.BadRequestError("Invalid Tavily request.")

    monkeypatch.setattr(services, "TAVILY_API_KEY", "test-key")
    monkeypatch.setattr(services, "TavilyClient", FakeTavilyClient)

    response = client.post("/api/users/2/search", json={"max_results": 5})

    assert response.status_code == 503
    assert response.json()["detail"] == "Tavily search failed: Invalid Tavily request."


def test_search_accepts_verified_non_linkedin_job_pages(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    accept_job_analysis: None,
) -> None:
    class FakeTavilyClient:
        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search(self, **kwargs: object) -> dict:
            assert "include_domains" not in kwargs
            return {
                "results": [
                    {
                        "title": "Backend Engineer - Acme",
                        "url": (
                            "https://boards.greenhouse.io/acme/jobs/12345"
                            "?utm_source=tavily"
                        ),
                        "content": "Python role in Poland.",
                        "raw_content": "Apply for this active remote Python role in Poland.",
                    }
                ]
            }

    monkeypatch.setattr(services, "TAVILY_API_KEY", "test-key")
    monkeypatch.setattr(services, "TavilyClient", FakeTavilyClient)

    response = client.post("/api/users/2/search", json={"max_results": 3})

    assert response.status_code == 200
    assert response.json()["offers"][0]["url"] == (
        "https://boards.greenhouse.io/acme/jobs/12345"
    )
    assert response.json()["offers"][0]["company"] == "Acme"


def test_work_modes_are_typed_and_normalize_onsite_alias(
    client: TestClient,
) -> None:
    profile = {
        "core_skills": ["Python"],
        "other_skills": [],
        "languages": [],
        "location": "",
        "work_modes": ["remote", "onsite", "hybrid"],
        "minimum_salary": None,
        "contract_types": [],
        "excluded_companies": [],
    }

    response = client.put("/api/users/2/profile", json=profile)
    invalid = client.put(
        "/api/users/2/profile",
        json={**profile, "work_modes": ["sometimes-office"]},
    )

    assert response.status_code == 200
    assert response.json()["work_modes"] == ["remote", "on-site", "hybrid"]
    assert invalid.status_code == 422


def test_credit_exhaustion_downgrades_and_payment_restores(
    client: TestClient,
) -> None:
    registration = client.post(
        "/api/auth/register",
        json={
            "name": "Credit Tester",
            "email": "credits@example.com",
            "password": "correct-horse-battery",
        },
    ).json()
    user_id = registration["user"]["id"]
    token = registration["token"]
    headers = {"Authorization": f"Bearer {token}"}

    db.record_usage(user_id, "test", "test-model", 1, 1, 0.25)

    exhausted = client.get("/api/me", headers=headers).json()
    usage = client.get("/api/usage", headers=headers).json()
    assert exhausted["plan"] == "free"
    assert exhausted["result_limit"] == 5
    assert usage["available_credits"] == 0

    payment_id = db.create_payment(user_id, "verified-session", 5000, "blik")
    assert payment_id > 0
    db.complete_payment("verified-session", 12345)
    db.complete_payment("verified-session", 12345)

    restored = client.get("/api/me", headers=headers).json()
    assert restored["plan"] == "premium"
    assert restored["result_limit"] == 100
    assert restored["credits_bought"] == 13.5
    assert restored["available_credits"] == 12.5


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


def test_collection_pages_are_crawled_when_no_verified_jobs(
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
                        "raw_content": (
                            '<a href="/jobs/view/python-developer-4441830533'
                            '?trackingId=abc">Python Developer - Fallback Company</a>'
                        ),
                    },
                ]
            }

        def extract(self, **kwargs: object) -> dict:
            assert kwargs["urls"] == ["https://www.linkedin.com/jobs/view/4441830533"]
            return {
                "results": [
                    {
                        "url": "https://www.linkedin.com/jobs/view/4441830533",
                        "raw_content": "Apply now for this Python role in Poland.",
                    }
                ]
            }

    def resolve(url: str):
        if url.endswith("/2001"):
            return (
                "job",
                "https://www.linkedin.com/jobs/view/2001",
                "No longer accepting applications.",
            )
        if "/view/" in url:
            return (
                "job",
                "https://www.linkedin.com/jobs/view/4441830533",
                "Apply now for this Python role in Poland.",
            )
        return None

    monkeypatch.setattr(services, "TAVILY_API_KEY", "test-key")
    monkeypatch.setattr(services, "TavilyClient", FakeTavilyClient)
    monkeypatch.setattr(services, "_resolve_linkedin_page", resolve)

    response = client.post("/api/users/2/search", json={"max_results": 3})

    assert response.status_code == 200
    offers = response.json()["offers"]
    assert [offer["result_type"] for offer in offers] == ["job", "collection"]
    assert offers[0]["url"] == "https://www.linkedin.com/jobs/view/4441830533"
    assert offers[0]["company"] == "Fallback Company"
    assert offers[1]["score"] is None
