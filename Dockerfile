FROM ghcr.io/astral-sh/uv:0.11.14 AS uv
FROM python:3.12-slim AS base
COPY --from=uv /uv /uvx /bin/
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY src ./src

FROM base AS dev
RUN uv sync --locked --no-dev
CMD ["angel-one-mcp"]

FROM base AS build
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12-slim AS prod
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=build /opt/venv /opt/venv
USER 65532:65532
CMD ["angel-one-mcp"]
