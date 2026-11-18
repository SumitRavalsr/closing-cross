FROM ghcr.io/astral-sh/uv:0.11.14 AS uv
FROM python:3.12-slim AS base
COPY --from=uv /uv /uvx /bin/
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never PATH="/opt/venv/bin:$PATH"
WORKDIR /app

FROM base AS dev
COPY . .
RUN uv sync --locked
CMD ["uvicorn", "closing_cross.api:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/src"]

FROM base AS build
COPY . .
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12-slim AS prod
ENV PATH="/opt/venv/bin:$PATH"
COPY --from=build /opt/venv /opt/venv
CMD ["uvicorn", "closing_cross.api:app", "--host", "0.0.0.0", "--port", "8000"]
