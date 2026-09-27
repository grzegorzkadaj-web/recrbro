from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(Path(__file__).with_name(".env"))

DATABASE_PATH = Path(
    os.getenv("RECRBRO_DATABASE_PATH", PROJECT_ROOT / "data" / "recrbro.db")
)
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
OPENAI_JOB_ANALYSIS_MODEL = os.getenv("OPENAI_JOB_ANALYSIS_MODEL", "gpt-5-nano")
OPENAI_INPUT_COST_PER_MILLION = float(
    os.getenv("OPENAI_INPUT_COST_PER_MILLION", "0.40")
)
OPENAI_OUTPUT_COST_PER_MILLION = float(
    os.getenv("OPENAI_OUTPUT_COST_PER_MILLION", "1.60")
)
USD_TO_PLN = float(os.getenv("USD_TO_PLN", "4.0"))
CREDIT_COST_MULTIPLIER = float(os.getenv("CREDIT_COST_MULTIPLIER", "10"))
CURRENCY_RATE_URL = os.getenv(
    "CURRENCY_RATE_URL", "https://api.frankfurter.dev/v2/rate/EUR/USD"
)
CURRENCY_RATE_CACHE_MINUTES = int(os.getenv("CURRENCY_RATE_CACHE_MINUTES", "60"))


def _normalized_origins(value: str) -> tuple[str, ...]:
    origins = tuple(
        dict.fromkeys(
            origin.strip().rstrip("/")
            for origin in value.split(",")
            if origin.strip().rstrip("/")
        )
    )
    if not origins:
        raise ValueError("At least one frontend origin must be configured.")
    return origins


FRONTEND_ORIGINS = _normalized_origins(
    os.getenv("FRONTEND_ORIGINS")
    or os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
)
FRONTEND_ORIGIN = FRONTEND_ORIGINS[0]
PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "http://127.0.0.1:8000")
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "168"))
SEED_DEMO_USERS = os.getenv("SEED_DEMO_USERS", "true").casefold() == "true"
APP_ENV = os.getenv("APP_ENV", "development")
APP_SECRET = os.getenv("APP_SECRET", "development-only-change-me")
TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY")
P24_MERCHANT_ID = os.getenv("P24_MERCHANT_ID")
P24_POS_ID = os.getenv("P24_POS_ID")
P24_API_KEY = os.getenv("P24_API_KEY")
P24_CRC = os.getenv("P24_CRC")
P24_SANDBOX = os.getenv("P24_SANDBOX", "true").casefold() == "true"
