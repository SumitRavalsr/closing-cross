import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import httpx

from closing_cross.adapters.backtest import UnsupportedCorporateAction, check_corporate_actions
from closing_cross.adapters.bhavcopy import Bhavcopy
from closing_cross.adapters.index_history import nifty_history
from closing_cross.domain.candles import DataError, FIELDS
from closing_cross.domain.paper import PaperTerms
from closing_cross.domain.portfolio import performance, simulate_portfolio
from closing_cross.scanner.backtest import trading_dates


def read_watchlist(path: Path, costs: PaperTerms) -> tuple[list[str], PaperTerms]:
    try:
        config = json.loads(path.read_text(encoding='utf-8-sig'))
    except (UnicodeError, json.JSONDecodeError):
        raise DataError('Expected a UTF-8 portfolio JSON file') from None
    if not isinstance(config, dict) or not isinstance(config.get('watchlist'), list):
        raise DataError('The portfolio JSON must contain a watchlist of 30 to 50 NSE symbols')
    if not 30 <= len(config['watchlist']) <= 50:
        raise DataError('Enter 30 to 50 distinct NSE equity symbols')
    symbols = []
    for value in config['watchlist']:
        symbol = value.strip().upper() if isinstance(value, str) else ''
        if not re.fullmatch(r'[A-Z0-9&-]{1,24}', symbol) or symbol.endswith('-EQ') or symbol in symbols:
            raise DataError('Watchlist entries must be distinct NSE equity symbols without the -EQ suffix')
        symbols.append(symbol)
    terms = PaperTerms.parse([
        str(config.get('starting_cash', '10000')), str(config.get('max_investment_per_company', '2000')),
        str(costs.fee), str(costs.slippage_per_share),
    ])
    if terms.allocation > terms.opening_cash:
        raise DataError('The per-company limit cannot exceed starting cash')
    return symbols, terms


def run_portfolio(
    http: httpx.Client, symbols: list[str], terms: PaperTerms, start: date,
    warmup: date, end: date, closures: set[date], special: set[date],
) -> dict:
    def action_issue(symbol: str) -> str | None:
        try:
            check_corporate_actions(http, symbol, warmup, end)
        except UnsupportedCorporateAction as error:
            return str(error)
        return None

    dates = trading_dates(warmup, end, closures, special)
    excluded = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for symbol, issue in zip(symbols, pool.map(action_issue, symbols), strict=True):
            if issue:
                excluded[symbol] = issue

        eligible = set(symbols) - excluded.keys()
        if not eligible:
            raise DataError('All watchlist companies had unsupported corporate actions')
        source = Bhavcopy(http)
        history = {}
        for day, rows in zip(dates, pool.map(lambda day: source.read_many(day, eligible), dates), strict=True):
            if rows is None:
                raise DataError(f'Final NSE bhavcopy is missing for {day}. Check the exchange calendar.')
            history[day] = rows
            for symbol in eligible:
                if symbol not in excluded and (symbol not in rows or rows[symbol].volume == 0):
                    excluded[symbol] = f'No traded NSE EQ candle for {day}'

    tested = [symbol for symbol in symbols if symbol not in excluded]
    if not tested:
        raise DataError('No watchlist company had complete, supported market data for this backtest')
    result = simulate_portfolio(history, tested, start, terms)
    funded = [day for day in dates if day >= start]
    index_closes = nifty_history(http, funded)
    closes = [index_closes[day] for day in funded]
    inputs = [
        [day.isoformat(), [[symbol, *(str(getattr(rows[symbol], field)) for field in FIELDS)] for symbol in tested]]
        for day, rows in history.items()
    ]
    return {
        'mode': 'portfolio_backtest', 'strategy': '20-50-raw-v1', 'source': 'NSE final bhavcopy',
        'funded_on': start.isoformat(), 'first_session': result['daily'][0]['session'], 'last_session': end.isoformat(),
        'watchlist': symbols, 'tested': tested,
        'excluded': [{'symbol': symbol, 'reason': excluded[symbol]} for symbol in symbols if symbol in excluded],
        'terms': {name: str(value) for name, value in vars(terms).items()},
        'input_hash': hashlib.sha256(json.dumps(inputs, separators=(',', ':')).encode('utf-8')).hexdigest(),
        'benchmark': {
            'name': 'Nifty 50 Price Index',
            'source': 'NSE historical index data and daily close archives',
            **performance(closes, closes[0]),
            'daily': [{'session': day.isoformat(), 'close': str(close)}
                      for day, close in zip(funded, closes, strict=True)],
        },
        **result,
    }
