from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from recrbro.config import DATABASE_PATH
from recrbro.models import JobOffer, Profile, ProfileUpdate, UsageSummary, User

LIST_FIELDS = {
    "target_roles",
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
                plan TEXT NOT NULL CHECK (plan IN ('free', 'premium')),
                result_limit INTEGER NOT NULL,
                monthly_budget_pln REAL NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS profiles (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                target_roles TEXT NOT NULL DEFAULT '[]',
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
                warning TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS job_offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                search_id INTEGER NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
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
            """)
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
            database.execute(
                """
                INSERT OR IGNORE INTO profiles
                    (user_id, target_roles, core_skills, other_skills, languages,
                     location, work_modes, contract_types, excluded_companies, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    json.dumps(["Python Developer"]),
                    json.dumps(["Python"]),
                    json.dumps([]),
                    json.dumps(["English"]),
                    "Poland",
                    json.dumps(["remote", "hybrid"]),
                    json.dumps(["B2B", "employment"]),
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
                target_roles = ?, core_skills = ?, other_skills = ?, languages = ?,
                location = ?, work_modes = ?, minimum_salary = ?, contract_types = ?,
                excluded_companies = ?, cv_filename = COALESCE(?, cv_filename),
                updated_at = ?
            WHERE user_id = ?
            """,
            (
                json.dumps(values["target_roles"]),
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


def create_search(user_id: int, query: str) -> int:
    with connection() as database:
        cursor = database.execute(
            """
            INSERT INTO searches (user_id, query, status, created_at)
            VALUES (?, ?, 'running', ?)
            """,
            (user_id, query, _now()),
        )
        return int(cursor.lastrowid)


def complete_search(
    search_id: int, offers: list[JobOffer], warning: str | None = None
) -> None:
    with connection() as database:
        database.executemany(
            """
            INSERT INTO job_offers
                (search_id, title, company, url, summary, score,
                 matched_skills, match_reasons)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    search_id,
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
            "UPDATE searches SET status = 'complete', warning = ? WHERE id = ?",
            (warning, search_id),
        )


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
