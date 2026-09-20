from __future__ import annotations

import re
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from pypdf import PdfReader
from tavily import TavilyClient

from recrbro.config import OPENAI_API_KEY, OPENAI_MODEL, TAVILY_API_KEY
from recrbro.db import record_usage
from recrbro.models import CvAnalysis, JobOffer, Profile, ProfileUpdate

CLOSED_OFFER_MARKERS = (
    "no longer accepting applications",
    "not accepting applications",
    "applications are closed",
    "applications have closed",
    "application window has closed",
    "this job is no longer available",
    "job is no longer available",
    "position is no longer available",
    "position has been filled",
    "vacancy has been filled",
    "job has expired",
    "job posting has expired",
    "closed-job__flavor--closed",
)
LINKEDIN_JOB_PATH = re.compile(r"^/jobs/view/(?:.+-)?(?P<job_id>\d+)/?$")


class ExtractedCvProfile(BaseModel):
    target_roles: list[str] = Field(default_factory=list)
    core_skills: list[str] = Field(default_factory=list)
    other_skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def _extract_pdf_text(contents: bytes) -> str:
    reader = PdfReader(BytesIO(contents))
    text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    if not text:
        raise ValueError("The PDF does not contain extractable text.")
    return text


def _fallback_cv_profile(text: str) -> ExtractedCvProfile:
    known_skills = [
        "Python",
        "FastAPI",
        "Django",
        "Flask",
        "JavaScript",
        "TypeScript",
        "React",
        "SQL",
        "PostgreSQL",
        "Docker",
        "Kubernetes",
        "Azure",
        "AWS",
        "LangChain",
    ]
    skills = [skill for skill in known_skills if skill.casefold() in text.casefold()]
    languages = [
        language
        for language in ["English", "Polish", "German", "French", "Spanish"]
        if language.casefold() in text.casefold()
    ]
    role_matches = re.findall(
        r"(?im)^.{0,45}(developer|engineer|architect|manager|consultant).{0,35}$",
        text,
    )
    target_roles = (
        [f"{role.title()} role" for role in _unique(role_matches)[:3]]
        if role_matches
        else ["Software Engineer"]
    )
    return ExtractedCvProfile(
        target_roles=target_roles,
        core_skills=skills[:8],
        other_skills=skills[8:],
        languages=languages,
    )


async def analyze_cv(
    user_id: int, filename: str, contents: bytes, current: Profile
) -> CvAnalysis:
    text = _extract_pdf_text(contents)
    warning = None
    mode = "local-fallback"

    if OPENAI_API_KEY:
        model = ChatOpenAI(model=OPENAI_MODEL, temperature=0)
        structured_model = model.with_structured_output(
            ExtractedCvProfile, include_raw=True
        )
        response = await structured_model.ainvoke(
            "Extract the candidate's likely target roles, strongest core technical "
            "skills, other relevant skills, and spoken languages from this CV. "
            "Return concise deduplicated lists. Do not infer unsupported facts.\n\n"
            f"CV:\n{text[:50000]}"
        )
        extracted = response["parsed"]
        raw = response.get("raw")
        usage = getattr(raw, "usage_metadata", None) or {}
        input_tokens = int(usage.get("input_tokens", 0))
        output_tokens = int(usage.get("output_tokens", 0))
        record_usage(
            user_id=user_id,
            operation="cv_analysis",
            model=OPENAI_MODEL,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=0,
        )
        mode = "ai"
    else:
        extracted = _fallback_cv_profile(text)
        warning = (
            "OPENAI_API_KEY is not configured. The CV was parsed with the local "
            "keyword fallback instead of an AI model."
        )

    profile = Profile(
        user_id=user_id,
        target_roles=_unique(extracted.target_roles) or current.target_roles,
        core_skills=_unique(extracted.core_skills) or current.core_skills,
        other_skills=_unique(extracted.other_skills),
        languages=_unique(extracted.languages) or current.languages,
        location=current.location,
        work_modes=current.work_modes,
        minimum_salary=current.minimum_salary,
        contract_types=current.contract_types,
        excluded_companies=current.excluded_companies,
        cv_filename=filename,
    )
    return CvAnalysis(profile=profile, analysis_mode=mode, warning=warning)


def build_search_query(profile: Profile, role: str | None = None) -> str:
    selected_role = role or (profile.target_roles[0] if profile.target_roles else "job")
    parts = [
        f'"{selected_role}"',
        " ".join(f'"{skill}"' for skill in profile.core_skills[:5]),
        profile.location,
        " ".join(profile.work_modes),
        " ".join(profile.contract_types),
        "hiring",
    ]
    return " ".join(part for part in parts if part).strip()


def _company_from_title(title: str) -> str:
    for separator in (" | ", " - ", " at "):
        if separator in title:
            return title.rsplit(separator, 1)[-1].strip()
    return "LinkedIn"


def _offer_page_text(result: dict) -> str:
    return " ".join(
        str(result.get(field) or "")
        for field in ("title", "content", "raw_content", "linkedin_page_content")
    ).strip()


def _canonical_linkedin_job_url(url: str) -> str | None:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").casefold()
    match = LINKEDIN_JOB_PATH.fullmatch(parsed.path)
    if (
        not (hostname == "linkedin.com" or hostname.endswith(".linkedin.com"))
        or match is None
        or "expired_jd_redirect" in parse_qs(parsed.query)
    ):
        return None
    return f"https://www.linkedin.com/jobs/view/{match.group('job_id')}"


def _resolve_job_url(url: str) -> tuple[str, str] | None:
    request = Request(
        url,
        method="GET",
        headers={"User-Agent": "Mozilla/5.0 (compatible; Recrbro/0.1)"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            canonical_url = _canonical_linkedin_job_url(response.geturl())
            if canonical_url is None:
                return None
            page_content = response.read(2_000_000).decode("utf-8", errors="ignore")
            return canonical_url, page_content
    except (HTTPError, URLError, TimeoutError, ValueError):
        return None


def _verify_job_detail_urls(
    results_by_url: dict[str, dict],
) -> tuple[dict[str, dict], int]:
    if not results_by_url:
        return {}, 0

    urls = list(results_by_url)
    with ThreadPoolExecutor(max_workers=min(8, len(urls))) as executor:
        resolved_urls = list(executor.map(_resolve_job_url, urls))

    verified: dict[str, dict] = {}
    for original_url, resolved in zip(urls, resolved_urls, strict=True):
        if resolved is None:
            continue
        resolved_url, page_content = resolved
        if resolved_url in verified:
            continue
        result = results_by_url[original_url]
        result["url"] = resolved_url
        result["linkedin_page_content"] = page_content
        verified[resolved_url] = result
    return verified, len(results_by_url) - len(verified)


def _is_active_offer(result: dict) -> bool:
    if not result.get("linkedin_page_content"):
        return False
    page_text = _offer_page_text(result).casefold()
    return not any(marker in page_text for marker in CLOSED_OFFER_MARKERS)


def _populate_missing_page_content(
    client: TavilyClient, results_by_url: dict[str, dict]
) -> None:
    missing_urls = [
        url for url, result in results_by_url.items() if not result.get("raw_content")
    ]
    for start in range(0, len(missing_urls), 20):
        response = client.extract(
            urls=missing_urls[start : start + 20],
            extract_depth="advanced",
            format="text",
            timeout=60,
        )
        for extracted in response.get("results", []):
            url = extracted.get("url")
            if url in results_by_url:
                results_by_url[url]["raw_content"] = extracted.get("raw_content") or ""


def _rank_offer(
    title: str, content: str, profile: Profile
) -> tuple[float, list[str], list[str]]:
    searchable = f"{title} {content}".casefold()
    matched_skills = [
        skill for skill in profile.core_skills if skill.casefold() in searchable
    ]
    reasons: list[str] = []
    score = 0.0

    if profile.core_skills:
        skill_ratio = len(matched_skills) / len(profile.core_skills)
        score += skill_ratio * 70
        if matched_skills:
            reasons.append(f"Matches {', '.join(matched_skills[:4])}")
    if profile.location and profile.location.casefold() in searchable:
        score += 12
        reasons.append(f"Location mentions {profile.location}")
    matched_modes = [
        mode for mode in profile.work_modes if mode.casefold() in searchable
    ]
    if matched_modes:
        score += 10
        reasons.append(f"Work mode: {', '.join(matched_modes)}")
    matched_contracts = [
        contract
        for contract in profile.contract_types
        if contract.casefold() in searchable
    ]
    if matched_contracts:
        score += 8
        reasons.append(f"Contract: {', '.join(matched_contracts)}")
    if not reasons:
        reasons.append("Matches the core search query")
    return min(round(score, 1), 100), matched_skills, reasons


def search_linkedin(
    profile: Profile, limit: int
) -> tuple[str, list[JobOffer], str | None]:
    if not TAVILY_API_KEY:
        raise RuntimeError(
            "TAVILY_API_KEY is not configured. Add it to .env to search live LinkedIn data."
        )

    client = TavilyClient(api_key=TAVILY_API_KEY)
    roles = profile.target_roles[:5] or ["job"]
    queries = [build_search_query(profile, role) for role in roles]
    results_by_url: dict[str, dict] = {}
    candidate_limit = min(max(limit * 3, 20), 100)

    for query in queries:
        remaining = candidate_limit - len(results_by_url)
        if remaining <= 0:
            break
        response = client.search(
            query=query,
            search_depth="advanced",
            max_results=min(20, max(remaining, 5)),
            include_domains=["linkedin.com"],
            topic="general",
            include_raw_content="text",
        )
        for result in response.get("results", []):
            url = result.get("url", "")
            if _canonical_linkedin_job_url(url) and url not in results_by_url:
                results_by_url[url] = result

    results_by_url, invalid_link_count = _verify_job_detail_urls(results_by_url)
    _populate_missing_page_content(client, results_by_url)

    excluded = {company.casefold() for company in profile.excluded_companies}
    offers: list[JobOffer] = []
    filtered_count = invalid_link_count
    for result in results_by_url.values():
        if not _is_active_offer(result):
            filtered_count += 1
            continue
        title = result.get("title") or "LinkedIn job offer"
        company = _company_from_title(title)
        if any(name in company.casefold() for name in excluded):
            continue
        content = result.get("raw_content") or result.get("content") or ""
        score, matched_skills, reasons = _rank_offer(title, content, profile)
        offers.append(
            JobOffer(
                title=title,
                company=company,
                url=result["url"],
                summary=content[:500],
                score=score,
                matched_skills=matched_skills,
                match_reasons=reasons,
            )
        )

    offers.sort(key=lambda offer: offer.score, reverse=True)
    warning = None
    if len(offers) < limit:
        filter_note = (
            f" {filtered_count} non-detail, closed, or unverifiable offers were removed."
            if filtered_count
            else ""
        )
        warning = (
            f"Tavily returned {len(offers)} unique LinkedIn job pages for this query; "
            f"the plan allows up to {limit}.{filter_note}"
        )
    return queries[0], offers[:limit], warning


def profile_update_from_profile(profile: Profile) -> ProfileUpdate:
    return ProfileUpdate.model_validate(
        profile.model_dump(exclude={"user_id", "cv_filename"})
    )
