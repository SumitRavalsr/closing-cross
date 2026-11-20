import json
import math
import struct
from decimal import Decimal
from time import monotonic

from websockets.exceptions import ConnectionClosedOK, InvalidStatus, WebSocketException
from websockets.sync.client import connect

from angel_one_mcp.smartapi.client import SmartAPISessionExpired
from angel_one_mcp.smartapi.errors import BrokerError
from angel_one_mcp.smartapi.reads import _clean

MARKET_STREAM = 'wss://smartapisocket.angelone.in/smart-stream'
ORDER_STREAM = 'wss://tns.angelone.in/smart-order-update'
STREAM_EXCHANGES = {'NSE': 1, 'NFO': 2, 'BSE': 3, 'BFO': 4, 'MCX': 5, 'NCDEX': 7, 'CDS': 13}
STREAM_MODES = {'LTP': 1, 'QUOTE': 2, 'SNAP_QUOTE': 3}
PACKET_SIZES = {1: 51, 2: 123, 3: 379}


def market_subscription(exchange_tokens: dict[str, list[str]], mode: str) -> str:
    return json.dumps({
        'action': 1,
        'params': {
            'mode': STREAM_MODES[mode],
            'tokenList': [{'exchangeType': STREAM_EXCHANGES[exchange], 'tokens': tokens}
                          for exchange, tokens in exchange_tokens.items()],
        },
    })


def _market_tick(packet: bytes) -> dict:
    mode, exchange, token, sequence, timestamp, ltp = struct.unpack_from('<BB25sqqq', packet)
    if PACKET_SIZES.get(mode) != len(packet):
        raise ValueError('Unexpected market tick size')
    tick = {
        'subscription_mode': mode, 'exchange_type': exchange, 'token': token.split(b'\0', 1)[0].decode('ascii'),
        'sequence_number': sequence, 'exchange_timestamp_ms': timestamp, 'last_traded_price_raw': ltp,
    }
    if mode >= 2:
        names = (
            'last_traded_quantity', 'average_traded_price_raw', 'day_volume', 'total_buy_quantity',
            'total_sell_quantity', 'day_open_raw', 'day_high_raw', 'day_low_raw', 'previous_close_raw',
        )
        fields = struct.unpack_from('<qqqddqqqq', packet, 51)
        if not all(map(math.isfinite, fields[3:5])):
            raise ValueError('Invalid market depth totals')
        tick.update(zip(names, fields))
    if mode == 3:
        last_trade, open_interest = struct.unpack_from('<qq', packet, 123)
        upper, lower, high, low = struct.unpack_from('<qqqq', packet, 347)
        depth = {'bids': [], 'asks': []}
        for side, quantity, price, orders in struct.iter_unpack('<hqqh', packet[147:347]):
            if side not in (0, 1):
                raise ValueError('Invalid market depth side')
            depth['bids' if side == 1 else 'asks'].append({
                'quantity': quantity, 'price_raw': price, 'orders': orders,
            })
        tick.update(last_traded_timestamp_ms=last_trade, open_interest=open_interest,
                    upper_circuit_limit_raw=upper, lower_circuit_limit_raw=lower,
                    high_52_week_raw=high, low_52_week_raw=low, **depth)
    return tick


def capture_stream(headers: dict[str, str], secrets: set[str], seconds: int, limit: int,
                   subscription: str | None = None) -> list[dict]:
    market = subscription is not None
    url = MARKET_STREAM if market else ORDER_STREAM
    items = []
    try:
        with connect(url, additional_headers=headers, proxy=None, open_timeout=5, close_timeout=1,
                     ping_interval=None, max_size=16_384) as socket:
            if market:
                socket.send(subscription)
            deadline = monotonic() + seconds
            next_ping = monotonic()
            while len(items) < limit and (remaining := deadline - (now := monotonic())) > 0:
                if not market and now >= next_ping:
                    socket.ping()
                    next_ping = now + 8
                try:
                    frame = socket.recv(timeout=remaining if market else min(remaining, next_ping - now))
                except TimeoutError:
                    continue
                if market and isinstance(frame, bytes):
                    items.append(_clean(_market_tick(frame), secrets))
                    continue
                if frame == 'pong':
                    continue
                message = json.loads(frame, parse_float=Decimal, parse_constant=_invalid_constant)
                if not isinstance(message, dict):
                    raise ValueError('Unexpected stream message')
                if market:
                    raise BrokerError('SmartAPI market stream rejected the subscription')
                if message.get('order-status') == 'AB00':
                    continue
                items.append(_clean(message, secrets))
    except InvalidStatus as error:
        status = error.response.status_code
        if status == 401 or (not market and status == 403):
            raise SmartAPISessionExpired('SmartAPI stream session expired') from None
        raise BrokerError(f'SmartAPI stream handshake returned HTTP {status}') from None
    except ConnectionClosedOK:
        pass
    except (ValueError, OSError, RecursionError, struct.error, WebSocketException):
        raise BrokerError('SmartAPI stream could not be read') from None
    return items


def _invalid_constant(_: str):
    raise ValueError
