# Production database user administration

These instructions apply to the SQLite database mounted at
`/data/recrbro.db` on the Railway API service.

Connect to the production API container:

```sh
railway link
railway ssh
```

Before making changes, create a backup:

```sh
cp /data/recrbro.db "/data/recrbro.db.backup-$(date +%Y%m%d-%H%M%S)"
```

Open the SQLite command-line interface:

```sh
uv run python -m sqlite3 /data/recrbro.db
```

## Drop all tables

Stop the API before resetting the database so it cannot read or write while the
schema is being recreated. This permanently deletes every user and all
application data.

Drop dependent tables before their parent tables:

```sql
PRAGMA foreign_keys = ON;
BEGIN;

DROP TABLE IF EXISTS job_offers;
DROP TABLE IF EXISTS user_offer_statuses;
DROP TABLE IF EXISTS usage_events;
DROP TABLE IF EXISTS balance_events;
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS profiles;
DROP TABLE IF EXISTS searches;
DROP TABLE IF EXISTS users;

COMMIT;
```

After dropping the tables, execute the complete schema below or restart the API.
The application calls its database initializer during startup and recreates all
tables automatically.

## Database schema

The application creates this schema when starting with a fresh database:

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT,
    plan TEXT NOT NULL CHECK (plan IN ('free', 'premium')),
    result_limit INTEGER NOT NULL,
    monthly_budget_pln REAL NOT NULL,
    credits_bought_usd REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CONSTRAINT fk_sessions_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS profiles (
    user_id INTEGER PRIMARY KEY,
    core_skills TEXT NOT NULL DEFAULT '[]',
    other_skills TEXT NOT NULL DEFAULT '[]',
    languages TEXT NOT NULL DEFAULT '[]',
    location TEXT NOT NULL DEFAULT '',
    work_modes TEXT NOT NULL DEFAULT '[]',
    minimum_salary INTEGER,
    contract_types TEXT NOT NULL DEFAULT '[]',
    excluded_companies TEXT NOT NULL DEFAULT '[]',
    additional_limitations TEXT NOT NULL DEFAULT '',
    cv_filename TEXT,
    updated_at TEXT NOT NULL,
    CONSTRAINT fk_profiles_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    query TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_results INTEGER NOT NULL DEFAULT 10,
    available_at TEXT NOT NULL DEFAULT '',
    claimed_at TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    plan_at_creation TEXT NOT NULL DEFAULT 'free',
    warning TEXT,
    error TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    CONSTRAINT fk_searches_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS job_offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id INTEGER NOT NULL,
    result_type TEXT NOT NULL DEFAULT 'job',
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    url TEXT NOT NULL,
    summary TEXT NOT NULL,
    score REAL NOT NULL,
    matched_skills TEXT NOT NULL,
    match_reasons TEXT NOT NULL,
    CONSTRAINT fk_job_offers_search
        FOREIGN KEY (search_id) REFERENCES searches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_offer_statuses (
    user_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    PRIMARY KEY (user_id, url),
    CONSTRAINT fk_user_offer_statuses_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS usage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    operation TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    CONSTRAINT fk_usage_events_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS balance_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    delta_credits REAL NOT NULL,
    amount_usd REAL,
    eur_usd_rate REAL,
    event_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    CONSTRAINT fk_balance_events_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

To inspect the schema of the installed database:

```sql
.schema
```

## Update a user to Premium

Replace `user@example.com` with the user's email address:

```sql
BEGIN;

UPDATE users
SET plan = 'premium',
    result_limit = 10
WHERE lower(email) = lower('user@example.com');

SELECT id, name, email, plan, result_limit
FROM users
WHERE lower(email) = lower('user@example.com');

COMMIT;
```

The update changes the user's plan but does not add credit
to the user's balance ledger.

## List all users

```sql
.headers on
.mode column

SELECT id,
       name,
       email,
       plan,
       result_limit,
       created_at
FROM users
ORDER BY id;
```

## Delete a user

Deleting a user is irreversible. Related sessions, profiles, searches, offers,
usage records, balance events, and application statuses are removed
through foreign-key cascades.

First verify the target:

```sql
SELECT id, name, email, plan
FROM users
WHERE lower(email) = lower('user@example.com');
```

Then delete it:

```sql
PRAGMA foreign_keys = ON;
BEGIN;

DELETE FROM users
WHERE lower(email) = lower('user@example.com');

SELECT changes() AS deleted_users;

COMMIT;
```

`deleted_users` must be `1`. If it is `0`, no matching user was found. If it is
greater than `1`, roll back instead of committing:

```sql
ROLLBACK;
```

Exit SQLite with:

```sql
.quit
```
