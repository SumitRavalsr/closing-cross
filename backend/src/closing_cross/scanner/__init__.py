import argparse
import json
import os
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import httpx

from closing_cross.adapters.angel import SmartAPI
from closing_cross.adapters.backtest import check_corporate_actions, store_backtest
from closing_cross.adapters.bhavcopy import Bhavcopy
from closing_cross.adapters.database import connect, migrate
from closing_cross.adapters.paper import save_ledger
from closing_cross.domain.candles import DataError
from closing_cross.domain.paper import PaperSession, PaperTerms, build_ledger
from closing_cross.domain.strategy import crossover
from closing_cross.scanner.backtest import backtest, load_history
from closing_cross.scanner.forward import initialize, run_forward
from closing_cross.scanner.portfolio import read_watchlist, run_portfolio
from closing_cross.scanner.verified import build_latest_ledger, save_report, validate_range, verify_and_scan
from closing_cross.settings import paper_terms


def seed_fixture() -> None:
    closes = [Decimal(100)] * 50 + [Decimal(110), Decimal(80), Decimal(90)]
    opens = [Decimal(100)] * 51 + [Decimal(112), Decimal(90)]
    sessions = [
        PaperSession(str(number), opening, close, crossover(closes[:number]))
        for number, (opening, close) in enumerate(zip(opens, closes, strict=True), start=1)
    ]
    ledger = {'symbol': 'FIXTURE', 'strategy': '20-50-raw-v1', **build_ledger(sessions, PaperTerms())}
    with connect() as connection:
        for day in sessions:
            if day.cross:
                connection.execute(
                    """
                    INSERT INTO pilot_signals VALUES (?, ?, ?)
                    ON CONFLICT (symbol, session_number) DO NOTHING
                    """,
                    ("FIXTURE", int(day.session), day.cross),
                )
        save_ledger(connection, ledger)


def main() -> None:
    parser = argparse.ArgumentParser(description="Closing crossover pilot")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate")
    commands.add_parser("seed-fixture")
    commands.add_parser("paper-ledger", help="Build paper accounting for the latest saved verified scan")
    historical = commands.add_parser("backtest-nse", help="Run a funded historical backtest from public NSE bhavcopy")
    portfolio = commands.add_parser("backtest-portfolio", help="Backtest a JSON watchlist using shared cash")
    for command in (historical, portfolio):
        command.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
        command.add_argument("--through", type=date.fromisoformat, required=True)
        command.add_argument("--warmup-from", type=date.fromisoformat, required=True)
        command.add_argument("--closed-on", action="append", type=date.fromisoformat, default=[])
        command.add_argument("--special-session", action="append", type=date.fromisoformat, default=[])
    historical.add_argument("--cash", default="5000.00", help="Opening cash and maximum position allocation in INR")
    portfolio.add_argument("--watchlist", type=Path, required=True, help="JSON configuration file")
    forward_init = commands.add_parser("forward-init", help="Start a flat forward portfolio from a verified seed")
    forward_init.add_argument("--calendar", type=Path, required=True)
    forward_init.add_argument("--session", type=date.fromisoformat, required=True, help="First forward session")
    forward_scan = commands.add_parser("forward-scan", help="Process due forward sessions in calendar order")
    forward_scan.add_argument("--calendar", type=Path, required=True)
    forward_scan.add_argument("--session", type=date.fromisoformat, help="Optional last session to process")
    scan = commands.add_parser("scan-nse", help="Verify and replay one NSE EQ stock")
    scan.add_argument("--session", type=date.fromisoformat, required=True, help="Final NSE session, YYYY-MM-DD")
    scan.add_argument("--start", type=date.fromisoformat, help="First date to verify, defaults to a 101-day window")
    scan.add_argument("--closed-on", action="append", type=date.fromisoformat, default=[],
                      help="Confirmed NSE weekday holiday, repeat as needed")
    scan.add_argument("--bhavcopy-dir", type=Path, help="Read original final NSE ZIPs from this directory")
    scan.add_argument("--confirm-no-split-bonus", action="store_true", required=True,
                      help="Confirm the selected window has no split or bonus for this symbol")
    arguments = parser.parse_args()
    if arguments.command == "migrate":
        migrate()
    elif arguments.command == "seed-fixture":
        seed_fixture()
    elif arguments.command in {"backtest-nse", "backtest-portfolio"}:
        try:
            costs = paper_terms()
            is_portfolio = arguments.command == 'backtest-portfolio'
            if is_portfolio:
                symbols, terms = read_watchlist(arguments.watchlist, costs)
            else:
                symbols = [os.environ.get("PILOT_NSE_SYMBOL", "RELIANCE").strip().upper()]
                terms = PaperTerms.parse([arguments.cash, arguments.cash, str(costs.fee), str(costs.slippage_per_share)])
            symbol = symbols[0]
            closures, special = set(arguments.closed_on), set(arguments.special_session)
            validate_range(symbol, arguments.warmup_from, arguments.through, closures, max_days=466 if is_portfolio else 366)
            if not arguments.warmup_from < arguments.start <= arguments.through:
                raise DataError('Choose funding and end dates after the candle warm-up start')
            if special & closures or any(not arguments.warmup_from <= day <= arguments.through for day in special):
                raise DataError('Special sessions must be within the candle range and cannot also be holidays')
            with httpx.Client(timeout=20, follow_redirects=False) as http:
                if is_portfolio:
                    report = run_portfolio(http, symbols, terms, arguments.start, arguments.warmup_from,
                                           arguments.through, closures, special)
                else:
                    check_corporate_actions(http, symbol, arguments.warmup_from, arguments.through)
                    candles = load_history(Bhavcopy(http), symbol, arguments.warmup_from, arguments.through, closures, special)
                    report = backtest(candles, symbol, arguments.start, terms)
            migrate()
            report_id = store_backtest(report)
            print(json.dumps({
                'id': report_id, **({'tested': len(report['tested']), 'excluded': len(report['excluded'])}
                                    if is_portfolio else {'symbol': symbol}), 'funded_on': report['funded_on'],
                'first_session': report['first_session'], 'last_session': report['last_session'],
                **report['summary'], 'fills': len(report['fills']),
            }, indent=2))
        except (DataError, OSError) as error:
            parser.exit(1, f"Backtest stopped. {error}\n")
    elif arguments.command == "paper-ledger":
        try:
            terms = paper_terms()
            migrate()
            print(json.dumps({"paper_ledger_id": build_latest_ledger(terms)}))
        except DataError as error:
            parser.exit(1, f"Paper ledger stopped. {error}\n")
    elif arguments.command in {"forward-init", "forward-scan"}:
        if os.environ.get("FORWARD_ENABLED", "").lower() != "true":
            parser.exit(0, "Forward paper pilot is paused.\n")
        try:
            migrate()
            if arguments.command == "forward-init":
                symbol = os.environ.get("PILOT_NSE_SYMBOL", "RELIANCE").strip().upper()
                result = initialize(arguments.calendar, arguments.session, paper_terms(), symbol)
            else:
                try:
                    reviewed = date.fromisoformat(os.environ.get("FORWARD_ACTIONS_REVIEWED_THROUGH", ""))
                except ValueError:
                    raise DataError("Set FORWARD_ACTIONS_REVIEWED_THROUGH to the last reviewed NSE date") from None
                result = run_forward(arguments.calendar, reviewed, arguments.session)
            print(json.dumps(result, indent=2))
        except (DataError, OSError) as error:
            parser.exit(1, f"Forward scan stopped. {error}\n")
    else:
        try:
            terms = paper_terms()
            symbol = os.environ.get("PILOT_NSE_SYMBOL", "RELIANCE").strip().upper()
            end = arguments.session
            start = arguments.start or end - timedelta(days=100)
            closures = set(arguments.closed_on)
            validate_range(symbol, start, end, closures)
            directory = arguments.bhavcopy_dir
            if directory is not None and not directory.is_dir():
                raise DataError("--bhavcopy-dir must be an existing directory")
            with httpx.Client(timeout=15, follow_redirects=False) as http:
                broker = SmartAPI(http)
                broker.login()
                report = verify_and_scan(broker, Bhavcopy(http, directory), symbol, start, end, closures)
            migrate()
            result = save_report(report, terms)
        except (DataError, OSError) as error:
            print(f"Scan stopped. {error}", file=sys.stderr)
            raise SystemExit(1) from None
        latest = result["candles"][-1]
        print(json.dumps({
            "id": result["id"], "symbol": symbol, "token": result["token"], "session": result["session"],
            "verified_sessions": result["verified_sessions"], "sma20": latest["sma20"],
            "sma50": latest["sma50"], "cross": latest["cross"], "paper_ledger_id": result["paper_ledger_id"],
        }, indent=2))
