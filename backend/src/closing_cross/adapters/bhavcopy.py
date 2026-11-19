import csv
import io
from datetime import date
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import httpx

from closing_cross.domain.candles import Candle, DataError

ARCHIVE = 'https://archives.nseindia.com/content/cm/'
MIRROR = 'https://nsearchives.nseindia.com/content/cm/'
PRICE_COLUMNS = ('OpnPric', 'HghPric', 'LwPric', 'ClsPric', 'TtlTradgVol')


class Bhavcopy:
    def __init__(self, http: httpx.Client, directory: Path | None = None):
        self.http = http
        self.directory = directory

    def read(self, session: date, symbol: str) -> Candle | None:
        result = self.read_many(session, {symbol})
        if result is None:
            return None
        if symbol not in result:
            raise DataError(f'NSE bhavcopy did not contain one matching {symbol}-EQ row for {session}')
        return result[symbol]

    def read_many(self, session: date, symbols: set[str]) -> dict[str, Candle] | None:
        filename = f'BhavCopy_NSE_CM_0_0_0_{session:%Y%m%d}_F_0000.csv.zip'
        if self.directory is not None:
            try:
                data = (self.directory / filename).read_bytes()
            except FileNotFoundError:
                return None
        else:
            for archive in (ARCHIVE, MIRROR):
                try:
                    response = self.http.get(archive + filename)
                except httpx.HTTPError:
                    continue
                if response.status_code == 404:
                    return None
                if response.is_success:
                    data = response.content
                    break
            else:
                raise DataError(f'NSE bhavcopy download failed for {session} on both archive hosts. Try --bhavcopy-dir.')
        return parse_bhavcopy_rows(data, filename[:-4], session, symbols)


def parse_bhavcopy_rows(data: bytes, csv_name: str, session: date, symbols: set[str]) -> dict[str, Candle]:
    candles = {}
    try:
        with ZipFile(io.BytesIO(data)) as archive, archive.open(csv_name) as stream:
            reader = csv.DictReader(io.TextIOWrapper(stream, encoding='utf-8-sig', newline=''))
            required = {'TradDt', 'TckrSymb', 'SctySrs', *PRICE_COLUMNS}
            if not required.issubset(reader.fieldnames or ()):
                raise DataError(f'NSE bhavcopy has unexpected columns for {session}')
            for row in reader:
                symbol = row['TckrSymb']
                if symbol not in symbols or row['SctySrs'] != 'EQ':
                    continue
                if symbol in candles or row['TradDt'] != session.isoformat():
                    raise DataError(f'NSE bhavcopy did not contain one matching {symbol}-EQ row for {session}')
                candles[symbol] = Candle.parse(session, [row[key] for key in PRICE_COLUMNS], 'NSE bhavcopy')
    except (BadZipFile, KeyError, UnicodeError, csv.Error):
        raise DataError(f'NSE bhavcopy is unreadable for {session}') from None
    return candles
