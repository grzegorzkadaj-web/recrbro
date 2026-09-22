from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

Plan = Literal["free", "premium"]
WorkMode = Literal["remote", "on-site", "hybrid"]


class User(BaseModel):
    id: int
    name: str
    email: str
    plan: Plan
    result_limit: int
    monthly_budget_pln: float
    tracked_cost_usd: float
    credits_bought: float
    available_credits: float


class AuthRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=10, max_length=128)


class RegisterRequest(AuthRequest):
    name: str = Field(min_length=2, max_length=100)


class AuthResponse(BaseModel):
    token: str
    user: User


class Profile(BaseModel):
    user_id: int
    core_skills: list[str] = Field(default_factory=list)
    other_skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    location: str = ""
    work_modes: list[WorkMode] = Field(default_factory=list)
    minimum_salary: int | None = None
    contract_types: list[str] = Field(default_factory=list)
    excluded_companies: list[str] = Field(default_factory=list)
    additional_limitations: str = ""
    cv_filename: str | None = None

    @field_validator("work_modes", mode="before")
    @classmethod
    def normalize_work_modes(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        aliases = {"onsite": "on-site", "on site": "on-site"}
        return [
            aliases.get(str(mode).strip().casefold(), str(mode).strip().casefold())
            for mode in value
        ]


class ProfileUpdate(BaseModel):
    core_skills: list[str] = Field(default_factory=list)
    other_skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    location: str = ""
    work_modes: list[WorkMode] = Field(default_factory=list)
    minimum_salary: int | None = Field(default=None, ge=0)
    contract_types: list[str] = Field(default_factory=list)
    excluded_companies: list[str] = Field(default_factory=list)
    additional_limitations: str = Field(default="", max_length=4000)

    @field_validator("work_modes", mode="before")
    @classmethod
    def normalize_work_modes(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        aliases = {"onsite": "on-site", "on site": "on-site"}
        return [
            aliases.get(str(mode).strip().casefold(), str(mode).strip().casefold())
            for mode in value
        ]


class CvAnalysis(BaseModel):
    profile: Profile
    analysis_mode: Literal["ai", "local-fallback"]
    warning: str | None = None


class SearchRequest(BaseModel):
    max_results: int = Field(default=10, ge=1, le=10)


class JobOffer(BaseModel):
    id: int | None = None
    result_type: Literal["job", "collection"] = "job"
    title: str
    company: str
    url: HttpUrl
    summary: str
    score: float | None
    matched_skills: list[str] = Field(default_factory=list)
    match_reasons: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    search_id: int
    query: str
    offers: list[JobOffer]
    warning: str | None = None


class SearchJob(BaseModel):
    id: int
    status: Literal["queued", "running", "complete", "failed"]
    requested_results: int
    query: str
    offers: list[JobOffer] = Field(default_factory=list)
    warning: str | None = None
    error: str | None = None
    available_at: datetime
    created_at: datetime
    completed_at: datetime | None = None


class SearchResults(BaseModel):
    current: SearchJob | None = None
    archival: list[JobOffer] = Field(default_factory=list)


class BalanceEvent(BaseModel):
    id: int
    event_type: str
    delta_credits: float
    amount_usd: float | None = None
    eur_usd_rate: float | None = None
    created_at: datetime


class CheckoutRequest(BaseModel):
    method: Literal["przelewy24", "blik"] = "przelewy24"


class CheckoutResponse(BaseModel):
    payment_id: int
    redirect_url: HttpUrl


class UsageSummary(BaseModel):
    input_tokens: int
    output_tokens: int
    cost_usd: float
    credits_bought: float
    available_credits: float
