import csv
import io
from datetime import date
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import httpx

from closing_cross.domain.candles import Candle, DataError

ARCHIVE = 'https://archives.nseindia.com/content/cm/'
PRICE_COLUMNS = ('OpnPric', 'HghPric', 'LwPric', 'ClsPric', 'TtlTradgVol')


class Bhavcopy:
    def __init__(self, http: httpx.Client, directory: Path | None = None):
        self.http = http
        self.directory = directory

    def read(self, session: date, symbol: str) -> Candle | None:
        filename = f'BhavCopy_NSE_CM_0_0_0_{session:%Y%m%d}_F_0000.csv.zip'
        if self.directory is not None:
            try:
                data = (self.directory / filename).read_bytes()
            except FileNotFoundError:
                return None
        else:
            try:
                response = self.http.get(ARCHIVE + filename)
            except httpx.HTTPError:
                raise DataError(f'NSE bhavcopy download failed for {session}. Try --bhavcopy-dir.') from None
            if response.status_code == 404:
                return None
            if not response.is_success:
                raise DataError(f'NSE bhavcopy returned HTTP {response.status_code} for {session}. Try --bhavcopy-dir.')
            data = response.content
        return parse_bhavcopy(data, filename[:-4], session, symbol)


def parse_bhavcopy(data: bytes, csv_name: str, session: date, symbol: str) -> Candle:
    try:
        with ZipFile(io.BytesIO(data)) as archive, archive.open(csv_name) as stream:
            reader = csv.DictReader(io.TextIOWrapper(stream, encoding='utf-8-sig', newline=''))
            required = {'TradDt', 'TckrSymb', 'SctySrs', *PRICE_COLUMNS}
            if not required.issubset(reader.fieldnames or ()):
                raise DataError(f'NSE bhavcopy has unexpected columns for {session}')
            rows = [row for row in reader if row['TckrSymb'] == symbol and row['SctySrs'] == 'EQ']
    except (BadZipFile, KeyError, UnicodeError, csv.Error):
        raise DataError(f'NSE bhavcopy is unreadable for {session}') from None
    if len(rows) != 1 or rows[0]['TradDt'] != session.isoformat():
        raise DataError(f'NSE bhavcopy did not contain one matching {symbol}-EQ row for {session}')
    return Candle.parse(session, [rows[0][key] for key in PRICE_COLUMNS], 'NSE bhavcopy')
