# Scanner operations and handoff

The current dashboard priority is a historical portfolio backtest for 30–50 user-selected NSE equities, with ₹10,000 shared starting cash. The earlier forward pilot and timer are paused. The Ubuntu VPS previously completed a verified Angel One replay and paper ledger for one NSE stock. [ARCHITECTURE.md](ARCHITECTURE.md) describes the services and [BUILD_PLAN.md](BUILD_PLAN.md) records the pilot plan.

## Run the portfolio backtest

[portfolio.example.json](portfolio.example.json) is ready to run with 36 Nifty 50 constituents across 15 industries. The group gives the backtest a spread of sectors and share prices. The watchlist uses alphabetical order for same-session buy priority. For a custom test, copy the file and edit `watchlist` to contain 30–50 distinct NSE equity symbols. The default opening cash is ₹10,000 shared across the entire portfolio. The adjustable ₹2,000 entry limit per company includes the fee and slippage. The worker sizes each order in whole shares from the lower of available cash and the cap. Companies can stay flat throughout the run. [NSE Indices constituent list](https://www.niftyindices.com/indices/equity/broad-based-indices/nifty--50)

The same 20/50 SMA rule applies independently to each company. Fills are at the next session's adjusted open. Sales are applied first, then buys compete for remaining cash in watchlist order. The worker reads each day's final NSE bhavcopy once for all companies. A missing exchange session stops the run. An individual symbol with incomplete candles or an unsupported corporate action is excluded from the whole calculation and listed in the report.

Run from the VPS checkout after deploying the updated stack. This command funds the portfolio for 20 November 2025 through 19 November 2026, with earlier candles for SMA warm-up. The calendar includes the 2025 weekday Muhurat session and the 2026 Sunday Budget and Muhurat sessions. [2025 NSE holidays](https://nsearchives.nseindia.com/content/circulars/CMTR65587.pdf) · [2026 NSE holidays](https://nsearchives.nseindia.com/content/circulars/CMTR71775.pdf) · [January election holiday](https://nsearchives.nseindia.com/content/circulars/CMTR72260.pdf) · [Budget session](https://nsearchives.nseindia.com/content/circulars/CMTR72349.pdf)

```bash
cd ~/closing-cross-git
sudo docker compose -p closing-cross-prod -f compose.prod.yaml run --rm --build \
  -v "$PWD/portfolio.example.json:/config/portfolio.json:ro" worker \
  closing-cross backtest-portfolio --watchlist /config/portfolio.json \
  --from 2025-11-20 --through 2026-11-19 --warmup-from 2025-09-01 \
  --closed-on 2025-10-02 --closed-on 2025-10-22 --closed-on 2025-11-05 --closed-on 2025-12-25 \
  --closed-on 2026-01-15 --closed-on 2026-01-26 --closed-on 2026-03-03 --closed-on 2026-03-26 \
  --closed-on 2026-03-31 --closed-on 2026-04-03 --closed-on 2026-04-14 --closed-on 2026-05-01 \
  --closed-on 2026-05-28 --closed-on 2026-06-26 --closed-on 2026-09-14 --closed-on 2026-10-02 \
  --closed-on 2026-10-20 --closed-on 2026-11-10 --special-session 2026-02-01 --special-session 2026-11-08
```

The dashboard shows the latest saved backtest, including net P&L after modeled fees and slippage, holdings, fills, skipped signals, exclusions, and daily equity. The comparison uses the Nifty 50 Price Index from the first funded close through the same final close, excluding dividends. Max drawdown is the largest percentage decline from a running peak at daily closes. An unavailable close stops the run before it saves a report. To use the local stack, use `docker compose -p closing-cross-dev -f compose.dev.yaml` and mount the Windows JSON path into the same `/config/portfolio.json` location. [NSE index history](https://www.niftyindices.com/reports)

The local 12-month run saved an annual report for 248 sessions. It tested 34 of the 36 watchlist symbols and excluded `HINDUNILVR` and `TMPV` for unsupported corporate actions. The strategy ended at ₹8,395.19 after ₹132 in modeled fees and ₹139 in modeled slippage. Return was −16.05% with 18.99% max drawdown, compared with −2.59% and 15.56% for the Nifty 50 Price Index.

## Run the historical backtest

The backtest reads official NSE final bhavcopies and checks NSE corporate actions. It starts flat with ₹5,000 on 1 November and uses earlier closes for SMA warm-up. The first funded session is 2 November. A 20/50 upward crossover can queue a buy at the next session's open, and a downward crossover can queue a sale of the open position. The dashboard shows cash or shares held on days without a fill. P&L includes the configured ₹2 per fill and ₹1 per share adverse slippage at the default settings. Open positions are marked at the final close in the selected range.

On the VPS after deploying the updated production stack, run:

```bash
cd ~/closing-cross-git
sudo docker compose -p closing-cross-prod -f compose.prod.yaml run --rm --build worker \
  closing-cross backtest-nse --from 2026-11-01 --through 2026-11-19 --warmup-from 2026-08-17 --cash 5000 \
  --closed-on 2026-09-14 --closed-on 2026-10-02 --closed-on 2026-10-20 --closed-on 2026-11-10 \
  --special-session 2026-11-08
```

On the laptop use `docker compose -p closing-cross-dev -f compose.dev.yaml` in place of the production Compose prefix. The dashboard reads its own environment's saved report at `/api/pilot/backtest`. The verified 19 November result is ₹5,115.60 in equity, ₹988.80 in cash, and three shares held. The ₹115.60 gain is unrealized. There was one buy, on 12 November, at ₹1,336.40 per share including modeled slippage. [NSE market timings and holidays](https://www.nseindia.com/resources/exchange-communication-holidays)

If the older timer was already enabled on the VPS, stop its unit and disable the timer there:

```bash
sudo systemctl disable --now closing-cross-forward.timer
sudo systemctl stop closing-cross-forward.service
```

Current builds default to `FORWARD_ENABLED=false` and skip the forward commands while paused.

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

Locally, run the development startup and fixture commands from **Develop and deploy**. The fixture report at `http://127.0.0.1:5173/api/pilot/paper-ledgers` shows two fills, cash and equity of ₹804.00, zero shares held, and net P&L of −₹196.00. The daily marks include ₹734.00 equity at session 52. Rerun `seed-fixture` and verify the same two fills.

After deploying the ledger build to the VPS, use the latest saved verified scan to build a paper ledger without fetching candles again:

```bash
cd ~/closing-cross-git
sudo docker compose -p closing-cross-prod -f compose.prod.yaml run --rm --build worker closing-cross paper-ledger
```

Inspect `/api/pilot/paper-ledgers` through the tunnel to see the verified paper ledger. Subsequent `scan-nse` runs save it automatically. A historical replay can have zero fills if no eligible crossover occurred or if the allocation could not buy one share. The last crossover can be pending when the next opening candle falls outside the report.

## Forward pilot reference

The saved `RELIANCE` paper ledger worked on the VPS. Use these steps only if the forward pilot is resumed. To resume on a current build, explicitly set `FORWARD_ENABLED=true` in the VPS backend env file. Record three consecutive automatic NSE sessions, including login after midnight, before expanding the watchlist.

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
