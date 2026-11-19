import hashlib
import json
from datetime import date

import httpx

from closing_cross.adapters.database import connect
from closing_cross.domain.candles import DataError

CORPORATE_ACTIONS = 'https://www.nseindia.in/api/corporates-corporateActions'


class UnsupportedCorporateAction(DataError):
    pass


def check_corporate_actions(http: httpx.Client, symbol: str, start: date, end: date) -> None:
    try:
        response = http.get(CORPORATE_ACTIONS, params={
            'index': 'equities', 'symbol': symbol,
            'from_date': start.strftime('%d-%m-%Y'), 'to_date': end.strftime('%d-%m-%Y'),
        }, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.nseindia.in/companies-listing/corporate-filings-actions'})
        response.raise_for_status()
        actions = response.json()
    except (httpx.HTTPError, ValueError):
        raise DataError('Could not verify the backtest window against NSE corporate actions') from None
    if not isinstance(actions, list) or any(
        not isinstance(row, dict) or row.get('symbol') != symbol or not isinstance(row.get('subject'), str)
        for row in actions
    ):
        raise DataError('NSE returned unexpected corporate-action data')
    for action in actions:
        if action.get('series') == 'EQ' and any(
            keyword in action['subject'].lower()
            for keyword in ('bonus', 'split', 'sub-division', 'subdivision', 'demerger', 'amalgamation')
        ):
            raise UnsupportedCorporateAction(f'Unsupported corporate action for {symbol} on {action.get("exDate")}')


def store_backtest(report: dict) -> int:
    encoded = json.dumps(report, sort_keys=True, separators=(',', ':'))
    digest = hashlib.sha256(encoded.encode('utf-8')).hexdigest()
    with connect() as connection:
        connection.execute(
            'INSERT INTO backtests (result_hash, report) VALUES (?, ?) ON CONFLICT (result_hash) DO NOTHING',
            (digest, encoded),
        )
        return connection.execute('SELECT id FROM backtests WHERE result_hash = ?', (digest,)).fetchone()['id']


def latest_backtest() -> dict | None:
    with connect(readonly=True) as connection:
        row = connection.execute('SELECT id, report FROM backtests ORDER BY id DESC LIMIT 1').fetchone()
    return {**json.loads(row['report']), 'id': row['id']} if row else None
