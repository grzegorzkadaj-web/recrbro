from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

Plan = Literal["free", "premium"]


class User(BaseModel):
    id: int
    name: str
    email: str
    plan: Plan
    result_limit: int
    monthly_budget_pln: float
    tracked_cost_usd: float


class Profile(BaseModel):
    user_id: int
    target_roles: list[str] = Field(default_factory=list)
    core_skills: list[str] = Field(default_factory=list)
    other_skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    location: str = ""
    work_modes: list[str] = Field(default_factory=list)
    minimum_salary: int | None = None
    contract_types: list[str] = Field(default_factory=list)
    excluded_companies: list[str] = Field(default_factory=list)
    cv_filename: str | None = None


class ProfileUpdate(BaseModel):
    target_roles: list[str] = Field(default_factory=list)
    core_skills: list[str] = Field(default_factory=list)
    other_skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    location: str = ""
    work_modes: list[str] = Field(default_factory=list)
    minimum_salary: int | None = Field(default=None, ge=0)
    contract_types: list[str] = Field(default_factory=list)
    excluded_companies: list[str] = Field(default_factory=list)


class CvAnalysis(BaseModel):
    profile: Profile
    analysis_mode: Literal["ai", "local-fallback"]
    warning: str | None = None


class SearchRequest(BaseModel):
    max_results: int = Field(default=10, ge=1, le=100)
    include_collections_if_needed: bool = False


class JobOffer(BaseModel):
    id: int | None = None
    result_type: Literal["job", "collection"] = "job"
    title: str
    company: str
    url: HttpUrl
    summary: str
    score: float
    matched_skills: list[str] = Field(default_factory=list)
    match_reasons: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    search_id: int
    query: str
    offers: list[JobOffer]
    warning: str | None = None


class UsageSummary(BaseModel):
    input_tokens: int
    output_tokens: int
    cost_usd: float
