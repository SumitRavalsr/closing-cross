# NSE Closing Crossover Scanner

A one-stock pilot for detecting 20-session and 50-session moving-average crossovers using daily NSE closing prices. The Python worker runs scans and replays, SQLite stores results, FastAPI serves them, and a React dashboard displays them. The scanner does not place broker orders. Scheduled forward scans, hypothetical portfolio accounting, and the 30-stock rollout are not yet complete.

## Run locally with Docker Desktop

Start Docker Desktop in Linux containers mode and wait for its engine to start. Docker Compose must be available as `docker compose`. The first build after deleting images needs internet access to download base images and dependencies. You do not need Python or Node.js installed on Windows to run the Docker stack.

In PowerShell, open the repository and create the local environment files **only if they are missing**:

```powershell
Set-Location 'F:\Clossing Cross Agent'
if (-not (Test-Path -LiteralPath 'backend/.env')) {
    Copy-Item -LiteralPath 'backend/.env.example' -Destination 'backend/.env'
}
if (-not (Test-Path -LiteralPath 'frontend/.env')) {
    Copy-Item -LiteralPath 'frontend/.env.example' -Destination 'frontend/.env'
}
```

Use your own checkout path if it differs. The example values are sufficient for the dashboard and sample data; leave the Angel One credentials blank unless you are setting up live scans. Keep local `.env` files out of Git and never put broker credentials in `frontend/.env`.

Build and start the development stack:

```powershell
docker compose -p closing-cross-dev -f compose.dev.yaml up --build --wait
```

Compose runs the SQLite migrations before starting the API, then starts the dashboard. Open [the dashboard](http://127.0.0.1:5173/). To check the API through the dashboard, run:

```powershell
Invoke-RestMethod 'http://127.0.0.1:5173/api/ready' | ConvertTo-Json -Compress
```

Expected response: `{"status":"ready"}`. React and FastAPI reload when their source files change; ordinary source edits do not require an image rebuild.

### Load sample signals (optional)

An empty dashboard is normal with a fresh database. To add sample crossover signals without broker credentials, run this from the repository root after startup:

```powershell
docker compose -p closing-cross-dev -f compose.dev.yaml run --rm --build worker closing-cross seed-fixture
```

Refresh the dashboard to see `FIXTURE` session 51 (`up`) and session 52 (`down`). Rerunning the loader does not duplicate the records. It does not fetch live market data.

## Recover after deleting Docker images or containers

Run the same `up --build --wait` command from the quickstart. Compose rebuilds missing images and recreates missing containers. Only recreate `.env` files if they are missing.

- **Only images or containers deleted:** Compose reuses the existing `closing-cross-dev_sqlite` volume if it is still present. Keep using the `closing-cross-dev` project name so the app and worker use the same local database.
- **SQLite volume also deleted:** The migration job initializes a fresh database. Restore a backup if you need your old results; the fixture loader only recreates sample signals.

To stop and remove the local containers without deleting their volumes:

```powershell
docker compose -p closing-cross-dev -f compose.dev.yaml down
```

Do not add `--volumes` (or `-v`) unless you intend to delete the development database and the frontend dependency volume.

## Troubleshoot local startup

Run these from the repository root:

```powershell
docker compose -p closing-cross-dev -f compose.dev.yaml --profile fixture config --quiet
docker compose -p closing-cross-dev -f compose.dev.yaml ps --all
docker compose -p closing-cross-dev -f compose.dev.yaml logs --tail 100 migrate api frontend
```

| Symptom | What to check |
| --- | --- |
| Cannot connect to the Docker engine | Open Docker Desktop, wait for the engine to start, then retry. |
| Compose reports a missing `.env` file | Run the conditional copy commands in the quickstart. |
| Port `5173` is already in use | Stop the other process or container using that port, then rerun startup. |
| Startup fails or readiness does not respond | Check the logs above, starting with `migrate`. An exit code of `0` for `migrate` is normal. |
| Dashboard loads but shows no records | Run the sample loader if you want fixture signals. A live report is a separate operation. |

## Development checks

If running checks directly on your machine, install uv and Node.js/npm first. From the repository root:

```powershell
Set-Location backend
uv sync --locked
uv run --locked pytest
Set-Location ../frontend
npm ci
npm run build
Set-Location ..
```

## Project docs

- [Operations](OPERATIONS.md): current pilot status, verified replay, live Angel One workflow, and Ubuntu VPS deployment. Use `compose.prod.yaml` for the VPS workflow, not the local quickstart.
- [Architecture](ARCHITECTURE.md): service boundaries, repository layout, and development and production Compose conventions.
- [Build plan](BUILD_PLAN.md): strategy rules, pilot acceptance checks, and the gate for expanding to 30 stocks.
