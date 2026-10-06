FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app/backend

COPY backend/pyproject.toml backend/uv.lock ./
COPY README.md /app/README.md

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache/uv \
    uv run --no-sync playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY backend/app ./app

ENV APP_ENV=production \
    DATABASE_URL=sqlite:////data/douyin_rag.db \
    STORAGE_ROOT=/data \
    PLAYWRIGHT_USER_DATA_DIR=/data/playwright \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    CHROMA_PERSIST_DIRECTORY=/data/chroma \
    LOCAL_EMBEDDING_CACHE_DIR=/data/models \
    FFMPEG_PATH=/usr/bin/ffmpeg \
    PATH=/opt/venv/bin:$PATH

LABEL org.opencontainers.image.source="https://github.com/Jonesxq/douyin_RAG"

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
