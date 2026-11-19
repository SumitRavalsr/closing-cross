import csv
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import httpx

from closing_cross.domain.candles import DataError

INDEX_ARCHIVES = (
    'https://nsearchives.nseindia.com/content/indices/',
    'https://archives.nseindia.com/content/indices/',
)
INDEX_HISTORY = 'https://www.nseindia.in/api/historicalOR/indicesHistory'


def nifty_history(http: httpx.Client, sessions: list[date]) -> dict[date, Decimal]:
    closes = {}
    # The exchange endpoint returns at most 70 records per request.
    for offset in range(0, len(sessions), 60):
        first = sessions[offset]
        last = sessions[min(offset + 59, len(sessions) - 1)]
        try:
            response = http.get(INDEX_HISTORY, params={
                'indexType': 'NIFTY 50', 'from': first.strftime('%d-%m-%Y'), 'to': last.strftime('%d-%m-%Y'),
            }, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
            response.raise_for_status()
            rows = response.json(parse_float=Decimal)['data']
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            continue
        try:
            for row in rows:
                session = datetime.strptime(row['EOD_TIMESTAMP'], '%d-%b-%Y').date()
                close = Decimal(row['EOD_CLOSE_INDEX_VAL'])
                if row['EOD_INDEX_NAME'] != 'NIFTY 50' or not first <= session <= last or session in closes:
                    raise ValueError
                if not close.is_finite() or close <= 0:
                    raise ValueError
                closes[session] = close
        except (ValueError, KeyError, TypeError, InvalidOperation):
            raise DataError(f'Invalid NSE Nifty 50 history for {first} through {last}') from None

    missing = [day for day in sessions if day not in closes]
    if missing:
        with ThreadPoolExecutor(max_workers=4) as pool:
            closes.update(zip(missing, pool.map(lambda day: nifty_close(http, day), missing), strict=True))
    return closes


def nifty_close(http: httpx.Client, session: date) -> Decimal:
    filename = f'ind_close_all_{session:%d%m%Y}.csv'
    for archive in INDEX_ARCHIVES:
        try:
            response = http.get(archive + filename, headers={'Accept': 'text/csv'})
            response.raise_for_status()
        except httpx.HTTPError:
            continue
        break
    else:
        raise DataError(f'Nifty 50 index archive unavailable for {session} from both NSE hosts')

    try:
        rows = csv.DictReader(io.StringIO(response.content.decode('utf-8-sig')))
        match, = (row for row in rows if row['Index Name'].strip() == 'Nifty 50')
        reported = datetime.strptime(match['Index Date'].strip(), '%d-%m-%Y').date()
        close = Decimal(match['Closing Index Value'].strip())
        if reported != session or not close.is_finite() or close <= 0:
            raise ValueError
    except (KeyError, AttributeError, UnicodeError, ValueError, InvalidOperation, csv.Error):
        raise DataError(f'Invalid Nifty 50 closing index value for {session}') from None
    return close
