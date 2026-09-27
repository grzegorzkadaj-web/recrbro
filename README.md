# RecrBro

RecrBro is an authenticated job-search assistant that builds a candidate
profile, discovers live individual offers across job boards and employer sites
through Tavily, rejects inactive or location-ineligible offers, and ranks the
remaining roles against the candidate's requirements.

## Product behavior

- Email/password accounts with Cloudflare Turnstile-protected registration.
- New accounts start on Free with 0.1 credit. Free accounts can upload a PDF CV
  and run immediate searches with up to ten results each.
- A verified 2 EUR Przelewy24/BLIK payment adds four credits and restores
  Premium.
- Credit balance is an append-only event stream containing purchases and actual
  AI usage charges. AI cost is converted from USD to EUR using the free
  Frankfurter reference-rate API, then multiplied by the configurable
  `CREDIT_COST_MULTIPLIER` (default `10`). At zero, the backend switches the
  account to Free until another payment is verified. Authenticated clients can
  read the ledger through `GET /api/balance-history`.
- Profiles include core and optional skills, languages, location, exactly three
  work-mode choices (remote, on-site, hybrid),
  minimum salary, contract type, excluded companies, and high-priority
  free-text limitations.
- AI usage and estimated USD cost are stored per account. AI CV extraction
  switches to the lower-cost model after tracked spend reaches 25 PLN.
- The dashboard separates the newest search from deduplicated archival offers.
  Starting a new search moves the prior current results into the archive.

## Architecture

- `src/recrbro/api.py`: FastAPI REST API, account boundary, live search
  execution, security headers, and payment callback.
- `src/recrbro/db.py`: SQLite schema, migrations, sessions, profiles, searches,
  offers, payments, and usage events.
- `src/recrbro/services.py`: PDF extraction, AI analysis, multi-source Tavily
  discovery, source-aware URL validation, and deterministic ranking. LinkedIn
  additionally receives authoritative direct-page validation.
- `src/recrbro/payments.py`: Przelewy24 registration and verification.
- `src/recrbro/agent.py`: LangGraph agent exposed over AG-UI.
- `web`: responsive Next.js 16 and CopilotKit interface.

### AI model usage

The backend uses OpenAI models at three points:

- The CopilotKit/LangGraph assistant uses `OPENAI_MODEL`.
- CV extraction uses `OPENAI_MODEL` until the account's tracked AI spend reaches
  25 PLN, then switches to `OPENAI_JOB_ANALYSIS_MODEL`. If AI is unavailable or
  the account has no credit, CV extraction uses the visibly labelled local
  keyword fallback.
- Offer validation, location and criteria eligibility, match percentage, and
  fit/gap explanations use `OPENAI_JOB_ANALYSIS_MODEL`.

Model names and accounting rates are configured through the backend
environment:

| Variable | Default | Effect |
| --- | --- | --- |
| `OPENAI_MODEL` | `gpt-4.1-mini` | Selects the conversational assistant and the primary CV extraction model. |
| `OPENAI_JOB_ANALYSIS_MODEL` | `gpt-5-nano` | Selects the structured offer-analysis model and the lower-cost CV model used after the 25 PLN threshold. |
| `OPENAI_INPUT_COST_PER_MILLION` | `0.40` | Input-token USD rate used to estimate usage for `OPENAI_MODEL`, and for `OPENAI_JOB_ANALYSIS_MODEL` when it is not `gpt-5-nano`. |
| `OPENAI_OUTPUT_COST_PER_MILLION` | `1.60` | Output-token USD rate used in the same accounting paths. |

Changing a model changes latency, token usage, provider cost, and result quality.
A larger model may improve CV field extraction, ambiguous location/eligibility
decisions, and match explanations, but usually costs more and may respond more
slowly. A smaller model generally reduces credit consumption and latency, but
may produce less consistent structured classifications or lower-quality
ranking explanations. The selected offer-analysis model must support the
structured-output options used by the application.

Whenever either model is changed, verify the current provider price and update
`OPENAI_INPUT_COST_PER_MILLION` and `OPENAI_OUTPUT_COST_PER_MILLION` to match.
Otherwise the stored USD usage cost and the credits charged to users will be
incorrect. The default `gpt-5-nano` job-analysis rates are handled explicitly
as `0.05` USD input and `0.40` USD output per million tokens; any other
`OPENAI_JOB_ANALYSIS_MODEL` uses the two configurable rates above. Restart the
API after changing these variables.

SQLite remains appropriate for this small, single-instance deployment. Do not
run more than one API replica against the database file. Move to PostgreSQL
before horizontal scaling.

## Local setup

Requirements: Python 3.10+, [uv](https://docs.astral.sh/uv/), Node.js 20.9+,
Tavily credentials, and OpenAI credentials.

```powershell
Copy-Item .env.example .env
uv sync
uv run recrbro
```

In another terminal:

```powershell
Set-Location web
Copy-Item .env.local.example .env.local
npm ci
npm run dev
```

Open <http://localhost:3000>. API documentation is at
<http://127.0.0.1:8000/docs>.

`SEED_DEMO_USERS=true` preserves the two old local demo records for API
regression tests, but the website uses real accounts. Set it to `false` outside
local development.

## Required production configuration

Generate a strong value for `APP_SECRET`. Set `APP_ENV=production`,
`SEED_DEMO_USERS=false`, the public frontend/API URLs,
`RECRBRO_DATABASE_PATH=/data/recrbro.db`, and all provider credentials listed
in `.env.example`.

Create a Cloudflare Turnstile widget for the frontend hostname. Set its site key
as `NEXT_PUBLIC_TURNSTILE_SITE_KEY` on the web service and its secret key as
`TURNSTILE_SECRET_KEY` on the API service. Registration is unavailable when
either side is not configured. The example environment files use Cloudflare's
official always-pass test keys for local development; replace both keys in
production.
For Przelewy24, keep `P24_SANDBOX=true` until the merchant flow and callbacks
pass certification. The implementation uses the official transaction register
and verify flow documented at <https://developers.przelewy24.pl/>.

Search results for every plan are persisted and presented directly in the
website dashboard. Eligible offers are ranked by an AI-generated match
percentage against the complete candidate profile, with the AI's concise fit
and gap explanation shown on each result. LangSmith tracing uses the standard
`LANGSMITH_*` variables.

## Railway deployment

[Railway](https://docs.railway.com/) is the recommended initial host because it
supports Docker services, private networking, and a persistent
volume for the single SQLite writer.

1. Create an API service from this repository using the root `Dockerfile`.
   Leave the Railway service root directory empty and use `Dockerfile` as the
   Dockerfile path. Do not set the path to `/Dockerfile`.
   Attach a volume at `/data`, set `RECRBRO_DATABASE_PATH=/data/recrbro.db`, and
   configure the backend variables from `.env.example`.
2. Create a web service with its Railway root directory set to `/web`. Use
   `Dockerfile` as the Dockerfile path because paths are resolved relative to
   the configured service root; do not use `web/Dockerfile` together with a
   `/web` root directory. Set
   `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_TURNSTILE_SITE_KEY` as build variables,
   and `BACKEND_URL` as a runtime variable pointing to the API's public HTTPS
   URL.
3. Set `FRONTEND_ORIGINS` on the API to the web service's exact HTTPS origin
   (for example, `https://web-production-web.up.railway.app`) and
   `PUBLIC_API_URL` to the API's exact HTTPS origin. Multiple allowed web
   origins can be comma-separated; the first is used for payment
   redirects. The legacy singular `FRONTEND_ORIGIN` remains supported.
4. Map custom domains, update the Turnstile hostname and Przelewy24 callback
   URLs, run a sandbox payment, and verify `/health` before enabling production
   payments.
5. Back up `/data/recrbro.db` regularly. Railway volumes are persistent, but
   application-level backup and restore drills remain your responsibility.

Railway volume guidance:
<https://docs.railway.com/reference/volumes>. For larger traffic or multiple API
replicas, migrate to managed PostgreSQL rather than sharing SQLite.

## Validation

```powershell
uv run pytest
uv run black --check --target-version py310 src tests
uv run isort --check-only src tests
uv build

Set-Location web
npm run lint
npm run build
```
