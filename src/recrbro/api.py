from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from recrbro.agent import add_agent_endpoint
from recrbro.config import FRONTEND_ORIGIN
from recrbro.db import (
    complete_search,
    create_search,
    get_profile,
    get_user,
    initialize_database,
    list_users,
    update_profile,
    usage_summary,
)
from recrbro.models import (
    CvAnalysis,
    Profile,
    ProfileUpdate,
    SearchRequest,
    SearchResponse,
    UsageSummary,
    User,
)
from recrbro.services import analyze_cv, profile_update_from_profile, search_linkedin


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Recrbro PoC API",
    description="Candidate profiles and live LinkedIn job discovery through Tavily.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_user(user_id: int) -> User:
    user = get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


def _require_profile(user_id: int) -> Profile:
    _require_user(user_id)
    profile = get_profile(user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return profile


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/users", response_model=list[User])
def users() -> list[User]:
    return list_users()


@app.get("/api/users/{user_id}/profile", response_model=Profile)
def profile(user_id: int) -> Profile:
    return _require_profile(user_id)


@app.put("/api/users/{user_id}/profile", response_model=Profile)
def save_profile(user_id: int, payload: ProfileUpdate) -> Profile:
    _require_user(user_id)
    return update_profile(user_id, payload)


@app.post("/api/users/{user_id}/cv", response_model=CvAnalysis)
async def upload_cv(user_id: int, file: UploadFile = File(...)) -> CvAnalysis:
    user = _require_user(user_id)
    if user.plan != "premium":
        raise HTTPException(
            status_code=403, detail="CV analysis is available only on the Premium plan."
        )
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Upload a PDF file.")
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="The PDF must be 10 MB or smaller.")
    try:
        result = await analyze_cv(
            user_id, file.filename or "cv.pdf", contents, _require_profile(user_id)
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    update_profile(
        user_id,
        profile_update_from_profile(result.profile),
        cv_filename=file.filename or "cv.pdf",
    )
    return result


@app.post("/api/users/{user_id}/search", response_model=SearchResponse)
def search(user_id: int, payload: SearchRequest) -> SearchResponse:
    user = _require_user(user_id)
    profile = _require_profile(user_id)
    limit = min(payload.max_results, user.result_limit)
    if not profile.core_skills:
        raise HTTPException(
            status_code=422,
            detail="Add at least one core skill before searching.",
        )
    try:
        query, offers, warning = search_linkedin(profile, limit)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    search_id = create_search(user_id, query)
    complete_search(search_id, offers, warning)
    return SearchResponse(
        search_id=search_id,
        query=query,
        offers=offers,
        warning=warning,
    )


@app.get("/api/users/{user_id}/usage", response_model=UsageSummary)
def usage(user_id: int) -> UsageSummary:
    _require_user(user_id)
    return usage_summary(user_id)


add_agent_endpoint(app)
