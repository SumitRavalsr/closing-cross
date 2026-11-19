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

The saved `RELIANCE` paper ledger worked on the VPS. Deploy the forward pilot, run a scheduled session manually first, and then enable the timer. Record three consecutive automatic NSE sessions, including login after midnight, before expanding the watchlist.

### Prepare the calendar and seed

1. Create `/etc/closing-cross/nse-sessions.csv` on the VPS. List every cash-market trading session in order, from the seed date to at least one session past the intended scan window. Use exchange-local times. Omit holidays and include special trading days with their actual opening time. `ready` is the earliest time to check for the final bhavcopy. Use `18:00` for the normal pilot schedule and review special-day timing separately. Keep the last committed session in the file when extending it. [NSE market timings and holidays](https://www.nseindia.com/resources/exchange-communication-holidays)
2. Run `scan-nse` on the VPS through the **trading session immediately before** the desired first forward session. The latest saved report for `RELIANCE` must end on that preceding session. Initialization takes the last 50 closes from the verified report and opens a new flat paper position with the configured cash and costs.
3. Review splits and bonuses for the symbol through your intended operating window. Set `FORWARD_ACTIONS_REVIEWED_THROUGH=YYYY-MM-DD` in `backend/.env.production` to the last reviewed date. Use `ANGEL_TOTP_SECRET` for unattended login and leave the manual `ANGEL_TOTP_CODE` empty. The worker stops at the reviewed cutoff or on a missing, mismatched, or zero-volume candle.

The file format below shows the seed and two trading sessions. Extend it with reviewed upcoming dates before enabling the schedule:

```csv
session,open,ready
2026-11-19,09:15,18:00
2026-11-20,09:15,18:00
2026-11-23,09:15,18:00
```

### Run manually before scheduling

After deploying, run these commands on the VPS from `~/closing-cross-git`. Replace `YYYY-MM-DD` with your chosen first forward session. Run the scan after that session's `ready` time.

```bash
sudo docker compose -p closing-cross-prod -f compose.prod.yaml --profile fixture build worker
sudo docker compose -p closing-cross-prod -f compose.prod.yaml run --rm --no-deps \
  -v /etc/closing-cross/nse-sessions.csv:/config/nse-sessions.csv:ro worker \
  closing-cross forward-init --calendar /config/nse-sessions.csv --session YYYY-MM-DD
sudo docker compose -p closing-cross-prod -f compose.prod.yaml run --rm --no-deps \
  -v /etc/closing-cross/nse-sessions.csv:/config/nse-sessions.csv:ro worker \
  closing-cross forward-scan --calendar /config/nse-sessions.csv --session YYYY-MM-DD
```

Expect `"processed": 1` for the first complete run. Rerun the scan and expect `"processed": 0` with status `idle`. The **Forward paper pilot** section shows the last attempt, latest finalized session, pending trade, and portfolio marks. Check it through the existing SSH tunnel. `GET /api/pilot/forward` returns the same status with signal observation and fill details. Failed attempts stay in SQLite, and a session still outstanding 30 minutes after its expected check is marked overdue.

### Enable the VPS timer

After the manual run passes, install the supplied systemd units. The service assumes Docker is at `/usr/bin/docker` and the repository is in `/root/closing-cross-git`. Adjust the unit if your paths differ. On later deploys rebuild the `worker` image too.

```bash
sudo install -m 0644 deploy/closing-cross-forward.service /etc/systemd/system/
sudo install -m 0644 deploy/closing-cross-forward.timer /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/closing-cross-forward.{service,timer}
sudo systemctl daemon-reload
sudo systemctl enable --now closing-cross-forward.timer
systemctl list-timers closing-cross-forward.timer
sudo journalctl -u closing-cross-forward.service -n 50 --no-pager
```

The timer checks at 18:00, 19:00 and 21:00 IST. On failure, systemd retries after ten minutes, limited to three starts per 45-minute window. The worker picks up due, uncommitted sessions in date order. On a missed run, a late entry is skipped and an overdue exit targets a future opening. A fill already queued before its target open can still be resolved once the matching candle arrives. [systemd service restart rules](https://freedesktop.org/software/systemd/man/latest/systemd.service.html)

The forward pilot keeps a verified close window rather than downloading the full historical window on every run. It pauses for zero-volume or absent candles. Automated confirmation of no-trade sessions and reconciliation of historical data corrections are still outside this implementation. Keep one stock until the remaining [pilot acceptance checks](BUILD_PLAN.md#3-one-stock-acceptance-tests) pass.
