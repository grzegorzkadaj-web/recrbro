from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from recrbro.config import (
    CREDIT_COST_MULTIPLIER,
    DATABASE_PATH,
    FREE_STARTING_CREDITS,
    SEED_DEMO_USERS,
)
from recrbro.currency import eur_usd_rate, usd_to_eur
from recrbro.models import (
    BalanceEvent,
    JobOffer,
    Profile,
    ProfileUpdate,
    SearchJob,
    SearchResults,
    UsageSummary,
    User,
)

LIST_FIELDS = {
    "core_skills",
    "other_skills",
    "languages",
    "work_modes",
    "contract_types",
    "excluded_companies",
}
STALE_SEARCH_MINUTES = 15


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fail_stale_searches(
    database: sqlite3.Connection, user_id: int | None = None
) -> None:
    stale_before = (
        datetime.now(timezone.utc) - timedelta(minutes=STALE_SEARCH_MINUTES)
    ).isoformat()
    user_filter = " AND user_id = ?" if user_id is not None else ""
    parameters: tuple[object, ...] = (
        (_now(), stale_before, user_id)
        if user_id is not None
        else (_now(), stale_before)
    )
    database.execute(
        f"""
        UPDATE searches
        SET status = 'failed',
            error = 'Search was interrupted before completion.',
            completed_at = ?
        WHERE status = 'running' AND created_at < ?{user_filter}
        """,
        parameters,
    )


@contextmanager
def connection(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = path or DATABASE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(path)
    database.row_factory = sqlite3.Row
    database.execute("PRAGMA foreign_keys = ON")
    try:
        yield database
        database.commit()
    finally:
        database.close()


def initialize_database() -> None:
    with connection() as database:
        database.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT,
                plan TEXT NOT NULL CHECK (plan IN ('free', 'premium')),
                result_limit INTEGER NOT NULL,
                monthly_budget_pln REAL NOT NULL,
                credits_bought_usd REAL NOT NULL DEFAULT 0,
                terms_accepted_at TEXT,
                terms_version TEXT,
                privacy_accepted_at TEXT,
                privacy_policy_version TEXT,
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

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_id TEXT NOT NULL UNIQUE,
                order_id INTEGER,
                amount_grosz INTEGER NOT NULL,
                currency TEXT NOT NULL DEFAULT 'EUR',
                method TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                CONSTRAINT fk_payments_user
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
            """)
        user_columns = {
            row["name"] for row in database.execute("PRAGMA table_info(users)")
        }
        if "password_hash" not in user_columns:
            database.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        if "credits_bought_usd" not in user_columns:
            database.execute(
                "ALTER TABLE users ADD COLUMN credits_bought_usd REAL NOT NULL DEFAULT 0"
            )
            database.execute(
                """
                UPDATE users
                SET credits_bought_usd = CASE WHEN plan = 'premium' THEN 1 ELSE 0 END
                """,
            )
        for column, definition in (
            ("terms_accepted_at", "TEXT"),
            ("terms_version", "TEXT"),
            ("privacy_accepted_at", "TEXT"),
            ("privacy_policy_version", "TEXT"),
        ):
            if column not in user_columns:
                database.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
        profile_columns = {
            row["name"] for row in database.execute("PRAGMA table_info(profiles)")
        }
        if "additional_limitations" not in profile_columns:
            database.execute(
                "ALTER TABLE profiles ADD COLUMN additional_limitations TEXT NOT NULL DEFAULT ''"
            )
        search_columns = {
            row["name"] for row in database.execute("PRAGMA table_info(searches)")
        }
        for statement in (
            (
                "requested_results",
                "ALTER TABLE searches ADD COLUMN requested_results INTEGER NOT NULL DEFAULT 10",
            ),
            (
                "available_at",
                "ALTER TABLE searches ADD COLUMN available_at TEXT NOT NULL DEFAULT ''",
            ),
            ("error", "ALTER TABLE searches ADD COLUMN error TEXT"),
            ("completed_at", "ALTER TABLE searches ADD COLUMN completed_at TEXT"),
            ("claimed_at", "ALTER TABLE searches ADD COLUMN claimed_at TEXT"),
            (
                "attempts",
                "ALTER TABLE searches ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0",
            ),
            (
                "plan_at_creation",
                "ALTER TABLE searches ADD COLUMN plan_at_creation TEXT NOT NULL DEFAULT 'legacy'",
            ),
        ):
            if statement[0] not in search_columns:
                database.execute(statement[1])
        offer_columns = {
            row["name"] for row in database.execute("PRAGMA table_info(job_offers)")
        }
        if "result_type" not in offer_columns:
            database.execute(
                "ALTER TABLE job_offers ADD COLUMN result_type TEXT NOT NULL DEFAULT 'job'"
            )
        database.execute("""
            DELETE FROM job_offers
            WHERE result_type != 'job'
               OR (
                    lower(url) LIKE '%linkedin.com/jobs/%'
                    AND lower(url) NOT LIKE '%linkedin.com/jobs/view/%'
               )
               OR lower(url) LIKE '%indeed.com/q-%-jobs.html%'
               OR lower(url) LIKE '%glassdoor.com/job/%-jobs-srch_%'
               OR lower(url) LIKE '%/jobs'
               OR lower(url) LIKE '%/jobs/search%'
               OR lower(url) LIKE '%/careers'
               OR lower(url) LIKE '%/vacancies'
            """)
        _fail_stale_searches(database)
        payment_columns = {
            row["name"] for row in database.execute("PRAGMA table_info(payments)")
        }
        if "currency" not in payment_columns:
            database.execute(
                "ALTER TABLE payments ADD COLUMN currency TEXT NOT NULL DEFAULT 'PLN'"
            )
        if SEED_DEMO_USERS:
            seed_users = [
                (1, "Free demo", "free@recrbro.local", "free", 10, 0, 0),
                (
                    2,
                    "Premium demo",
                    "premium@recrbro.local",
                    "premium",
                    10,
                    0,
                    4,
                ),
            ]
            database.executemany(
                """
                INSERT OR IGNORE INTO users
                    (id, name, email, plan, result_limit, monthly_budget_pln,
                     credits_bought_usd, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [(*user, _now()) for user in seed_users],
            )
            for user_id in (1, 2):
                _insert_default_profile(database, user_id, seeded=True)
        database.execute("""
            UPDATE users
            SET result_limit = 10
            WHERE result_limit != 10
            """)
        _backfill_balance_events(database)


def _insert_default_profile(
    database: sqlite3.Connection, user_id: int, seeded: bool = False
) -> None:
    database.execute(
        """
        INSERT OR IGNORE INTO profiles
            (user_id, core_skills, other_skills, languages,
             location, work_modes, contract_types, excluded_companies,
             additional_limitations, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            json.dumps(["Python"] if seeded else []),
            json.dumps([]),
            json.dumps(["English"] if seeded else []),
            "Poland" if seeded else "",
            json.dumps(["remote", "hybrid"] if seeded else []),
            json.dumps(["B2B", "employment"] if seeded else []),
            json.dumps([]),
            "",
            _now(),
        ),
    )


def _backfill_balance_events(database: sqlite3.Connection) -> None:
    rows = database.execute("""
        SELECT users.id, users.credits_bought_usd,
               COALESCE(SUM(usage_events.cost_usd), 0) AS cost_usd
        FROM users
        LEFT JOIN usage_events ON usage_events.user_id = users.id
        GROUP BY users.id
        """).fetchall()
    for row in rows:
        existing = database.execute(
            "SELECT 1 FROM balance_events WHERE user_id = ? LIMIT 1",
            (row["id"],),
        ).fetchone()
        if existing:
            continue
        if row["credits_bought_usd"]:
            database.execute(
                """
                INSERT INTO balance_events
                    (user_id, event_type, delta_credits, event_key, created_at)
                VALUES (?, 'opening_credit', ?, ?, ?)
                """,
                (
                    row["id"],
                    row["credits_bought_usd"],
                    f"opening-credit:{row['id']}",
                    _now(),
                ),
            )
        if row["cost_usd"]:
            database.execute(
                """
                INSERT INTO balance_events
                    (user_id, event_type, delta_credits, amount_usd, event_key, created_at)
                VALUES (?, 'legacy_ai_usage', ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    -round(row["cost_usd"] * 4, 8),
                    row["cost_usd"],
                    f"legacy-ai-usage:{row['id']}",
                    _now(),
                ),
            )


def _profile_from_row(row: sqlite3.Row) -> Profile:
    values = dict(row)
    for field in LIST_FIELDS:
        values[field] = json.loads(values[field])
    values.pop("updated_at", None)
    return Profile.model_validate(values)


def _reconcile_credit_state(
    database: sqlite3.Connection, user_id: int | None = None
) -> None:
    parameters: tuple[object, ...] = ()
    user_filter = ""
    if user_id is not None:
        user_filter = "AND users.id = ?"
        parameters = (user_id,)
    exhausted = database.execute(
        f"""
        SELECT users.id
        FROM users
        LEFT JOIN balance_events ON balance_events.user_id = users.id
        GROUP BY users.id
        HAVING users.plan = 'premium'
           AND ROUND(COALESCE(SUM(balance_events.delta_credits), 0), 2) <= 0
           {user_filter}
        """,
        parameters,
    ).fetchall()
    if exhausted:
        database.executemany(
            "UPDATE users SET plan = 'free', result_limit = 10 WHERE id = ?",
            [(row["id"],) for row in exhausted],
        )


def list_users() -> list[User]:
    with connection() as database:
        _reconcile_credit_state(database)
        rows = database.execute("""
            SELECT u.*,
                   COALESCE((SELECT SUM(cost_usd) FROM usage_events
                             WHERE user_id = u.id), 0) AS tracked_cost_usd,
                   COALESCE((SELECT SUM(delta_credits) FROM balance_events
                             WHERE user_id = u.id
                               AND event_type IN ('opening_credit', 'purchase')), 0)
                       AS credits_bought,
                   MAX(ROUND(COALESCE((SELECT SUM(delta_credits)
                                      FROM balance_events
                                      WHERE user_id = u.id), 0), 2), 0)
                       AS available_credits
            FROM users u
            ORDER BY u.id
            """).fetchall()
    return [User.model_validate(dict(row)) for row in rows]


def get_user(user_id: int) -> User | None:
    return next((user for user in list_users() if user.id == user_id), None)


def get_user_by_email(
    email: str, include_password: bool = False
) -> User | tuple[User, str | None] | None:
    with connection() as database:
        _reconcile_credit_state(database)
        row = database.execute(
            """
            SELECT u.*,
                   COALESCE((SELECT SUM(cost_usd) FROM usage_events
                             WHERE user_id = u.id), 0) AS tracked_cost_usd,
                   COALESCE((SELECT SUM(delta_credits) FROM balance_events
                             WHERE user_id = u.id
                               AND event_type IN ('opening_credit', 'purchase')), 0)
                       AS credits_bought,
                   MAX(ROUND(COALESCE((SELECT SUM(delta_credits)
                                      FROM balance_events
                                      WHERE user_id = u.id), 0), 2), 0)
                       AS available_credits
            FROM users u WHERE u.email = ?
            """,
            (email,),
        ).fetchone()
    if row is None:
        return None
    values = dict(row)
    password_hash = values.pop("password_hash", None)
    values.pop("google_subject", None)
    user = User.model_validate(values)
    return (user, password_hash) if include_password else user


def create_user(
    name: str,
    email: str,
    password_hash: str | None = None,
    *,
    terms_version: str | None = None,
    privacy_policy_version: str | None = None,
) -> User:
    with connection() as database:
        accepted_at = (
            _now()
            if terms_version is not None and privacy_policy_version is not None
            else None
        )
        cursor = database.execute(
            """
            INSERT INTO users
                (name, email, password_hash, plan, result_limit,
                 monthly_budget_pln, credits_bought_usd, terms_accepted_at,
                 terms_version, privacy_accepted_at, privacy_policy_version,
                 created_at)
            VALUES (?, ?, ?, 'free', 10, 0, 0, ?, ?, ?, ?, ?)
            """,
            (
                name,
                email,
                password_hash,
                accepted_at,
                terms_version,
                accepted_at,
                privacy_policy_version,
                _now(),
            ),
        )
        user_id = int(cursor.lastrowid)
        _record_balance_event(
            database,
            user_id,
            "starter_credit",
            FREE_STARTING_CREDITS,
            f"starter-credit:{user_id}",
        )
        _insert_default_profile(database, user_id)
    user = get_user(user_id)
    if user is None:
        raise LookupError("Created user could not be loaded.")
    return user


def create_session(user_id: int, token_hash: str, expires_at: datetime) -> None:
    with connection() as database:
        database.execute(
            """
            INSERT INTO sessions (token_hash, user_id, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (token_hash, user_id, expires_at.isoformat(), _now()),
        )


def user_for_session(token: str) -> User | None:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with connection() as database:
        row = database.execute(
            """
            SELECT user_id FROM sessions
            WHERE token_hash = ? AND expires_at > ?
            """,
            (token_hash, _now()),
        ).fetchone()
    return get_user(int(row["user_id"])) if row else None


def delete_session(token: str) -> None:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with connection() as database:
        database.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))


def get_profile(user_id: int) -> Profile | None:
    with connection() as database:
        row = database.execute(
            "SELECT * FROM profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
    return _profile_from_row(row) if row else None


def update_profile(
    user_id: int, profile: ProfileUpdate, cv_filename: str | None = None
) -> Profile:
    values = profile.model_dump()
    with connection() as database:
        database.execute(
            """
            UPDATE profiles SET
                core_skills = ?, other_skills = ?, languages = ?,
                location = ?, work_modes = ?, minimum_salary = ?, contract_types = ?,
                excluded_companies = ?, additional_limitations = ?,
                cv_filename = COALESCE(?, cv_filename), updated_at = ?
            WHERE user_id = ?
            """,
            (
                json.dumps(values["core_skills"]),
                json.dumps(values["other_skills"]),
                json.dumps(values["languages"]),
                values["location"],
                json.dumps(values["work_modes"]),
                values["minimum_salary"],
                json.dumps(values["contract_types"]),
                json.dumps(values["excluded_companies"]),
                values["additional_limitations"],
                cv_filename,
                _now(),
                user_id,
            ),
        )
    updated = get_profile(user_id)
    if updated is None:
        raise LookupError(f"Profile for user {user_id} does not exist")
    return updated


def create_search(
    user_id: int,
    query: str,
    requested_results: int = 10,
    status: str = "running",
    available_at: datetime | None = None,
) -> int:
    available = available_at or datetime.now(timezone.utc)
    with connection() as database:
        _fail_stale_searches(database, user_id)
        user = database.execute(
            "SELECT plan FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if user is None:
            raise LookupError("User not found.")
        cursor = database.execute(
            """
            INSERT INTO searches
                (user_id, query, status, requested_results, available_at,
                 plan_at_creation, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                query,
                status,
                requested_results,
                available.isoformat(),
                user["plan"],
                _now(),
            ),
        )
        return int(cursor.lastrowid)


def complete_search(
    search_id: int, offers: list[JobOffer], warning: str | None = None
) -> None:
    with connection() as database:
        unique_offers = list({str(offer.url): offer for offer in offers}.values())
        database.executemany(
            """
            INSERT INTO job_offers
                (search_id, result_type, title, company, url, summary, score,
                 matched_skills, match_reasons)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    search_id,
                    offer.result_type,
                    offer.title,
                    offer.company,
                    str(offer.url),
                    offer.summary,
                    offer.score,
                    json.dumps(offer.matched_skills),
                    json.dumps(offer.match_reasons),
                )
                for offer in unique_offers
            ],
        )
        database.execute(
            """
            UPDATE searches
            SET status = 'complete', warning = ?, completed_at = ?
            WHERE id = ?
            """,
            (warning, _now(), search_id),
        )


def fail_search(search_id: int, error: str) -> None:
    with connection() as database:
        database.execute(
            """
            UPDATE searches
            SET status = 'failed', error = ?, completed_at = ?
            WHERE id = ?
            """,
            (error, _now(), search_id),
        )


def append_search_warning(search_id: int, warning: str) -> None:
    with connection() as database:
        database.execute(
            """
            UPDATE searches
            SET warning = CASE
                WHEN warning IS NULL OR warning = '' THEN ?
                ELSE warning || ' ' || ?
            END
            WHERE id = ?
            """,
            (warning, warning, search_id),
        )


def _search_from_row(database: sqlite3.Connection, row: sqlite3.Row) -> SearchJob:
    offers = database.execute(
        """
        SELECT job_offers.*, user_offer_statuses.applied_at IS NOT NULL AS applied
        FROM job_offers
        LEFT JOIN user_offer_statuses
          ON user_offer_statuses.user_id = ?
         AND user_offer_statuses.url = job_offers.url
        WHERE job_offers.search_id = ?
        ORDER BY score DESC, id
        """,
        (row["user_id"], row["id"]),
    ).fetchall()
    return SearchJob(
        id=row["id"],
        status=row["status"],
        requested_results=row["requested_results"],
        query=row["query"],
        warning=row["warning"],
        error=row["error"],
        available_at=row["available_at"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
        offers=[
            JobOffer.model_validate(
                {
                    **dict(offer),
                    "matched_skills": json.loads(offer["matched_skills"]),
                    "match_reasons": json.loads(offer["match_reasons"]),
                }
            )
            for offer in offers
        ],
    )


def get_search(search_id: int, user_id: int | None = None) -> SearchJob | None:
    with connection() as database:
        _fail_stale_searches(database, user_id)
        if user_id is None:
            row = database.execute(
                "SELECT * FROM searches WHERE id = ?", (search_id,)
            ).fetchone()
        else:
            row = database.execute(
                "SELECT * FROM searches WHERE id = ? AND user_id = ?",
                (search_id, user_id),
            ).fetchone()
        return _search_from_row(database, row) if row else None


def get_search_results(user_id: int) -> SearchResults:
    with connection() as database:
        _fail_stale_searches(database, user_id)
        rows = database.execute(
            """
            SELECT * FROM searches
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,),
        ).fetchall()
        if not rows:
            return SearchResults()
        current = _search_from_row(database, rows[0])
        seen: set[str] = set()
        archival: list[JobOffer] = []
        for row in rows[1:]:
            if row["status"] != "complete":
                continue
            for offer in _search_from_row(database, row).offers:
                url = str(offer.url)
                if url in seen:
                    continue
                seen.add(url)
                archival.append(offer)
    return SearchResults(current=current, archival=archival)


def mark_offer_applied(user_id: int, offer_id: int) -> bool:
    with connection() as database:
        offer = database.execute(
            """
            SELECT job_offers.url, job_offers.result_type
            FROM job_offers
            JOIN searches ON searches.id = job_offers.search_id
            WHERE job_offers.id = ? AND searches.user_id = ?
            """,
            (offer_id, user_id),
        ).fetchone()
        if offer is None:
            return False
        database.execute(
            """
            INSERT INTO user_offer_statuses (user_id, url, applied_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, url) DO UPDATE SET applied_at = excluded.applied_at
            """,
            (user_id, offer["url"], _now()),
        )
    return True


def search_owner_and_profile(search_id: int) -> tuple[User, Profile, SearchJob] | None:
    with connection() as database:
        row = database.execute(
            "SELECT user_id FROM searches WHERE id = ?", (search_id,)
        ).fetchone()
    if row is None:
        return None
    user = get_user(int(row["user_id"]))
    profile = get_profile(int(row["user_id"]))
    search = get_search(search_id)
    if user is None or profile is None or search is None:
        return None
    return user, profile, search


def create_payment(
    user_id: int,
    session_id: str,
    amount_grosz: int,
    method: str,
    currency: str = "EUR",
) -> int:
    with connection() as database:
        cursor = database.execute(
            """
            INSERT INTO payments
                (user_id, session_id, amount_grosz, currency, method, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
            """,
            (user_id, session_id, amount_grosz, currency, method, _now()),
        )
        return int(cursor.lastrowid)


def complete_payment(session_id: str, order_id: int) -> None:
    with connection() as database:
        row = database.execute(
            """
            SELECT id, user_id, amount_grosz, currency, status
            FROM payments WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            raise LookupError("Payment not found.")
        if row["status"] == "complete":
            return
        database.execute(
            """
            UPDATE payments
            SET status = 'complete', order_id = ?, completed_at = ?
            WHERE session_id = ?
            """,
            (order_id, _now(), session_id),
        )
        database.execute(
            """
            UPDATE users
            SET plan = 'premium',
                result_limit = 10
            WHERE id = ?
            """,
            (row["user_id"],),
        )
        _record_balance_event(
            database,
            row["user_id"],
            "purchase",
            4,
            f"payment:{row['id']}",
        )


def get_payment(session_id: str) -> dict[str, object] | None:
    with connection() as database:
        row = database.execute(
            "SELECT * FROM payments WHERE session_id = ?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


def record_usage(
    user_id: int,
    operation: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
) -> None:
    rate = eur_usd_rate() if cost_usd > 0 else None
    credit_cost = (
        round(usd_to_eur(cost_usd, rate) * CREDIT_COST_MULTIPLIER, 8)
        if rate is not None
        else 0
    )
    with connection() as database:
        cursor = database.execute(
            """
            INSERT INTO usage_events
                (user_id, operation, model, input_tokens, output_tokens, cost_usd, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, operation, model, input_tokens, output_tokens, cost_usd, _now()),
        )
        usage_id = int(cursor.lastrowid)
        if credit_cost:
            _record_balance_event(
                database,
                user_id,
                "ai_usage",
                -credit_cost,
                f"usage:{usage_id}",
                amount_usd=cost_usd,
                rate=rate,
            )
        _reconcile_credit_state(database, user_id)


def ensure_available_credit(user_id: int) -> None:
    user = get_user(user_id)
    if user is None:
        raise LookupError("User not found.")
    if user.available_credits <= 0:
        with connection() as database:
            database.execute(
                "UPDATE users SET plan = 'free', result_limit = 10 WHERE id = ?",
                (user_id,),
            )
        raise RuntimeError(
            "Available AI credits are exhausted. Buy more credits to restore Premium."
        )


def usage_summary(user_id: int) -> UsageSummary:
    with connection() as database:
        _reconcile_credit_state(database, user_id)
        row = database.execute(
            """
            SELECT COALESCE((SELECT SUM(input_tokens) FROM usage_events
                             WHERE user_id = users.id), 0) AS input_tokens,
                   COALESCE((SELECT SUM(output_tokens) FROM usage_events
                             WHERE user_id = users.id), 0) AS output_tokens,
                   COALESCE((SELECT SUM(cost_usd) FROM usage_events
                             WHERE user_id = users.id), 0) AS cost_usd,
                   COALESCE((SELECT SUM(delta_credits) FROM balance_events
                             WHERE user_id = users.id
                               AND event_type IN ('opening_credit', 'purchase')), 0)
                       AS credits_bought,
                   MAX(ROUND(COALESCE((SELECT SUM(delta_credits)
                                      FROM balance_events
                                      WHERE user_id = users.id), 0), 2), 0)
                       AS available_credits
            FROM users WHERE users.id = ?
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        raise LookupError("User not found.")
    return UsageSummary.model_validate(dict(row))


def list_balance_events(user_id: int) -> list[BalanceEvent]:
    with connection() as database:
        rows = database.execute(
            """
            SELECT id, event_type, delta_credits, amount_usd, eur_usd_rate, created_at
            FROM balance_events
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,),
        ).fetchall()
    return [BalanceEvent.model_validate(dict(row)) for row in rows]


def _record_balance_event(
    database: sqlite3.Connection,
    user_id: int,
    event_type: str,
    delta_credits: float,
    event_key: str,
    amount_usd: float | None = None,
    rate: float | None = None,
) -> None:
    database.execute(
        """
        INSERT OR IGNORE INTO balance_events
            (user_id, event_type, delta_credits, amount_usd, eur_usd_rate,
             event_key, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            event_type,
            delta_credits,
            amount_usd,
            rate,
            event_key,
            _now(),
        ),
    )
