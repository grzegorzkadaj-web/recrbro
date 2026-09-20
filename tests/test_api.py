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
