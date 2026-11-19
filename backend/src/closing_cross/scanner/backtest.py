from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal

from closing_cross.adapters.bhavcopy import Bhavcopy
from closing_cross.domain.candles import Candle, DataError, FIELDS
from closing_cross.domain.paper import PaperSession, PaperTerms, build_ledger
from closing_cross.domain.strategy import crossover


def trading_dates(warmup: date, end: date, closures: set[date], special: set[date]) -> list[date]:
    dates = [warmup + timedelta(days=offset) for offset in range((end - warmup).days + 1)]
    # Regular trading weekdays plus explicitly confirmed live special sessions.
    sessions = [day for day in dates if (day.weekday() < 5 or day in special) and day not in closures]
    if not sessions or sessions[-1] != end:
        raise DataError('The backtest end date must be an NSE trading session')
    return sessions


def load_history(
    source: Bhavcopy, symbol: str, warmup: date, end: date, closures: set[date], special: set[date],
) -> list[Candle]:
    sessions = trading_dates(warmup, end, closures, special)
    history = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for day, candle in zip(sessions, pool.map(lambda session: source.read(session, symbol), sessions), strict=True):
            if candle is None or candle.volume == 0:
                raise DataError(f'No final traded NSE candle for {day}. Check the date and exchange calendar.')
            history.append(candle)
    return history


def backtest(candles: list[Candle], symbol: str, start: date, terms: PaperTerms) -> dict:
    closes: list[Decimal] = []
    sessions = []
    for candle in candles:
        closes.append(candle.close)
        if candle.session >= start:
            if len(closes) < 51:
                raise DataError('Include at least 50 NSE sessions before the first funded session')
            sessions.append(PaperSession(candle.session.isoformat(), candle.open, candle.close, crossover(closes)))
    ledger = build_ledger(sessions, terms)
    fills = {fill['fill_session']: fill for fill in ledger['fills']}
    for row in ledger['daily']:
        fill = fills.get(row['session'])
        row['action'] = fill['side'] if fill else ('hold_shares' if row['shares'] else 'hold_cash')
    return {
        'mode': 'backtest', 'symbol': symbol, 'strategy': '20-50-raw-v1', 'source': 'NSE final bhavcopy',
        'funded_on': start.isoformat(), 'first_session': sessions[0].session,
        'last_session': sessions[-1].session, 'warmup_sessions': len(candles) - len(sessions),
        'candles': [{'session': c.session.isoformat(), **{field: str(getattr(c, field)) for field in FIELDS}} for c in candles],
        **ledger,
    }
