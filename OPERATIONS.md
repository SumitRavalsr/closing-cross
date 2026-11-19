# Scanner operations and handoff

The Windows development stack passed its fixture test and the Ubuntu VPS completed a verified live Angel One replay for one NSE stock. The code now includes a paper trade ledger for verified replays. The production worker runs on demand. Read this file before working on deployments or continuing the one-stock pilot. [ARCHITECTURE.md](ARCHITECTURE.md) describes the services and [BUILD_PLAN.md](BUILD_PLAN.md) defines the rollout gate.

## Current environments

| Setting | Windows laptop | Ubuntu VPS |
|---|---|---|
| Checkout | `F:\Clossing Cross Agent` | `~/closing-cross-git` under the SSH login used for deployment |
| Compose file and project | `compose.dev.yaml`, `closing-cross-dev` | `compose.prod.yaml`, `closing-cross-prod` |
| Application | FastAPI and React with hot reload | Built FastAPI and React/Nginx images |
| Dashboard | `http://127.0.0.1:5173/` | VPS loopback `127.0.0.1:8080`, forwarded to Windows port `8081` over SSH |
| Environment files | `backend/.env` and `frontend/.env` | `backend/.env.production` and `frontend/.env.production` |
| Data | Local SQLite volume for development | Separate named SQLite volume mounted at `/data` by the API, migration job, and worker |

The worker reaches Angel One from the VPS's registered public IPv4. Its broker calls are limited to login, instrument lookup, and daily candle retrieval. Broker credentials stay in the VPS backend env file and are only supplied to the worker. Use `.env.example` for the variable names. The GitHub Pages setup for the Angel One form uses `https://sumitravalsr.github.io/`. The scanner authenticates directly with a login PIN and TOTP.

## What passed

- **Local fixture.** The API returned `FIXTURE` session 51 `up` and session 52 `down`. Rerunning the loader left exactly two records. Earlier container smoke tests verified React and FastAPI reload in development and SQLite persistence across service recreation.
- **Live one-stock replay.** The VPS worker authenticated, resolved `RELIANCE-EQ` to SmartAPI token `2885`, and verified exact OHLCV against final NSE bhavcopies for 57 sessions in the requested 24 August–13 November 2026 window. Production SQLite saved report ID `1`. The target session had SMA 20 of `1255.025`, SMA 50 of `1239.79`, and `cross: null`, meaning no new crossover on that date.
- **Report access.** Production readiness was confirmed on the VPS. The user supplied the successful worker output. Viewing that report through the Windows SSH tunnel remains to be confirmed.

## Develop and deploy

Use local development Compose for source edits, hot reload, and fixture tests. The fixture loader runs without SmartAPI credentials.

```powershell
Set-Location 'F:\Clossing Cross Agent'
docker compose -p closing-cross-dev -f compose.dev.yaml up --build --wait
docker compose -p closing-cross-dev -f compose.dev.yaml run --rm --build worker closing-cross seed-fixture
```

When a change needs a live integration test, commit it and run `git push origin main` from the laptop. For a private repo, give the VPS checkout GitHub read access using a repository-scoped deploy key. The production `.env` files live on the VPS and are ignored by Git. For a fresh VPS checkout, create both `.env.production` files from their respective `.env.example` templates before starting Compose, then enter broker settings in the backend file.

Run on the VPS after pushing the intended commit:

```bash
cd ~/closing-cross-git
git pull --ff-only && sudo docker compose -p closing-cross-prod -f compose.prod.yaml up --build --wait
curl -fsS http://127.0.0.1:8080/api/ready
```

Expect `{"status":"ready"}`. Keep the project name `closing-cross-prod` on every production command so API and worker use the same database. Preserve the named volume on redeploy. Run the worker with `--build` on the first scan after a code change to refresh its separate image. The application remains on loopback for the pilot.

## Run and inspect the live pilot

The following VPS command records the successful replay window. For a new run, choose an actual completed NSE session with a published final bhavcopy. Confirm the configured stock had no split or bonus in the lookback and use `--closed-on` only for confirmed cash-market holidays. [NSE capital market holiday circular](https://nsearchives.nseindia.com/content/circulars/CMTR71775.pdf)

```bash
cd ~/closing-cross-git
sudo docker compose -p closing-cross-prod -f compose.prod.yaml run --rm --build worker \
  closing-cross scan-nse --session 2026-11-13 --start 2026-08-24 \
  --closed-on 2026-09-14 --closed-on 2026-10-02 \
  --closed-on 2026-10-20 --closed-on 2026-11-10 \
  --confirm-no-split-bonus
```

The CLI requires at least 51 verified sessions. Identical inputs reuse the saved report. For failures, capture the `Scan stopped.` message with credentials removed. For an invalid `--session`, replace the placeholder with a date in `YYYY-MM-DD` format. Check `/api/ready` on the VPS if the stack itself fails to respond.

To see the dashboard, substitute the actual VPS public IPv4 and run this in **Windows PowerShell**. Keep the SSH session open while viewing the dashboard.

```powershell
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8081:127.0.0.1:8080 root@YOUR_VPS_IPV4
```

Open `http://127.0.0.1:8081/` and look for **RELIANCE · Verified NSE replay**. In a second PowerShell window, check which report the API is serving:

```powershell
Invoke-RestMethod http://127.0.0.1:8081/api/pilot/verified-scan |
  Select-Object id, symbol, session, verified_sessions
```

If the tunnel cannot bind to `8081`, use `8082` as the local port in the SSH command and both Windows URLs. The VPS target stays at `8080`. If the endpoint returns `null`, check on the VPS that the API and worker were both launched in the `closing-cross-prod` project and that the scan succeeded.

The laptop uses its fixture database for development. If verified report data is needed locally in the future, take a consistent backup of the VPS SQLite database and restore it into the development volume. A hosted database is a separate future option.

## Verify the paper trade ledger

Locally, run the development startup and fixture commands from **Develop and deploy**, then refresh `http://127.0.0.1:5173/`. The **Fixture · Paper trade ledger** shows two fills, cash and equity of ₹804.00, zero shares held, and net P&L of −₹196.00. Expand **Daily cash and equity** to see ₹734.00 equity at session 52. Rerun `seed-fixture` and verify the same two fills.

After deploying the ledger build to the VPS, use the latest saved verified scan to build a paper ledger without fetching candles again:

```bash
cd ~/closing-cross-git
sudo docker compose -p closing-cross-prod -f compose.prod.yaml run --rm --build worker closing-cross paper-ledger
```

Refresh the tunnel dashboard to see **RELIANCE · Paper trade ledger**. Subsequent `scan-nse` runs save the ledger automatically. A historical replay can have zero fills if no eligible crossover occurred or if the allocation could not buy one share. The last crossover can be pending when the next opening candle falls outside the report.

## Continue the one-stock pilot

1. **Verify the ledger on the VPS.** Build a ledger for the saved `RELIANCE` report and check the dashboard through the tunnel. The ₹1,000 to ₹804 fixture also exercises the completed round trip and rerun locally.
2. **Add scheduled forward scans.** Validate final candle timing, missed runs, authentication recovery, idempotency, and after-open signal behavior on the VPS.
3. **Expand to 30 only after the one-stock gate passes.** Keep the read-only broker boundary and verify the shared-cash and partial-data cases before turning on the expanded schedule.
