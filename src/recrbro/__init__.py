from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "recrbro.api:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("APP_ENV", "development") != "production",
    )
