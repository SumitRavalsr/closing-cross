# NSE scanner architecture

The FastAPI backend, React frontend, and scanner worker live in one Git repository. The backend uses uv and owns the strategy, broker integration, and SQLite database. The frontend accesses results through the API. Two standalone Docker Compose files define development and production.

See [OPERATIONS.md](OPERATIONS.md) for the active Windows and Ubuntu VPS setup, deployment commands, SSH tunnel, and live pilot status.

## Repository layout

This is the target layout for the one-stock pilot. `AGENTS.md` at the repository root applies to both applications.

```text
.
├── AGENTS.md
├── ARCHITECTURE.md
├── BUILD_PLAN.md
├── OPERATIONS.md
├── .gitignore
├── compose.dev.yaml
├── compose.prod.yaml
├── backend/
│   ├── .dockerignore
│   ├── .env.example
│   ├── .python-version
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── src/closing_cross/
│   │   ├── api/               # FastAPI routes, API schemas, health endpoints
│   │   ├── domain/            # SMA, signals, fills, cash, portfolio rules
│   │   ├── scanner/           # Replay, forward scanning, scheduling, CLI
│   │   ├── adapters/          # SmartAPI, exchange calendar, SQLite and its migrations
│   │   └── settings.py        # Typed backend configuration
│   └── tests/
│       └── fixtures/
└── frontend/
    ├── .dockerignore
    ├── .env.example
    ├── Dockerfile
    ├── package.json
    ├── package-lock.json
    ├── vite.config.ts
    ├── deploy/
    │   └── nginx.conf.template
    └── src/
        ├── api/               # Typed API client
        ├── components/        # Reusable UI components
        └── features/          # Watchlist, stock detail, performance, scan health
```

## Service and data boundaries

- **Frontend** sends browser requests to same-origin `/api/` endpoints. Vite proxies these requests in development, and the production static server proxies them in production. Both proxies keep the `/api` prefix and use `http://api:8000` on the Compose network.
- **API** serves scanner results from SQLite. It exposes health and readiness checks. Scheduled scans, ingestion, and replay run through the backend worker or CLI.
- **Worker** can load the deterministic fixture, run a verified historical replay, or advance the one-stock forward portfolio. It compares SmartAPI candles with final NSE bhavcopy before running the shared crossover and paper accounting logic.
- **Migration job** runs from the backend image before the API and worker start. A failed migration blocks those services. The migration job, API, and worker share a named SQLite volume at `/data`. Keep the database and SQLite journal files on that volume and use SQLite's backup API for consistent copies. Development and production use separate Compose project names and volumes.
- **Domain logic** accepts explicit inputs and stays independent of FastAPI, SQLite, SmartAPI, scheduling, and the system clock. Browser traffic reaches the API through the frontend. SmartAPI credentials are required by the worker when it fetches broker data.

## Dependencies and images

- Run Python dependency commands from `backend/`. Use `uv add` to change dependencies, `uv sync --locked` to install them, and `uv run --locked pytest` to run backend tests. Commit `pyproject.toml`, `uv.lock`, and `.python-version` together when affected.
- Use npm in `frontend/` for the React and TypeScript project. Commit `package-lock.json` and use `npm ci` in images and CI.
- Build each component from its own directory with one multi-stage `Dockerfile` and separate `dev` and `prod` targets. Pin the Python, uv, and Node versions used by the build. The backend production image uses the locked environment with development dependencies omitted. The frontend production image builds the Vite bundle and serves it through Nginx.

## Environment files

| Scope | Development | Production | Contents |
|---|---|---|---|
| Backend | `backend/.env` | `backend/.env.production` | Database path, scan settings, and backend-only broker credentials |
| Frontend | `frontend/.env` | `frontend/.env.production` | Public configuration, such as development polling or the internal web server listen port |

Copy each application's `.env.example` to `.env` for development and `.env.production` for production. Other `.env` files are ignored in Git and excluded from each Docker build context. Each Compose file explicitly selects its environment-specific files with service-level `env_file`. Only the worker receives the backend env file. The API and migration job receive their required non-secret settings explicitly. Provision future production broker secrets on the host.

Use `/api` as the browser API base in both environments. Keep any future `VITE_*` values public. Vite embeds those values at build time, so changing a production service's runtime environment does not update a built browser bundle. Keep the production frontend environment limited to settings the static server reads at startup.

## Docker Compose workflows

The `api`, `worker`, and `migrate` services use the backend image, and `frontend` uses the frontend image. The scaffold worker has an opt-in `fixture` profile in both stacks. Enable the production worker by default when unattended scans are implemented.

### Development

```sh
docker compose -p closing-cross-dev -f compose.dev.yaml up --build --wait
docker compose -p closing-cross-dev -f compose.dev.yaml run --rm --build worker
```

- Bind-mount the application directories into their development containers. Put the uv environment at `/opt/venv`, outside the backend source mount. Keep container `node_modules` in a dedicated volume beneath the frontend mount. Run `npm ci` at frontend startup so the mounted dependencies match `package-lock.json` after a rebuild.
- Run Uvicorn on `0.0.0.0:8000` with `--reload` and `--reload-dir /app/src`. Install the `watchfiles` backend dependency in the development group and set `WATCHFILES_FORCE_POLLING=true` in development for Docker Desktop bind mounts.
- Run Vite on `0.0.0.0:5173` with React Fast Refresh. Set `server.watch.usePolling` in development for Docker Desktop bind mounts. Publish the frontend port on loopback and keep its HMR WebSocket reachable from the browser. Normal Python and React source edits take effect without rebuilding containers. Dependency changes require a rebuild or dependency refresh.
- Open `http://127.0.0.1:5173` for the dashboard. The optional worker command loads two deterministic crossover rows. Reload the page to see them if it was open during the load.

### Verified one-stock replay

The live pilot runs on the VPS using `compose.prod.yaml` and `backend/.env.production`. Follow the [VPS runbook](OPERATIONS.md#run-and-inspect-the-live-pilot). The development examples below apply to a machine with SmartAPI access from its own registered network.

1. Fill `ANGEL_API_KEY`, `ANGEL_CLIENT_CODE`, `ANGEL_PIN`, and `ANGEL_TOTP_SECRET` in `backend/.env`. The secret is the authenticator setup key. A fresh `ANGEL_TOTP_CODE` can be used instead for manual login. Enter it immediately before running the worker and clear it afterwards. `PILOT_NSE_SYMBOL` defaults to `RELIANCE` and accepts a single cash symbol without the `-EQ` suffix. If your broker setup requires particular IP headers, set `ANGEL_LOCAL_IP` and `ANGEL_PUBLIC_IP` there too. The worker only calls SmartAPI login, instrument search, and daily candle read endpoints.
2. Pick a completed NSE trading session with a published final bhavcopy and confirm the stock had no splits or bonus issues during the selected window. The default window is 101 calendar days ending on that session. Use `--start` to choose a different window with at least 51 trading sessions.
3. From the repo root, run the following with the chosen session date. Add `--closed-on YYYY-MM-DD` for each missing weekday archive you have confirmed as an exchange holiday. An unexplained missing weekday, a missing target report, or a data mismatch stops the run. Archives published for weekend special sessions are included. Check the NSE calendar for any special sessions in the window when using local archives. [NSE daily reports](https://www.nseindia.com/all-reports/) · [NSE exchange calendar](https://www.nseindia.com/resources/exchange-communication-holidays) · [Angel One SmartAPI documentation](https://smartapi.angelone.in/docs)

```sh
docker compose -p closing-cross-dev -f compose.dev.yaml up --build --wait
docker compose -p closing-cross-dev -f compose.dev.yaml run --rm --build worker closing-cross scan-nse --session YYYY-MM-DD --confirm-no-split-bonus
```

If the NSE download is unavailable, place the original `CM-UDiFF Common Bhavcopy Final` ZIP files in a subdirectory of `backend/` and add `--bhavcopy-dir /app/<directory>` to the worker command. For a standalone run with a local SQLite database, change into `backend/` and run `uv run --locked --env-file .env closing-cross scan-nse` with the same flags and a local directory path.

The CLI reports the number of matching sessions, both SMAs, and the cross or absence of one on the target date. Open the dashboard or `GET /api/pilot/verified-scan` to inspect the run. Identical inputs reuse the same saved report. The report records exact OHLCV matches and raw-price replay signals. Select a different window when a split or bonus falls within the lookback.

### Paper trade ledger

After verifying candles, the worker saves an immutable, one-stock historical ledger alongside the report in the same SQLite transaction. Identical runs reuse the saved ledger. Fixture and verified ledgers are stored independently and exposed via `GET /api/pilot/paper-ledgers`. `closing-cross paper-ledger` builds accounting from the latest saved verified scan, including reports created before the ledger migration.

Each replay starts flat with an independent cash balance. Use `PAPER_OPENING_CASH`, `PAPER_ALLOCATION`, `PAPER_FEE`, and `PAPER_SLIPPAGE_PER_SHARE` in the worker's backend env file to configure INR amounts. Defaults are ₹1,000 cash, ₹1,000 per position, ₹2 per fill, and ₹1 per share adverse slippage. The fixture always uses those values. Fills use the next verified session's open, adjusted for slippage and rounded to the paise against the trade. Closing equity is rounded half up to the paise. P&L currently reflects price changes, fees, and slippage.

### Forward pilot

`forward-init` creates an independent flat paper portfolio from the last 50 verified closes. `forward-scan` fetches only due, uncommitted dates and uses the reviewed CSV calendar for open and publication-check times. Each completed session saves its verified OHLCV, observation time, calendar hash, and paper events in the same transaction as the position update. Duplicate commits reuse the existing session. The forward position locks the initial paper terms at initialization. The VPS systemd timer invokes the production worker without enabling a persistent scanner container. [Forward pilot runbook](OPERATIONS.md#continue-the-one-stock-pilot)

### Production

```sh
docker compose -p closing-cross-prod -f compose.prod.yaml up --build --wait
docker compose -p closing-cross-prod -f compose.prod.yaml run --rm --build worker
```

Production Compose uses immutable images, ordinary Uvicorn, and the built static frontend. The VPS publishes the frontend on `127.0.0.1:8080`. Access it from the laptop through the SSH tunnel in [OPERATIONS.md](OPERATIONS.md#run-and-inspect-the-live-pilot). The API and migration job stay on the private Compose network. Source bind mounts, file watchers, and HMR are development-only.

## Container acceptance checks

1. Validate both Compose files with `docker compose -f <file> config --quiet` after creating the respective environment files.
2. Bring up development with pilot fixtures. Edit a React component and verify the browser updates through HMR. Edit a Python route and verify the changed API response after Uvicorn reloads. Neither edit should rebuild an image or recreate a container.
3. Verify `/api/` requests work through the frontend in both environments. Start production from a clean build and confirm it serves the compiled frontend and API without source mounts or reload processes.
4. Recreate containers without deleting their volumes. Verify SQLite data persists and development and production have separate data. Confirm a failed migration prevents dependent services from starting.
5. Confirm the frontend bundle and image contain no broker credentials and both `.env` example files are sufficient to identify the required settings.

[uv Docker integration](https://docs.astral.sh/uv/guides/integration/docker/) · [Docker Compose environment files](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/) · [Vite server options](https://vite.dev/config/server-options.html)
