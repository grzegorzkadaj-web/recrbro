# Copilot instructions for `recrbro`

## Project overview

`recrbro` is a small Python application for helping job seekers discover relevant job offers from LinkedIn and other sources. The requirements describe a product that:

- lets users sign in or create an account,
- loads a CV/PDF and extracts skills and languages,
- accepts filtering criteria such as location, work mode, salary, and contract type,
- queues and runs job searches,
- presents results and tracks token cost.

The repository is a two-part production MVP: a FastAPI/LangGraph backend under
`src/recrbro` and a Next.js/CopilotKit frontend under `web`.

## Setup and commands

Use `uv` for dependency management and command execution, because the project is configured as a `uv`-managed Python package.

- Install dependencies: `uv sync`
- Run the API: `uv run recrbro`
- Build the package: `uv build`
- Format code: `uv run black .` and `uv run isort .`
- Run backend tests: `uv run pytest`
- Run one backend test: `uv run pytest tests/test_api.py -k free_search`
- Install frontend dependencies: `cd web; npm install`
- Run the frontend: `cd web; npm run dev`
- Type-check the frontend: `cd web; npm run lint`
- Build the frontend: `cd web; npm run build`

### Tests and linting

Backend API tests use `pytest` and FastAPI's `TestClient`. Frontend linting is a
strict TypeScript no-emit check rather than ESLint.

## Architecture

- `src/recrbro/api.py` is the FastAPI application and REST boundary.
- `src/recrbro/db.py` owns SQLite schema creation, seed data, and persistence.
- `src/recrbro/services.py` owns PDF extraction, optional AI CV analysis, Tavily
  search, and deterministic result ranking.
- `src/recrbro/auth.py` owns password hashing, opaque sessions, and Turnstile
  registration verification.
- `src/recrbro/agent.py` exposes the LangGraph agent through AG-UI at `/agent`.
- `web/app/api/copilotkit/route.ts` is the CopilotKit Runtime proxy between the
  browser and the Python AG-UI endpoint.
- `web/app/page.tsx` is a conventional controlled React dashboard. It exposes
  current profile/results through `useAgentContext` and narrowly scoped UI
  changes through `useFrontendTool`.
- SQLite is intentionally used for this local, single-process PoC. The database
  at `data/recrbro.db` is generated state and must not be committed. Production
  must remain a single API replica with the file on a persistent volume.

## Conventions and repository-specific patterns

- Keep the project Python 3.10+ compatible (`requires-python = ">=3.10"`).
- Prefer `uv` commands over raw `python`/`pip` to match the project toolchain.
- Keep environment and secrets handling separate from application logic.
- Use Tavily and the public CzyJestEldorado Remote MCP server as independent job
  sources. `TAVILY_API_KEY` enables broad web discovery and extraction;
  `CZYJESTELDORADO_MCP_URL` configures the Polish IT aggregator. Use
  `OPENAI_API_KEY` for the assistant, AI CV extraction, and AI validation of
  offer activity and location eligibility. Missing keys or unavailable sources
  must produce explicit errors or visibly labelled degraded behavior; never
  invent job data.
- Keep plan and credit enforcement in the backend. New users start Free and may
  run two queued searches with up to five results each and upload CVs. Premium
  can request up to ten immediate results. Credit balance comes from append-only
  balance events; AI USD cost is converted with the current EUR/USD rate and
  multiplied by `CREDIT_COST_MULTIPLIER` (default 10). Exhausted Free searches
  must not incur AI debt; use visibly labelled deterministic content checks.
- Never restore user-ID selection as an authorization mechanism. Production
  user data is accessed only through the authenticated `/api/profile`,
  `/api/searches` and `/api/usage` endpoints.
- The buycoffee.to widget is voluntary external support and must not
  automatically change a user's plan or credit balance.
- Keep the scheduled worker endpoint protected by `WORKER_SECRET`; worker
  failures must persist as failed searches rather than appearing successful.
- Store list-valued profile fields as JSON arrays in SQLite and expose them as
  typed arrays through the API.
- Search ranking gives core-skill matches the dominant weight, then location,
  work mode, and contract type. Preserve this ordering when tuning scores.
- Work mode is a typed array containing only `remote`, `on-site`, and `hybrid`.
- Search all suitable Tavily sources, not only LinkedIn. Individual offer URLs
  from employer sites and job boards are valid when their extracted content
  passes active-offer and location checks. Canonicalize each source sensibly
  and remove tracking parameters.
- Search candidates must be checked against extracted or directly fetched page
  content before persistence. Reject closed/expired markers such as "No longer
  accepting applications"; do not rely only on search-result snippets or MCP
  metadata.
- Resolve LinkedIn links before presenting them. The final location must remain
  a numeric `/jobs/view/{id}` page; reject redirects to `/jobs/*-jobs` listing
  pages, including URLs marked with `expired_jd_redirect`, and persist the
  canonical `https://www.linkedin.com/jobs/view/{id}` URL.
- Treat the directly fetched LinkedIn page as authoritative for active status,
  because Tavily snippets can omit LinkedIn's `closed-job` banner. Reject a
  result when the direct HTML contains a closed/expired marker even if Tavily's
  extracted content looks active.
- Treat the directly fetched CzyJestEldorado offer page as authoritative for
  active status; reject MCP candidates whose offer page cannot be fetched or
  contains a closed/expired marker.
- Never return collection/search pages as results. Extract individual offer links
  from collection pages, fetch their contents, and run them through the same
  active-status, criteria, ranking, and canonicalization checks as direct results.
- Use current CopilotKit v2 APIs from `@copilotkit/react-core/v2`; do not replace
  `useAgentContext`/`useFrontendTool` with deprecated v1 hooks.

## Working style expectations

When making changes:

- update the Python package under `src/recrbro`, not the repo root,
- keep feature additions aligned with the stated job-search use case,
- do not assume a large web app or multi-service architecture exists yet,
- prefer direct, obvious code that matches the minimal structure of the repository.
