# RecrBro

RecrBro is an authenticated job-search assistant that builds a candidate
profile, discovers live individual offers across job boards and employer sites
through Tavily, rejects inactive or location-ineligible offers, and ranks the
remaining roles against the candidate's requirements.

## Product behavior

- Email/password accounts and Google OAuth sign-in.
- New accounts start on Free. Free accounts can upload a PDF CV and run two
  queued searches with up to five results each.
- A verified 2 EUR Przelewy24/BLIK payment adds four credits and restores
  Premium. Premium searches run immediately and return up to ten offers.
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
- AI usage and estimated USD cost are stored per account. Premium CV extraction
  switches to the lower-cost model after tracked spend reaches 25 PLN.
- The dashboard separates the newest search from deduplicated archival offers.
  Starting a new search moves the prior current results into the archive.

## Architecture

- `src/recrbro/api.py`: FastAPI REST API, account boundary, search queue, worker
  endpoint, security headers, and payment callback.
- `src/recrbro/db.py`: SQLite schema, migrations, sessions, profiles, searches,
  offers, payments, and usage events.
- `src/recrbro/services.py`: PDF extraction, AI analysis, multi-source Tavily
  discovery, source-aware URL validation, and deterministic ranking. LinkedIn
  additionally receives authoritative direct-page validation.
- `src/recrbro/payments.py`: Przelewy24 registration and verification.
- `src/recrbro/notifications.py`: SMTP result delivery.
- `src/recrbro/agent.py`: LangGraph agent exposed over AG-UI.
- `web`: responsive Next.js 16 and CopilotKit interface.

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

Generate strong independent values for `APP_SECRET` and `WORKER_SECRET`. Set
`APP_ENV=production`, `SEED_DEMO_USERS=false`, the public frontend/API URLs,
`RECRBRO_DATABASE_PATH=/data/recrbro.db`, and all provider credentials listed
in `.env.example`.

For Google sign-in, register
`https://<api-host>/api/auth/google/callback` as an authorized redirect URI.
For Przelewy24, keep `P24_SANDBOX=true` until the merchant flow and callbacks
pass certification. The implementation uses the official transaction register
and verify flow documented at <https://developers.przelewy24.pl/>.

Configure SMTP to deliver Free-plan results. Without SMTP, the completed search
remains visible in the dashboard and carries an explicit delivery warning.
LangSmith tracing uses the standard `LANGSMITH_*` variables.

## Railway deployment

[Railway](https://docs.railway.com/) is the recommended initial host because it
supports Docker services, private networking, cron jobs, and a persistent
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
   `NEXT_PUBLIC_API_URL` as a build variable and `BACKEND_URL` as a runtime
   variable to the API's public HTTPS URL.
3. Set `FRONTEND_ORIGINS` on the API to the web service's exact HTTPS origin
   (for example, `https://web-production-web.up.railway.app`) and
   `PUBLIC_API_URL` to the API's exact HTTPS origin. Multiple allowed web
   origins can be comma-separated; the first is used for OAuth and payment
   redirects. The legacy singular `FRONTEND_ORIGIN` remains supported.
4. Add a Railway cron service that runs every 15 minutes and invokes:

   ```sh
   curl --fail-with-body --request POST \
     --header "X-Worker-Secret: $WORKER_SECRET" \
     "$PUBLIC_API_URL/api/internal/run-due-searches"
   ```

5. Map custom domains, update the Google and Przelewy24 callback URLs, run a
   sandbox payment, and verify `/health` before enabling production payments.
6. Back up `/data/recrbro.db` regularly. Railway volumes are persistent, but
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
