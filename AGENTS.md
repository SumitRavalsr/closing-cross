# Repository instructions

This file applies to the whole repository. For a new chat or deployment task, start with [OPERATIONS.md](OPERATIONS.md) for the current pilot status, Windows and VPS workflow, and remaining work. Use [ARCHITECTURE.md](ARCHITECTURE.md) for layout, service ownership, and Docker conventions. Use [BUILD_PLAN.md](BUILD_PLAN.md) for strategy rules, pilot acceptance checks, and the gate to expand to 30 stocks.

## Working in the monorepo

- Put Python services, CLI, migrations, and Python tests under `backend/`. Put React and TypeScript code under `frontend/`. Keep both in this Git repository.
- Use uv for backend dependency changes and execution. Run `uv sync --locked` and `uv run --locked pytest` from `backend/`. Commit `uv.lock` with dependency changes. Use npm and its lockfile for the frontend. Run the frontend lint, test, and build scripts that exist in `frontend/package.json`.
- Keep shared strategy and portfolio rules in the backend domain. Keep HTTP handling and broker and database adapters outside it. Use the same domain implementation for replay and forward scanning. Keep holdings independent of hypothetical accounting.
- Preserve finalized forward history and record the input versions and observation times needed to reproduce results. Keep session commits atomic and retries idempotent. Broker integration is limited to authentication, instrument lookup, market data, and optional holdings reads.

## Docker and configuration

- Use the two root Compose files `compose.dev.yaml` and `compose.prod.yaml`. Keep React HMR and Uvicorn reload enabled in development and use built images in production.
- Keep backend and frontend environment files separate. Update the relevant `.env.example` and architecture notes when required settings change. Keep real environment files, broker credentials, tokens, SQLite data, and generated dependency directories out of Git and image build contexts. Treat all browser configuration as public.
- When changing container wiring, validate both Compose files and exercise the affected startup or reload workflow. When changing scanner behavior, verify the affected pilot acceptance cases in the build plan. Record any checks that could not run.
