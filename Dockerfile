FROM ghcr.io/astral-sh/uv:0.8.3-python3.12-bookworm-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH=/app/.venv/bin:$PATH
WORKDIR /app

COPY pyproject.toml README.md ./
RUN uv sync --no-dev --no-install-project
COPY app ./app
COPY mcp_bridge ./mcp_bridge
COPY benchmarks ./benchmarks
RUN uv sync --no-dev

FROM base AS app
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --home-dir /nonexistent --shell /usr/sbin/nologin app \
    && mkdir -p /data /models && chown -R app:app /data /models /app
USER 10001:10001
EXPOSE 8088
CMD ["python", "-m", "app.main"]

FROM base AS browser
USER root
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN uv sync --no-dev --extra browser && uv run playwright install --with-deps chromium \
    && groupadd --gid 10001 browser && useradd --uid 10001 --gid browser --home-dir /nonexistent --shell /usr/sbin/nologin browser \
    && chown -R browser:browser /app /ms-playwright
COPY browser_service ./browser_service
USER 10001:10001
EXPOSE 8090
CMD ["uvicorn", "browser_service.main:app", "--host", "0.0.0.0", "--port", "8090"]
