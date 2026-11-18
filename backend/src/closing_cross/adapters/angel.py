import json
import os
from datetime import date, datetime
from decimal import Decimal
from uuid import getnode
from zoneinfo import ZoneInfo

import httpx
import pyotp

from closing_cross.domain.candles import Candle, DataError

IST = ZoneInfo('Asia/Kolkata')
BASE_URL = 'https://apiconnect.angelone.in'
LOGIN = '/rest/auth/angelbroking/user/v1/loginByPassword'
SEARCH = '/rest/secure/angelbroking/order/v1/searchScrip'
HISTORY = '/rest/secure/angelbroking/historical/v1/getCandleData'


class SmartAPI:
    def __init__(self, http: httpx.Client):
        self.http = http
        keys = ('ANGEL_API_KEY', 'ANGEL_CLIENT_CODE', 'ANGEL_PIN')
        values = [os.environ.get(key, '').strip() for key in keys]
        missing = [key for key, value in zip(keys, values, strict=True) if not value]
        if missing:
            raise DataError(f'Missing backend settings {", ".join(missing)}')
        api_key, client_code, pin = values
        self._credentials = (client_code, pin)
        mac = f'{getnode():012x}'
        self._headers = {
            'Accept': 'application/json', 'X-PrivateKey': api_key,
            'X-UserType': 'USER', 'X-SourceID': 'WEB',
            'X-ClientLocalIP': os.environ.get('ANGEL_LOCAL_IP') or '127.0.0.1',
            'X-ClientPublicIP': os.environ.get('ANGEL_PUBLIC_IP') or '127.0.0.1',
            'X-MACAddress': ':'.join(mac[i:i+2] for i in range(0, 12, 2)),
        }

    def _post(self, endpoint: str, operation: str, payload: dict[str, str]):
        try:
            response = self.http.post(BASE_URL + endpoint, headers=self._headers, json=payload)
        except httpx.HTTPError:
            raise DataError(f'SmartAPI {operation} request could not be completed') from None
        if not response.is_success:
            raise DataError(f'SmartAPI {operation} returned HTTP {response.status_code}')
        try:
            body = json.loads(response.content, parse_float=Decimal)
        except (ValueError, UnicodeError):
            raise DataError(f'SmartAPI {operation} returned invalid JSON') from None
        if not isinstance(body, dict) or body.get('status') is not True or 'data' not in body:
            code = body.get('errorcode') if isinstance(body, dict) else None
            suffix = f' ({code})' if isinstance(code, str) and len(code) <= 12 and code.isalnum() else ''
            raise DataError(f'SmartAPI {operation} failed{suffix}')
        return body['data']

    def login(self) -> None:
        client_code, pin = self._credentials
        totp = os.environ.get('ANGEL_TOTP_CODE', '').strip()
        if totp:
            if len(totp) != 6 or not totp.isascii() or not totp.isdecimal():
                raise DataError('ANGEL_TOTP_CODE must contain six digits')
        else:
            secret = ''.join(os.environ.get('ANGEL_TOTP_SECRET', '').split()).upper()
            try:
                totp = pyotp.TOTP(secret).now()
            except ValueError:
                raise DataError('Supply a valid ANGEL_TOTP_SECRET setup key or a fresh ANGEL_TOTP_CODE') from None
        data = self._post(LOGIN, 'login', {'clientcode': client_code, 'password': pin, 'totp': totp})
        token = data.get('jwtToken') if isinstance(data, dict) else None
        if not isinstance(token, str) or not token:
            raise DataError('SmartAPI login response did not contain an access token')
        self._headers['Authorization'] = f'Bearer {token}'

    def resolve_equity(self, symbol: str) -> str:
        data = self._post(SEARCH, 'instrument lookup', {'exchange': 'NSE', 'searchscrip': symbol})
        if not isinstance(data, list):
            raise DataError('SmartAPI instrument lookup returned invalid data')
        tokens = {
            str(row.get('symboltoken')) for row in data
            if isinstance(row, dict) and row.get('exchange') == 'NSE'
            and row.get('tradingsymbol') == f'{symbol}-EQ'
        }
        if len(tokens) != 1 or not (token := next(iter(tokens))).isdecimal():
            raise DataError(f'SmartAPI did not resolve a unique NSE {symbol}-EQ token')
        return token

    def daily(self, token: str, start: date, end: date) -> dict[date, Candle]:
        data = self._post(HISTORY, 'daily candles', {
            'exchange': 'NSE', 'symboltoken': token, 'interval': 'ONE_DAY',
            'fromdate': f'{start} 00:00', 'todate': f'{end} 23:59',
        })
        if not isinstance(data, list) or not data:
            raise DataError('SmartAPI returned no daily candles for the requested range')
        candles = {}
        for row in data:
            if not isinstance(row, list) or len(row) != 6:
                raise DataError('SmartAPI returned an invalid daily candle row')
            try:
                timestamp = datetime.fromisoformat(row[0])
                if timestamp.tzinfo is None:
                    raise ValueError
                session = timestamp.astimezone(IST).date()
            except (TypeError, ValueError):
                raise DataError('SmartAPI returned an invalid daily timestamp') from None
            if not start <= session <= end or session in candles:
                raise DataError(f'SmartAPI returned an unexpected or duplicate session {session}')
            candles[session] = Candle.parse(session, row[1:], 'SmartAPI')
        return candles
