import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from closing_cross.adapters.angel import IST, SmartAPI
from closing_cross.adapters.bhavcopy import Bhavcopy
from closing_cross.adapters.database import connect
from closing_cross.adapters.paper import save_ledger
from closing_cross.domain.candles import FIELDS, Candle, DataError
from closing_cross.domain.paper import PaperSession, PaperTerms, build_ledger
from closing_cross.domain.strategy import crossover, moving_averages


def decimal_text(value: Decimal) -> str:
    return format(value.normalize(), 'f')


def verify_and_scan(
    broker: SmartAPI,
    nse: Bhavcopy,
    symbol: str,
    start: date,
    end: date,
    closures: set[date],
) -> dict:
    token = broker.resolve_equity(symbol)
    candles = broker.daily(token, start, end)
    verified: list[Candle] = []
    unknown_dates = []
    for offset in range((end - start).days + 1):
        session = start + timedelta(days=offset)
        actual = candles.get(session)
        reference = nse.read(session, symbol)
        if reference is None:
            if actual or session == end:
                raise DataError(f'Final NSE bhavcopy is missing for {session}')
            if session.weekday() < 5 and session not in closures:
                unknown_dates.append(session.isoformat())
            continue
        if session in closures:
            raise DataError(f'NSE published a trading session for declared closure {session}')
        if actual is None:
            raise DataError(f'SmartAPI is missing the NSE trading session {session}')
        differences = [
            f'{field} SmartAPI={getattr(actual, field)} NSE={getattr(reference, field)}'
            for field in FIELDS if getattr(actual, field) != getattr(reference, field)
        ]
        if differences:
            raise DataError(f'{symbol}-EQ mismatch on {session}: {", ".join(differences)}')
        verified.append(actual)
    if unknown_dates:
        raise DataError('Missing NSE weekday archives for ' + ', '.join(unknown_dates)
                        + '. Supply the reports or use --closed-on for confirmed NSE holidays.')
    if len(verified) < 51:
        raise DataError(f'At least 51 verified sessions are required. Found {len(verified)}.')
    rows = []
    closes = []
    for candle in verified:
        closes.append(candle.close)
        averages = moving_averages(closes) if len(closes) >= 50 else (None, None)
        rows.append({
            'session': candle.session.isoformat(),
            **{field: decimal_text(getattr(candle, field)) for field in FIELDS},
            'sma20': decimal_text(averages[0]) if averages[0] is not None else None,
            'sma50': decimal_text(averages[1]) if averages[1] is not None else None,
            'cross': crossover(closes),
        })
    return {
        'symbol': symbol, 'series': 'EQ', 'exchange': 'NSE', 'token': token,
        'start': start.isoformat(), 'session': end.isoformat(),
        'strategy': '20-50-raw-v1', 'mode': 'verified_replay',
        'verified_sessions': len(rows), 'confirmed_closures': sorted(d.isoformat() for d in closures),
        'candles': rows,
    }


def validate_range(symbol: str, start: date, end: date, closures: set[date]) -> None:
    if not re.fullmatch(r'[A-Z0-9&-]{1,24}', symbol) or symbol.endswith('-EQ'):
        raise DataError('Configure one NSE cash symbol without the -EQ series suffix')
    if not 50 <= (end - start).days <= 365 or end > datetime.now(IST).date():
        raise DataError('Choose an NSE session through today and a 51-366 calendar-day inclusive range')
    if any(not start <= day < end for day in closures):
        raise DataError('Each declared exchange closure must be within the lookback and before the target')


def verified_ledger(report: dict, terms: PaperTerms) -> dict:
    sessions = [
        PaperSession(row['session'], Decimal(row['open']), Decimal(row['close']), row['cross'])
        for row in report['candles']
    ]
    return {'symbol': report['symbol'], 'strategy': report['strategy'], **build_ledger(sessions, terms)}


def save_report(report: dict, terms: PaperTerms) -> dict:
    encoded = json.dumps(report, sort_keys=True, separators=(',', ':'))
    digest = hashlib.sha256(encoded.encode('utf-8')).hexdigest()
    observed = datetime.now(timezone.utc).isoformat()
    ledger = verified_ledger(report, terms)
    with connect() as connection:
        connection.execute(
            'INSERT INTO verified_scans (input_hash, observed_at, report) VALUES (?, ?, ?) '
            'ON CONFLICT (input_hash) DO NOTHING', (digest, observed, encoded),
        )
        row = connection.execute(
            'SELECT id, observed_at FROM verified_scans WHERE input_hash = ?', (digest,),
        ).fetchone()
        ledger_id = save_ledger(connection, ledger, row['id'])
    return {**report, 'id': row['id'], 'observed_at': row['observed_at'], 'paper_ledger_id': ledger_id}


def build_latest_ledger(terms: PaperTerms) -> int:
    with connect() as connection:
        row = connection.execute('SELECT id, report FROM verified_scans ORDER BY id DESC LIMIT 1').fetchone()
        if row is None:
            raise DataError('No saved verified NSE scan is available')
        return save_ledger(connection, verified_ledger(json.loads(row['report']), terms), row['id'])
