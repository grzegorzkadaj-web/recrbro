from __future__ import annotations

import secrets
from contextlib import asynccontextmanager

from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from recrbro.agent import add_agent_endpoint
from recrbro.auth import (
    authenticate_google,
    create_oauth_state,
    google_authorization_url,
    google_success_redirect,
    login_user,
    register_user,
    verify_oauth_state,
)
from recrbro.config import (
    APP_ENV,
    APP_SECRET,
    FREE_SEARCH_DELAY_MINUTES,
    FREE_SEARCH_SCHEDULE_MINUTES,
    FRONTEND_ORIGINS,
    SEARCH_LEASE_MINUTES,
    WORKER_SECRET,
)
from recrbro.db import (
    append_search_warning,
    claim_due_searches,
    complete_search,
    create_search,
    delete_session,
    fail_search,
    get_profile,
    get_search,
    get_search_results,
    initialize_database,
    list_balance_events,
    list_users,
    queue_free_search,
    search_owner_and_profile,
    update_profile,
    usage_summary,
    user_for_session,
)
from recrbro.models import (
    AuthRequest,
    AuthResponse,
    BalanceEvent,
    CheckoutRequest,
    CheckoutResponse,
    CvAnalysis,
    Profile,
    ProfileUpdate,
    RegisterRequest,
    SearchJob,
    SearchRequest,
    SearchResults,
    UsageSummary,
    User,
)
from recrbro.notifications import send_search_results
from recrbro.payments import create_checkout, verify_status
from recrbro.services import (
    analyze_cv,
    build_search_query,
    profile_update_from_profile,
    search_jobs,
)

security = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if APP_ENV == "production" and APP_SECRET == "development-only-change-me":
        raise RuntimeError("APP_SECRET must be configured in production.")
    initialize_database()
    yield


app = FastAPI(
    title="RecrBro API",
    description="Authenticated candidate profiles and live multi-source job discovery.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(FRONTEND_ORIGINS),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> User:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to continue.",
        )
    user = user_for_session(credentials.credentials)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session is invalid or expired.",
        )
    return user


def _profile_for(user: User) -> Profile:
    profile = get_profile(user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return profile


def _run_search(search_id: int) -> SearchJob:
    context = search_owner_and_profile(search_id)
    if context is None:
        raise LookupError("Search not found.")
    user, profile, job = context
    try:
        query, offers, warning = search_jobs(
            profile, min(job.requested_results, user.result_limit)
        )
        complete_search(search_id, offers, warning)
    except Exception as error:
        fail_search(search_id, str(error))
        raise
    completed_user = next(
        (candidate for candidate in list_users() if candidate.id == user.id), user
    )
    if completed_user.plan == "free":
        try:
            email_warning = send_search_results(user.email, offers)
        except Exception as error:
            email_warning = f"Email delivery failed: {error}"
        if email_warning:
            append_search_warning(search_id, email_warning)
    completed = get_search(search_id, user.id)
    if completed is None:
        raise LookupError("Completed search could not be loaded.")
    return completed


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/register", response_model=AuthResponse, status_code=201)
def register(payload: RegisterRequest) -> AuthResponse:
    try:
        token, user = register_user(payload.name, payload.email, payload.password)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return AuthResponse(token=token, user=user)


@app.post("/api/auth/login", response_model=AuthResponse)
def login(payload: AuthRequest) -> AuthResponse:
    try:
        token, user = login_user(payload.email, payload.password)
    except ValueError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    return AuthResponse(token=token, user=user)


@app.delete("/api/auth/session", status_code=204)
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> None:
    if credentials:
        delete_session(credentials.credentials)


@app.get("/api/auth/google/start")
def google_start() -> RedirectResponse:
    try:
        state = create_oauth_state()
        response = RedirectResponse(google_authorization_url(state))
        response.set_cookie(
            "recrbro_oauth_state",
            state,
            max_age=600,
            httponly=True,
            secure=APP_ENV == "production",
            samesite="lax",
        )
        return response
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/auth/google/callback")
def google_callback(
    code: str, state: str, recrbro_oauth_state: str | None = Cookie(default=None)
) -> RedirectResponse:
    if (
        not recrbro_oauth_state
        or not secrets.compare_digest(state, recrbro_oauth_state)
        or not verify_oauth_state(state)
    ):
        raise HTTPException(status_code=400, detail="Invalid OAuth state.")
    try:
        token, _ = authenticate_google(code)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    response = RedirectResponse(google_success_redirect(token))
    response.delete_cookie("recrbro_oauth_state")
    return response


@app.get("/api/me", response_model=User)
def me(user: User = Depends(current_user)) -> User:
    return user


@app.get("/api/users", response_model=list[User], include_in_schema=False)
def development_users() -> list[User]:
    if APP_ENV == "production":
        raise HTTPException(status_code=404, detail="Not found.")
    return list_users()


@app.get(
    "/api/users/{user_id}/profile",
    response_model=Profile,
    include_in_schema=False,
)
def development_profile(user_id: int) -> Profile:
    if APP_ENV == "production":
        raise HTTPException(status_code=404, detail="Not found.")
    profile = get_profile(user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return profile


@app.put(
    "/api/users/{user_id}/profile",
    response_model=Profile,
    include_in_schema=False,
)
def development_save_profile(user_id: int, payload: ProfileUpdate) -> Profile:
    if APP_ENV == "production":
        raise HTTPException(status_code=404, detail="Not found.")
    if get_profile(user_id) is None:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return update_profile(user_id, payload)


@app.get("/api/profile", response_model=Profile)
def profile(user: User = Depends(current_user)) -> Profile:
    return _profile_for(user)


@app.put("/api/profile", response_model=Profile)
def save_profile(payload: ProfileUpdate, user: User = Depends(current_user)) -> Profile:
    return update_profile(user.id, payload)


@app.post("/api/cv", response_model=CvAnalysis)
async def upload_cv(
    file: UploadFile = File(...), user: User = Depends(current_user)
) -> CvAnalysis:
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Upload a PDF file.")
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="The PDF must be 10 MB or smaller.")
    try:
        result = await analyze_cv(
            user.id, file.filename or "cv.pdf", contents, _profile_for(user)
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    update_profile(
        user.id,
        profile_update_from_profile(result.profile),
        cv_filename=file.filename or "cv.pdf",
    )
    return result


@app.post(
    "/api/users/{user_id}/cv",
    response_model=CvAnalysis,
    include_in_schema=False,
)
async def development_upload_cv(
    user_id: int, file: UploadFile = File(...)
) -> CvAnalysis:
    if APP_ENV == "production":
        raise HTTPException(status_code=404, detail="Not found.")
    user = next(
        (candidate for candidate in list_users() if candidate.id == user_id), None
    )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Upload a PDF file.")
    contents = await file.read()
    result = await analyze_cv(
        user.id, file.filename or "cv.pdf", contents, _profile_for(user)
    )
    update_profile(
        user.id,
        profile_update_from_profile(result.profile),
        cv_filename=file.filename or "cv.pdf",
    )
    return result


@app.post("/api/searches", response_model=SearchJob, status_code=202)
def search(payload: SearchRequest, user: User = Depends(current_user)) -> SearchJob:
    profile = _profile_for(user)
    limit = min(payload.max_results, user.result_limit, 10)
    if not profile.core_skills:
        raise HTTPException(
            status_code=422, detail="Add at least one core skill before searching."
        )
    query = build_search_query(profile)
    if user.plan == "free":
        try:
            search_id = queue_free_search(
                user.id,
                query,
                limit,
                FREE_SEARCH_DELAY_MINUTES,
                FREE_SEARCH_SCHEDULE_MINUTES,
            )
        except ValueError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
    else:
        try:
            search_id = create_search(user.id, query, limit)
            return _run_search(search_id)
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
    queued = get_search(search_id, user.id)
    if queued is None:
        raise HTTPException(
            status_code=500, detail="Queued search could not be loaded."
        )
    return queued


@app.post(
    "/api/users/{user_id}/search",
    response_model=SearchJob,
    include_in_schema=False,
)
def development_search(user_id: int, payload: SearchRequest) -> SearchJob:
    if APP_ENV == "production":
        raise HTTPException(status_code=404, detail="Not found.")
    user = next(
        (candidate for candidate in list_users() if candidate.id == user_id), None
    )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    profile = _profile_for(user)
    limit = min(payload.max_results, user.result_limit, 10)
    if not profile.core_skills:
        raise HTTPException(status_code=422, detail="Add at least one core skill.")
    try:
        search_id = create_search(user.id, build_search_query(profile), limit)
        return _run_search(search_id)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/searches/results", response_model=SearchResults)
def search_results(user: User = Depends(current_user)) -> SearchResults:
    return get_search_results(user.id)


@app.get("/api/searches/{search_id}", response_model=SearchJob)
def search_status(search_id: int, user: User = Depends(current_user)) -> SearchJob:
    job = get_search(search_id, user.id)
    if job is None:
        raise HTTPException(status_code=404, detail="Search not found.")
    return job


@app.post("/api/internal/run-due-searches")
def run_due_searches(
    x_worker_secret: str | None = Header(default=None),
) -> dict[str, int]:
    if not WORKER_SECRET or not secrets_compare(x_worker_secret, WORKER_SECRET):
        raise HTTPException(status_code=401, detail="Invalid worker secret.")
    completed = 0
    failed = 0
    for search_id in claim_due_searches(SEARCH_LEASE_MINUTES):
        try:
            _run_search(search_id)
            completed += 1
        except Exception:
            failed += 1
    return {"completed": completed, "failed": failed}


def secrets_compare(value: str | None, expected: str) -> bool:
    return value is not None and secrets.compare_digest(value, expected)


@app.get("/api/usage", response_model=UsageSummary)
def usage(user: User = Depends(current_user)) -> UsageSummary:
    return usage_summary(user.id)


@app.get("/api/balance-history", response_model=list[BalanceEvent])
def balance_history(user: User = Depends(current_user)) -> list[BalanceEvent]:
    return list_balance_events(user.id)


@app.post("/api/payments/checkout", response_model=CheckoutResponse)
def checkout(
    payload: CheckoutRequest, user: User = Depends(current_user)
) -> CheckoutResponse:
    try:
        return create_checkout(user, payload.method)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/api/payments/przelewy24/status")
def payment_status(payload: dict[str, object]) -> dict[str, str]:
    try:
        verify_status(payload)
    except (KeyError, ValueError, RuntimeError, LookupError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"status": "ok"}


add_agent_endpoint(app)


@app.middleware("http")
async def security_headers(request, call_next):
    if request.url.path.startswith("/agent"):
        authorization = request.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if (
            scheme.casefold() != "bearer"
            or not token
            or user_for_session(token) is None
        ):
            return JSONResponse(
                status_code=401, content={"detail": "Sign in to use the assistant."}
            )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if APP_ENV == "production":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response
