import json
import sqlite3
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

from closing_cross.adapters.angel import SmartAPI
from closing_cross.adapters.bhavcopy import Bhavcopy
from closing_cross.adapters.calendar import IST, TradingSession, read_calendar
from closing_cross.adapters.database import connect
from closing_cross.adapters.forward import finish_attempt, load_state, start_attempt
from closing_cross.domain.candles import Candle, DataError
from closing_cross.domain.forward import advance
from closing_cross.domain.paper import PaperTerms
from closing_cross.scanner.verified import match_candle


def initialize(path: Path, first: date, terms: PaperTerms, symbol: str) -> dict:
    calendar, _ = read_calendar(path)
    days = [session.day for session in calendar]
    if first not in days[1:-1]:
        raise DataError('First forward date must have both a preceding and a following session in the calendar')
    previous = days.index(first) - 1
    with connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        existing = connection.execute('SELECT state FROM forward_portfolio WHERE id = 1').fetchone()
        if existing:
            state = json.loads(existing['state'])
            if state['first_session'] == first.isoformat() and state['symbol'] == symbol:
                return {'symbol': symbol, 'first_session': state['first_session'], 'status': 'already_initialized'}
            raise DataError('A forward portfolio is already initialized')

        row = connection.execute('SELECT id, report FROM verified_scans ORDER BY id DESC LIMIT 1').fetchone()
        report = json.loads(row['report']) if row else None
        if not report or report['symbol'] != symbol or report['session'] != days[previous].isoformat():
            raise DataError(f'Latest verified scan must be for {symbol} through {days[previous]}')
        if len(report['candles']) < 50:
            raise DataError('Verified seed must contain at least 50 closes')
        state = {
            'symbol': symbol, 'token': report['token'], 'seed_scan_id': row['id'], 'strategy': report['strategy'],
            'first_session': first.isoformat(), 'last_session': report['session'],
            'next_due_at': calendar[previous + 1].ready_at.isoformat(),
            'terms': {name: str(value) for name, value in vars(terms).items()},
            'closes': [item['close'] for item in report['candles'][-50:]],
            'cash': str(terms.opening_cash), 'shares': 0, 'entry_cost': '0.00', 'realized': '0.00', 'pending': None,
        }
        connection.execute('INSERT INTO forward_portfolio (id, state) VALUES (1, ?)', (json.dumps(state),))
    return {'symbol': symbol, 'first_session': first.isoformat(), 'status': 'initialized'}


def commit_session(
    candle: Candle, index: int, calendar: list[TradingSession], observed: datetime, calendar_hash: str,
) -> bool:
    day = candle.session.isoformat()
    with connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        state = json.loads(connection.execute('SELECT state FROM forward_portfolio WHERE id = 1').fetchone()['state'])
        if state['last_session'] >= day:
            return False
        if state['last_session'] != calendar[index - 1].day.isoformat():
            raise DataError('An earlier forward session is still missing')
        pending = state['pending']
        if pending and pending['target_session'] and pending['target_session'] < day:
            raise DataError('The calendar omitted a pending fill session')
        if pending and pending['target_session'] == day and datetime.fromisoformat(pending['observed_at']) >= calendar[index].opens_at:
            raise DataError('Updated calendar puts the pending fill open before its signal was observed')
        updated, result = advance(state, candle, observed, [item.opens_at for item in calendar[index + 1:]], calendar_hash)
        updated['next_due_at'] = calendar[index + 1].ready_at.isoformat()
        connection.execute('INSERT INTO forward_sessions (session, result) VALUES (?, ?)', (day, json.dumps(result)))
        connection.execute('UPDATE forward_portfolio SET state = ? WHERE id = 1', (json.dumps(updated),))
    return True


def run_forward(
    calendar_path: Path, reviewed_through: date, target: date | None = None,
    *, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict:
    started = clock()
    attempt = start_attempt(started)
    target_label = target.isoformat() if target else None
    processed = 0
    try:
        state = load_state()
        calendar, digest = read_calendar(calendar_path)
        days = [item.day for item in calendar]
        previous = date.fromisoformat(state['last_session'])
        if previous not in days:
            raise DataError('The calendar must retain the last committed session')
        if target is None and started.astimezone(IST).date() > days[-1]:
            raise DataError('The forward calendar has expired')
        if target is not None and (target not in days or calendar[days.index(target)].ready_at > started):
            raise DataError('The selected session is absent from the calendar or its publication window has not opened')
        due = [index for index in range(days.index(previous) + 1, len(days))
               if calendar[index].ready_at <= started and (target is None or days[index] <= target)]
        if due:
            start, end = days[due[0]], days[due[-1]]
            target_label = end.isoformat()
            if end > reviewed_through:
                raise DataError(f'Review splits and bonuses for {state["symbol"]} through {end} before scanning')
            if due[-1] == len(days) - 1:
                raise DataError('Extend the calendar to include the session after the scan target')

            with httpx.Client(timeout=15, follow_redirects=False) as http:
                broker = SmartAPI(http)
                broker.login()
                symbol = state['symbol']
                token = broker.resolve_equity(symbol)
                if token != state['token']:
                    raise DataError('SmartAPI token differs from the verified seed report')
                candles = broker.daily(token, start, end)
                bhavcopy = Bhavcopy(http)
                for index in due:
                    day = days[index]
                    reference = bhavcopy.read(day, symbol)
                    if reference is None:
                        raise DataError(f'Final NSE bhavcopy is missing for {day}')
                    candle = match_candle(candles.get(day), reference, symbol, day)
                    if candle.volume == 0:
                        raise DataError(f'Zero-volume session {day} requires manual review')
                    processed += commit_session(candle, index, calendar, clock(), digest)
    except (DataError, OSError, sqlite3.Error) as error:
        message = f'{error} ({processed} sessions committed before stopping)'
        finish_attempt(attempt, clock(), target_label, 'failed', message)
        raise DataError(message) from None

    status = 'complete' if processed else 'idle'
    finish_attempt(attempt, clock(), target_label, status, f'{processed} forward sessions committed')
    return {'status': status, 'target': target_label, 'processed': processed}
