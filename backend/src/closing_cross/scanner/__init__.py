import argparse
import json
import os
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import httpx

from closing_cross.adapters.angel import SmartAPI
from closing_cross.adapters.bhavcopy import Bhavcopy
from closing_cross.adapters.database import connect, migrate
from closing_cross.domain.candles import DataError
from closing_cross.domain.strategy import crossover
from closing_cross.scanner.verified import save_report, validate_range, verify_and_scan


def seed_fixture() -> None:
    closes = [Decimal(100)] * 50 + [Decimal(110), Decimal(80)]
    with connect() as connection:
        for session_number in range(51, len(closes) + 1):
            direction = crossover(closes[:session_number])
            if direction:
                connection.execute(
                    """
                    INSERT INTO pilot_signals VALUES (?, ?, ?)
                    ON CONFLICT (symbol, session_number) DO NOTHING
                    """,
                    ("FIXTURE", session_number, direction),
                )


def main() -> None:
    parser = argparse.ArgumentParser(description="Closing crossover pilot")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate")
    commands.add_parser("seed-fixture")
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
    else:
        try:
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
            result = save_report(report)
        except (DataError, OSError) as error:
            print(f"Scan stopped. {error}", file=sys.stderr)
            raise SystemExit(1) from None
        latest = result["candles"][-1]
        print(json.dumps({
            "id": result["id"], "symbol": symbol, "token": result["token"], "session": result["session"],
            "verified_sessions": result["verified_sessions"], "sma20": latest["sma20"],
            "sma50": latest["sma50"], "cross": latest["cross"],
        }, indent=2))
