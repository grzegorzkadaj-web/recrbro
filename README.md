# Recrbro proof of concept

Recrbro is a local proof-of-concept website that builds a candidate profile from
a CV, searches live LinkedIn job pages through Tavily, and ranks results against
the candidate's core and optional criteria. The dashboard includes a CopilotKit
assistant for refining the visible search profile.

## Architecture

- **FastAPI** provides user, profile, CV, usage, and job-search APIs.
- **SQLite** stores the two demo users, profiles, searches, offers, and AI usage.
- **Tavily** runs several focused searches for skill and role variants, merges
  and deduplicates the results, and retrieves current LinkedIn job-page content.
  Each candidate is also fetched directly from LinkedIn and rejected when the
  current page says applications are closed or when LinkedIn redirects to a
  job-list page. When LinkedIn blocks a direct request, a canonical detail URL
  may use Tavily-extracted content as an explicitly labelled fallback. Valid
  links are stored as clean
  `linkedin.com/jobs/view/{job-id}` detail URLs before deduplication, excluded
  company filtering, and local ranking.
- **LangGraph + CopilotKit** provide the embedded search assistant.
- **Next.js** renders the dashboard and proxies CopilotKit runtime traffic to
  the Python agent.

SQLite was selected because this is a single-process local PoC and its data is
relational. The default database is created at `data/recrbro.db`.

## Prerequisites

- Python 3.10 or newer
- [uv](https://docs.astral.sh/uv/)
- Node.js 20.9 or newer
- Tavily API key for live job searches
- OpenAI API key for CopilotKit chat, AI CV extraction, and job validation

## Configure

Copy `.env.example` to `.env` and set:

```dotenv
TAVILY_API_KEY=tvly-...
OPENAI_API_KEY=sk-...
OPENAI_JOB_ANALYSIS_MODEL=gpt-5-nano
```

Without `TAVILY_API_KEY`, search returns an explicit configuration error.
Without `OPENAI_API_KEY`, the supplied CV can still be parsed using a visibly
labelled local keyword fallback, but chat and job searches are unavailable.
Job searches use the low-cost `gpt-5-nano` model by default to reject inactive
offers and offers that do not allow working from the requested location.

The sample CV is `data/cv/CV Grzegorz Kadaj en.pdf`.

## Run locally

Install Python dependencies and start the API:

```powershell
uv sync
uv run recrbro
```

In another terminal, install and start the website:

```powershell
Set-Location web
Copy-Item .env.local.example .env.local
npm install
npm run dev
```

Open <http://localhost:3000>. API documentation is available at
<http://127.0.0.1:8000/docs>.

The database seeds two selectable users:

- `Free demo`: five results per search; CV analysis disabled.
- `Premium demo`: up to 100 requested results; CV analysis enabled.

When there are not enough verified individual offers, the search automatically
opens matching LinkedIn collection/search pages, extracts their individual job
links, and runs those jobs through the same activity, location, and ranking
checks. Collection pages themselves are not presented as offers.

When fewer offers are found than requested, the response warning includes
discovery diagnostics such as query count, duplicates, unresolved links,
inactive offers, location mismatches, and Tavily-content fallbacks.

For the PoC, both plans run searches immediately. Scheduled Free-plan execution,
email delivery, authentication, and payments remain outside the prototype.

## Checks

```powershell
uv run pytest
uv run pytest tests/test_api.py -k free_search
uv run black --check src tests
uv run isort --check-only src tests

Set-Location web
npm run lint
npm run build
```
