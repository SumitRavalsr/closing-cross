import json
import os
import re
from decimal import Decimal
from time import monotonic
from uuid import getnode
from zoneinfo import ZoneInfo

import httpx
import pyotp

from angel_one_mcp.smartapi.credentials import AngelCredentials
from angel_one_mcp.smartapi.errors import BrokerError

IST = ZoneInfo('Asia/Kolkata')
BASE_URL = 'https://apiconnect.angelone.in'
LOGIN = '/rest/auth/angelbroking/user/v1/loginByPassword'
REFRESH = '/rest/auth/angelbroking/jwt/v1/generateTokens'
SEARCH = '/rest/secure/angelbroking/order/v1/searchScrip'
HISTORY = '/rest/secure/angelbroking/historical/v1/getCandleData'


class SmartAPISessionExpired(BrokerError):
    pass


class SmartAPI:
    def __init__(self, http: httpx.Client):
        self.http = http
        self._credentials = AngelCredentials.load()
        self._refresh_token: str | None = None
        self._feed_token: str | None = None
        mac = f'{getnode():012x}'
        self._headers = {
            'Accept': 'application/json', 'Content-Type': 'application/json', 'Accept-Encoding': 'identity',
            'X-PrivateKey': self._credentials.api_key,
            'X-UserType': 'USER', 'X-SourceID': 'WEB',
            'X-ClientLocalIP': os.environ.get('ANGEL_LOCAL_IP') or '127.0.0.1',
            'X-ClientPublicIP': os.environ.get('ANGEL_PUBLIC_IP') or '127.0.0.1',
            'X-MACAddress': ':'.join(mac[i:i+2] for i in range(0, 12, 2)),
        }

    def _request(self, method: str, endpoint: str, operation: str, payload: dict | None = None):
        deadline = monotonic() + 30
        try:
            with self.http.stream(method, BASE_URL + endpoint, headers=self._headers, json=payload,
                                  follow_redirects=False) as response:
                if response.status_code == 401 and endpoint != LOGIN:
                    raise SmartAPISessionExpired('SmartAPI session expired')
                if not response.is_success:
                    raise BrokerError(f'SmartAPI {operation} returned HTTP {response.status_code}')
                raw = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    if monotonic() >= deadline or len(raw) + len(chunk) > 4_000_000:
                        raise BrokerError(f'SmartAPI {operation} exceeded the response limit')
                    raw.extend(chunk)
        except httpx.HTTPError:
            raise BrokerError(f'SmartAPI {operation} request could not be completed') from None
        try:
            body = json.loads(raw, parse_float=Decimal, parse_constant=_invalid_json_constant)
        except (ValueError, RecursionError):
            raise BrokerError(f'SmartAPI {operation} returned invalid JSON') from None
        if not isinstance(body, dict) or body.get('status') is not True or 'data' not in body:
            code = (body.get('errorcode') or body.get('errorCode')) if isinstance(body, dict) else None
            if endpoint != LOGIN and code in ('AG8001', 'AG8002', 'AG8003', 'AB1010', 'AB1011'):
                raise SmartAPISessionExpired('SmartAPI session expired')
            suffix = f' ({code})' if isinstance(code, str) and re.fullmatch(r'A[BG][0-9]{4}', code) else ''
            raise BrokerError(f'SmartAPI {operation} failed{suffix}')
        return body['data']

    def _post(self, endpoint: str, operation: str, payload: dict):
        return self._request('POST', endpoint, operation, payload)

    def login(self) -> None:
        credentials = self._credentials
        secret = ''.join(credentials.totp_secret.split()).upper()
        try:
            totp = pyotp.TOTP(secret).now()
        except ValueError:
            raise BrokerError('Angel One credential file contains an invalid TOTP setup key') from None
        self._headers.pop('Authorization', None)
        data = self._post(LOGIN, 'login', {
            'clientcode': credentials.client_code, 'password': credentials.pin, 'totp': totp,
        })
        self._set_session(data)

    def recover_session(self) -> None:
        self._headers.pop('Authorization', None)
        if self._refresh_token:
            try:
                self._set_session(self._post(REFRESH, 'token refresh', {'refreshToken': self._refresh_token}))
                return
            except BrokerError:
                self.clear_session()
        self.login()

    def clear_session(self) -> None:
        self._headers.pop('Authorization', None)
        self._refresh_token = None
        self._feed_token = None

    def _set_session(self, data) -> None:
        if not isinstance(data, dict) or not (token := _session_token(data.get('jwtToken'))):
            raise BrokerError('SmartAPI session response did not contain an access token')
        self._headers['Authorization'] = f'Bearer {token}'
        self._refresh_token = _session_token(data.get('refreshToken'))
        self._feed_token = _session_token(data.get('feedToken'))


def _session_token(value) -> str | None:
    if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9._-]{1,8192}', value):
        return value
    return None


def _invalid_json_constant(_: str):
    raise ValueError
