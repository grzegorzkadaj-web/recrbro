from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from recrbro.config import DATABASE_PATH, SEED_DEMO_USERS
from recrbro.models import (
    JobOffer,
    Profile,
    ProfileUpdate,
    SearchJob,
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
                google_subject TEXT UNIQUE,
                plan TEXT NOT NULL CHECK (plan IN ('free', 'premium')),
                result_limit INTEGER NOT NULL,
                monthly_budget_pln REAL NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS profiles (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                core_skills TEXT NOT NULL DEFAULT '[]',
                other_skills TEXT NOT NULL DEFAULT '[]',
                languages TEXT NOT NULL DEFAULT '[]',
                location TEXT NOT NULL DEFAULT '',
                work_modes TEXT NOT NULL DEFAULT '[]',
                minimum_salary INTEGER,
                contract_types TEXT NOT NULL DEFAULT '[]',
                excluded_companies TEXT NOT NULL DEFAULT '[]',
                cv_filename TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                query TEXT NOT NULL,
                status TEXT NOT NULL,
                requested_results INTEGER NOT NULL DEFAULT 5,
                available_at TEXT NOT NULL DEFAULT '',
                claimed_at TEXT,
                attempts INTEGER NOT NULL DEFAULT 0,
                warning TEXT,
                error TEXT,
                completed_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS job_offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                search_id INTEGER NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
                result_type TEXT NOT NULL DEFAULT 'job',
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                url TEXT NOT NULL,
                summary TEXT NOT NULL,
                score REAL NOT NULL,
                matched_skills TEXT NOT NULL,
                match_reasons TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS usage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                operation TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                cost_usd REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                session_id TEXT NOT NULL UNIQUE,
                order_id INTEGER,
                amount_grosz INTEGER NOT NULL,
                method TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );
            """)
        user_columns = {
            row["name"] for row in database.execute("PRAGMA table_info(users)")
        }
        if "password_hash" not in user_columns:
            database.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        if "google_subject" not in user_columns:
            database.execute("ALTER TABLE users ADD COLUMN google_subject TEXT")
        search_columns = {
            row["name"] for row in database.execute("PRAGMA table_info(searches)")
        }
        for statement in (
            (
                "requested_results",
                "ALTER TABLE searches ADD COLUMN requested_results INTEGER NOT NULL DEFAULT 5",
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
        if SEED_DEMO_USERS:
            seed_users = [
                (1, "Free demo", "free@recrbro.local", "free", 5, 0),
                (2, "Premium demo", "premium@recrbro.local", "premium", 100, 50),
            ]
            database.executemany(
                """
                INSERT OR IGNORE INTO users
                    (id, name, email, plan, result_limit, monthly_budget_pln, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [(*user, _now()) for user in seed_users],
            )
            for user_id in (1, 2):
                _insert_default_profile(database, user_id, seeded=True)


def _insert_default_profile(
    database: sqlite3.Connection, user_id: int, seeded: bool = False
) -> None:
    database.execute(
        """
        INSERT OR IGNORE INTO profiles
            (user_id, core_skills, other_skills, languages,
             location, work_modes, contract_types, excluded_companies, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            _now(),
        ),
    )


def _profile_from_row(row: sqlite3.Row) -> Profile:
    values = dict(row)
    for field in LIST_FIELDS:
        values[field] = json.loads(values[field])
    values.pop("updated_at", None)
    return Profile.model_validate(values)


def list_users() -> list[User]:
    with connection() as database:
        rows = database.execute("""
            SELECT u.*, COALESCE(SUM(e.cost_usd), 0) AS tracked_cost_usd
            FROM users u
            LEFT JOIN usage_events e ON e.user_id = u.id
            GROUP BY u.id
            ORDER BY u.id
            """).fetchall()
    return [User.model_validate(dict(row)) for row in rows]


def get_user(user_id: int) -> User | None:
    return next((user for user in list_users() if user.id == user_id), None)


def get_user_by_email(
    email: str, include_password: bool = False
) -> User | tuple[User, str | None] | None:
    with connection() as database:
        row = database.execute(
            """
            SELECT u.*, COALESCE(SUM(e.cost_usd), 0) AS tracked_cost_usd
            FROM users u LEFT JOIN usage_events e ON e.user_id = u.id
            WHERE u.email = ? GROUP BY u.id
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


def create_user(name: str, email: str, password_hash: str | None = None) -> User:
    with connection() as database:
        cursor = database.execute(
            """
            INSERT INTO users
                (name, email, password_hash, plan, result_limit,
                 monthly_budget_pln, created_at)
            VALUES (?, ?, ?, 'free', 5, 0, ?)
            """,
            (name, email, password_hash, _now()),
        )
        user_id = int(cursor.lastrowid)
        _insert_default_profile(database, user_id)
    user = get_user(user_id)
    if user is None:
        raise LookupError("Created user could not be loaded.")
    return user


def set_google_identity(subject: str, name: str, email: str) -> User:
    existing = get_user_by_email(email)
    if isinstance(existing, User):
        with connection() as database:
            database.execute(
                "UPDATE users SET google_subject = ? WHERE id = ?",
                (subject, existing.id),
            )
        return existing
    with connection() as database:
        cursor = database.execute(
            """
            INSERT INTO users
                (name, email, google_subject, plan, result_limit,
                 monthly_budget_pln, created_at)
            VALUES (?, ?, ?, 'free', 5, 0, ?)
            """,
            (name, email, subject, _now()),
        )
        user_id = int(cursor.lastrowid)
        _insert_default_profile(database, user_id)
    user = get_user(user_id)
    if user is None:
        raise LookupError("Google user could not be loaded.")
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
                excluded_companies = ?, cv_filename = COALESCE(?, cv_filename),
                updated_at = ?
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
    requested_results: int = 5,
    status: str = "running",
    available_at: datetime | None = None,
) -> int:
    available = available_at or datetime.now(timezone.utc)
    with connection() as database:
        cursor = database.execute(
            """
            INSERT INTO searches
                (user_id, query, status, requested_results, available_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                query,
                status,
                requested_results,
                available.isoformat(),
                _now(),
            ),
        )
        return int(cursor.lastrowid)


def complete_search(
    search_id: int, offers: list[JobOffer], warning: str | None = None
) -> None:
    with connection() as database:
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
                for offer in offers
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


def queue_free_search(
    user_id: int,
    query: str,
    requested_results: int,
    delay_minutes: int,
    schedule_minutes: int,
) -> int:
    now = datetime.now(timezone.utc)
    with connection() as database:
        database.execute("BEGIN IMMEDIATE")
        row = database.execute(
            """
            SELECT MAX(available_at) AS available_at
            FROM searches WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        latest = (
            datetime.fromisoformat(row["available_at"])
            if row and row["available_at"]
            else None
        )
        available_at = (
            max(now, latest + timedelta(minutes=delay_minutes)) if latest else now
        )
        interval = max(1, schedule_minutes)
        minute = ((available_at.minute // interval) + 1) * interval
        available_at = available_at.replace(second=0, microsecond=0)
        if minute >= 60:
            available_at = available_at.replace(minute=0) + timedelta(hours=1)
        else:
            available_at = available_at.replace(minute=minute)
        cursor = database.execute(
            """
            INSERT INTO searches
                (user_id, query, status, requested_results, available_at, created_at)
            VALUES (?, ?, 'queued', ?, ?, ?)
            """,
            (
                user_id,
                query,
                requested_results,
                available_at.isoformat(),
                _now(),
            ),
        )
        return int(cursor.lastrowid)


def claim_due_searches(lease_minutes: int, limit: int = 5) -> list[int]:
    now = datetime.now(timezone.utc)
    stale_before = (now - timedelta(minutes=lease_minutes)).isoformat()
    with connection() as database:
        database.execute("BEGIN IMMEDIATE")
        rows = database.execute(
            """
            SELECT id FROM searches
            WHERE (status = 'queued' AND available_at <= ?)
               OR (
                   status = 'running'
                   AND (claimed_at IS NULL OR claimed_at <= ?)
               )
            ORDER BY available_at, id LIMIT ?
            """,
            (now.isoformat(), stale_before, limit),
        ).fetchall()
        ids = [int(row["id"]) for row in rows]
        if ids:
            database.executemany(
                """
                UPDATE searches
                SET status = 'running', claimed_at = ?, attempts = attempts + 1
                WHERE id = ?
                """,
                [(now.isoformat(), search_id) for search_id in ids],
            )
    return ids


def _search_from_row(database: sqlite3.Connection, row: sqlite3.Row) -> SearchJob:
    offers = database.execute(
        "SELECT * FROM job_offers WHERE search_id = ? ORDER BY score DESC, id",
        (row["id"],),
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
    user_id: int, session_id: str, amount_grosz: int, method: str
) -> int:
    with connection() as database:
        cursor = database.execute(
            """
            INSERT INTO payments
                (user_id, session_id, amount_grosz, method, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (user_id, session_id, amount_grosz, method, _now()),
        )
        return int(cursor.lastrowid)


def complete_payment(session_id: str, order_id: int) -> None:
    with connection() as database:
        row = database.execute(
            "SELECT user_id FROM payments WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise LookupError("Payment not found.")
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
            SET plan = 'premium', result_limit = 100, monthly_budget_pln = 50
            WHERE id = ?
            """,
            (row["user_id"],),
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
    with connection() as database:
        database.execute(
            """
            INSERT INTO usage_events
                (user_id, operation, model, input_tokens, output_tokens, cost_usd, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, operation, model, input_tokens, output_tokens, cost_usd, _now()),
        )


def usage_summary(user_id: int) -> UsageSummary:
    with connection() as database:
        row = database.execute(
            """
            SELECT COALESCE(SUM(input_tokens), 0) AS input_tokens,
                   COALESCE(SUM(output_tokens), 0) AS output_tokens,
                   COALESCE(SUM(cost_usd), 0) AS cost_usd
            FROM usage_events WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
    return UsageSummary.model_validate(dict(row))
