import json
import re
from decimal import Decimal
from enum import Enum
from time import monotonic, sleep

import httpx

from angel_one_mcp.smartapi.client import HISTORY, SEARCH, SmartAPI, SmartAPISessionExpired
from angel_one_mcp.smartapi.errors import BrokerError

SECURE = '/rest/secure/angelbroking'
MARKET = f'{SECURE}/marketData/v1'
ORDERS = f'{SECURE}/order/v1'
MASTER_URL = 'https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json'


def search_master(http: httpx.Client, exchange: str, query: str, limit: int, offset: int) -> dict:
    """Filter Angel One's public dump before sending results to the MCP client."""
    deadline = monotonic() + 45
    raw = bytearray()
    try:
        with http.stream('GET', MASTER_URL, follow_redirects=False, headers={'Accept-Encoding': 'identity'}) as reply:
            reply.raise_for_status()
            for chunk in reply.iter_bytes(chunk_size=65536):
                if monotonic() >= deadline or len(raw) + len(chunk) > 50_000_000:
                    raise BrokerError('Angel One instrument master exceeded the download limit')
                raw.extend(chunk)
        records = json.loads(raw)
    except (httpx.HTTPError, ValueError, RecursionError):
        raise BrokerError('Angel One instrument master is unavailable') from None
    if not isinstance(records, list):
        raise BrokerError('Angel One instrument master returned an unexpected format')
    segment_alias = {'NSE': 'NSE_CM', 'NFO': 'NSE_FO', 'BSE': 'BSE_CM', 'BFO': 'BSE_FO'}.get(exchange)
    segments = {exchange, segment_alias}
    keys = ('token', 'symbol', 'name', 'expiry', 'strike', 'lotsize', 'instrumenttype', 'exch_seg', 'tick_size')
    total = 0
    items = []
    for record in records:
        if not isinstance(record, dict) or str(record.get('exch_seg', '')).upper() not in segments:
            continue
        if not any(query in str(record.get(key, '')).upper() for key in ('token', 'symbol', 'name')):
            continue
        if offset <= total < offset + limit:
            items.append({key: record[key] for key in keys if isinstance(record.get(key), (str, int, float))})
        total += 1
    return {'total': total, 'items': items, 'next_offset': offset + limit if offset + limit < total else None}


class AccountView(str, Enum):
    PROFILE = 'profile'
    FUNDS = 'funds'
    HOLDINGS = 'holdings'
    ALL_HOLDINGS = 'all_holdings'
    POSITIONS = 'positions'
    ORDER_BOOK = 'order_book'
    TRADE_BOOK = 'trade_book'


ACCOUNT_PATHS = {
    AccountView.PROFILE: f'{SECURE}/user/v1/getProfile',
    AccountView.FUNDS: f'{SECURE}/user/v1/getRMS',
    AccountView.HOLDINGS: f'{SECURE}/portfolio/v1/getHolding',
    AccountView.ALL_HOLDINGS: f'{SECURE}/portfolio/v1/getAllHolding',
    AccountView.POSITIONS: f'{ORDERS}/getPosition',
    AccountView.ORDER_BOOK: f'{ORDERS}/getOrderBook',
    AccountView.TRADE_BOOK: f'{ORDERS}/getTradeBook',
}


class Read(str, Enum):
    SEARCH = SEARCH
    LTP = f'{ORDERS}/getLtpData'
    QUOTE = f'{SECURE}/market/v1/quote/'
    CANDLES = HISTORY
    HISTORICAL_OI = f'{SECURE}/historical/v1/getOIData'
    GREEKS = f'{MARKET}/optionGreek'
    PCR = f'{MARKET}/putCallRatio'
    MOVERS = f'{MARKET}/gainersLosers'
    BUILDUP = f'{MARKET}/OIBuildup'
    NSE_INTRADAY = f'{MARKET}/nseIntraday'
    BSE_INTRADAY = f'{MARKET}/bseIntraday'
    CAUTION = f'{SECURE}/securities/v1/cautionaryScrips'
    GTT_LIST = f'{SECURE}/gtt/v1/ruleList'
    GTT_DETAILS = f'{SECURE}/gtt/v1/ruleDetails'
    MARGIN = f'{SECURE}/margin/v1/batch'
    CHARGES = f'{SECURE}/brokerage/v1/estimateCharges'
    EDIS_STATUS = f'{SECURE}/edis/v1/getTranStatus'


GET_READS = {Read.PCR, Read.NSE_INTRADAY, Read.BSE_INTRADAY, Read.CAUTION}

_AUTH_FIELDS = {
    'accesstoken', 'authorization', 'apikey', 'clientsecret', 'feedtoken', 'idtoken',
    'jwttoken', 'pan', 'password', 'pin', 'privatekey', 'refreshtoken', 'secret',
    'totp', 'totpsecret', 'tpin', 'xprivatekey',
}


def _safe_field(key: str, value, secrets: set[str]) -> bool:
    normalized = re.sub(r'[^a-z0-9]', '', key.lower())
    if normalized == 'token':
        return isinstance(value, (int, str)) and bool(re.fullmatch(r'[0-9]{1,20}', str(value)))
    return normalized not in _AUTH_FIELDS and key not in secrets


def _clean(value, secrets: set[str], depth: int = 0):
    if depth > 32:
        raise BrokerError('SmartAPI returned an excessively nested payload')
    if isinstance(value, dict):
        return {
            key: _clean(item, secrets, depth + 1) for key, item in value.items()
            if _safe_field(key, item, secrets)
        }
    if isinstance(value, list):
        return [_clean(item, secrets, depth + 1) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, str):
        if value in secrets or value.startswith('Bearer ') or re.fullmatch(
            r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', value
        ):
            return '[redacted]'
    return value


class SmartAPIReads(SmartAPI):
    def __init__(self, http: httpx.Client):
        super().__init__(http)
        self._next_request = 0.0
        self._next_login = 0.0

    def _request(self, *args, **kwargs):
        delay = self._next_request - monotonic()
        if delay > 0:
            sleep(delay)
        self._next_request = monotonic() + 1.05
        return super()._request(*args, **kwargs)

    def login(self) -> None:
        if monotonic() < self._next_login:
            raise BrokerError('SmartAPI login cooldown is active. Try again shortly')
        self._next_login = monotonic() + 15
        super().login()

    def _authenticated(self, method: str, path: str, label: str, payload=None, *, retry_expired=True):
        if 'Authorization' not in self._headers:
            self.recover_session()
        try:
            value = self._request(method, path, label, payload)
        except SmartAPISessionExpired:
            self._headers.pop('Authorization', None)
            if not retry_expired:
                raise
            self.recover_session()
            value = self._request(method, path, label, payload)
        return _clean(value, self.session_secrets())

    def session_secrets(self) -> set[str]:
        secrets = {self._credentials.api_key, self._credentials.pin, self._credentials.totp_secret,
                   self._headers.get('Authorization', '').removeprefix('Bearer ')}
        secrets.update(token for token in (self._refresh_token, self._feed_token) if token)
        return secrets

    def read(self, endpoint: Read, payload: dict | None = None):
        method = 'GET' if endpoint in GET_READS else 'POST'
        return self._authenticated(method, endpoint.value, endpoint.name.lower(), payload)

    def account(self, view: AccountView):
        return self._authenticated('GET', ACCOUNT_PATHS[view], view.value)

    def order_details(self, order_id: str):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', order_id):
            raise BrokerError('Invalid SmartAPI order ID')
        return self._authenticated('GET', f'{ORDERS}/details/{order_id}', 'order details')
