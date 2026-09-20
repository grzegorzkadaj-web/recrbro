from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run(
        "recrbro.api:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
