FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV APP_ENV=production \
    HOST=0.0.0.0 \
    PORT=8000 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev

RUN mkdir -p /data
VOLUME ["/data"]
EXPOSE 8000

CMD ["uv", "run", "--no-sync", "recrbro"]
