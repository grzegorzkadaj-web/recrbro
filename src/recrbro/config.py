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
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
