import asyncio
import json
import struct
from contextlib import contextmanager
from http import HTTPStatus
from threading import Thread

import httpx
import pytest
from websockets.sync.server import serve

from angel_one_mcp.server import create_server
from angel_one_mcp.smartapi import streams
from angel_one_mcp.smartapi.client import LOGIN, REFRESH


@contextmanager
def websocket_endpoint(handler, *, process_request=None):
    with serve(handler, '127.0.0.1', 0, process_request=process_request) as server:
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            yield f'ws://127.0.0.1:{server.socket.getsockname()[1]}'
        finally:
            server.shutdown()
            thread.join(timeout=5)


@pytest.fixture
def stream_credentials(monkeypatch, tmp_path):
    credentials = tmp_path / 'angel.json'
    credentials.write_text(json.dumps({
        'api_key': 'mock-api-key', 'client_code': 'mock-client', 'pin': '0123',
        'totp_secret': 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP',
    }), encoding='utf-8')
    credentials.chmod(0o600)
    monkeypatch.setenv('ANGEL_CREDENTIALS_FILE', str(credentials))


def test_market_ticks_and_order_updates_share_private_session(monkeypatch, stream_credentials):
    logins = []

    def upstream(request):
        assert request.url.path == LOGIN
        logins.append(request.url.path)
        return httpx.Response(200, json={'status': True, 'data': {
            'jwtToken': 'mock-jwt', 'feedToken': 'mock-feed',
        }})

    def feed(socket):
        headers = socket.request.headers
        assert headers['Authorization'] == 'Bearer mock-jwt'
        assert headers['x-api-key'] == 'mock-api-key'
        assert headers['x-client-code'] == 'mock-client'
        assert headers['x-feed-token'] == 'mock-feed'
        assert json.loads(socket.recv(timeout=2)) == {
            'action': 1, 'params': {'mode': 3, 'tokenList': [{'exchangeType': 1, 'tokens': ['3045']}]},
        }
        tick = bytearray(379)
        struct.pack_into('<BB25sqqq', tick, 0, 3, 1, b'3045', 17, 1000, 19450)
        struct.pack_into('<qqqddqqqq', tick, 51, 2, 19400, 20, 13.0, 15.0, 19000, 19700, 18750, 19300)
        struct.pack_into('<qq', tick, 123, 999, 500)
        struct.pack_into('<hqqh', tick, 147, 1, 10, 19449, 3)
        struct.pack_into('<hqqh', tick, 167, 0, 20, 19451, 4)
        socket.send(bytes(tick))

    def order_events(socket):
        assert socket.request.headers['Authorization'] == 'Bearer mock-jwt'
        assert 'x-feed-token' not in socket.request.headers
        socket.send(json.dumps({'order-status': 'AB00', 'orderData': {}}))
        socket.send(json.dumps({
            'order-status': 'AB05', 'orderData': {'orderid': '100', 'jwtToken': 'mock-jwt'},
        }))

    async def exercise(server):
        _, ticks = await server.call_tool('market_ticks', {
            'exchange_tokens': {'NSE': ['3045']}, 'mode': 'SNAP_QUOTE', 'seconds': 2, 'limit': 1,
        })
        tick, = ticks['data']
        assert tick['last_traded_price_raw'] == 19450
        assert tick['open_interest'] == 500
        assert tick['bids'][0] == {'quantity': 10, 'price_raw': 19449, 'orders': 3}
        assert tick['asks'][0] == {'quantity': 20, 'price_raw': 19451, 'orders': 4}
        _, updates = await server.call_tool('order_updates', {'seconds': 2, 'limit': 1})
        assert updates == {'data': [{'order-status': 'AB05', 'orderData': {'orderid': '100'}}]}

    with websocket_endpoint(feed) as market_url, websocket_endpoint(order_events) as order_url:
        monkeypatch.setattr(streams, 'MARKET_STREAM', market_url)
        monkeypatch.setattr(streams, 'ORDER_STREAM', order_url)
        with httpx.Client(transport=httpx.MockTransport(upstream)) as http:
            asyncio.run(exercise(create_server(http)))
    assert logins == [LOGIN]


def test_order_updates_refreshes_expired_token_on_forbidden(monkeypatch, stream_credentials):
    requests = []
    handshakes = []

    def upstream(request):
        requests.append(request.url.path)
        if request.url.path == LOGIN:
            data = {'jwtToken': 'expired-token', 'refreshToken': 'mock-refresh'}
        else:
            assert request.url.path == REFRESH
            assert json.loads(request.content) == {'refreshToken': 'mock-refresh'}
            data = {'jwtToken': 'new-token'}
        return httpx.Response(200, json={'status': True, 'data': data})

    def authorize(socket, request):
        authorization = request.headers['Authorization']
        handshakes.append(authorization)
        if authorization != 'Bearer new-token':
            return socket.respond(HTTPStatus.FORBIDDEN, 'Expired token')

    event = {'order-status': 'AB05', 'orderData': {'orderid': '100'}}

    def order_events(socket):
        socket.send(json.dumps(event))

    async def exercise(server):
        _, updates = await server.call_tool('order_updates', {'seconds': 2, 'limit': 1})
        assert updates == {'data': [event]}

    with websocket_endpoint(order_events, process_request=authorize) as order_url:
        monkeypatch.setattr(streams, 'ORDER_STREAM', order_url)
        with httpx.Client(transport=httpx.MockTransport(upstream)) as http:
            asyncio.run(exercise(create_server(http)))

    assert requests == [LOGIN, REFRESH]
    assert handshakes == ['Bearer expired-token', 'Bearer new-token']
