import asyncio
import json

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from angel_one_mcp.server import create_server
from angel_one_mcp.smartapi.client import LOGIN, REFRESH


@pytest.fixture
def trading(monkeypatch, tmp_path):
    credentials = tmp_path / 'angel.json'
    credentials.write_text(json.dumps({
        'api_key': 'mock-key', 'client_code': 'mock-client', 'pin': '0123',
        'totp_secret': 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP',
    }), encoding='utf-8')
    credentials.chmod(0o600)
    monkeypatch.setenv('ANGEL_CREDENTIALS_FILE', str(credentials))
    clock = iter(range(100, 10_000, 30))
    monkeypatch.setattr('angel_one_mcp.smartapi.reads.monotonic', lambda: next(clock))


ORDER = {
    'variety': 'NORMAL', 'exchange': 'NSE', 'tradingsymbol': 'SBIN-EQ', 'symboltoken': '3045',
    'ordertype': 'LIMIT', 'producttype': 'DELIVERY', 'duration': 'DAY', 'quantity': 2, 'price': '195.25',
}


def test_order_tools_forward_documented_payloads(trading):
    calls = []

    def upstream(request):
        assert request.url.host == 'apiconnect.angelone.in'
        assert request.method == 'POST'
        if request.url.path == LOGIN:
            return httpx.Response(200, json={'status': True, 'data': {'jwtToken': 'mock-jwt'}})
        assert request.headers['Authorization'] == 'Bearer mock-jwt'
        calls.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={'status': True, 'data': {
            'orderid': '100', 'uniqueorderid': 'uid-100', 'jwtToken': 'mock-jwt',
        }})

    async def exercise(server):
        tools = {tool.name: tool for tool in await server.list_tools()}
        for name in ('place_order', 'modify_order', 'cancel_order'):
            annotations = tools[name].annotations
            assert not annotations.readOnlyHint and annotations.destructiveHint
            assert not annotations.idempotentHint and annotations.openWorldHint
        _, status = await server.call_tool('server_status', {})
        assert status['broker_access'] == 'trading_enabled'
        with pytest.raises(ToolError):
            await server.call_tool('place_order', {'order': {**ORDER, 'transactiontype': 'BUY', 'price': '0'}})
        assert calls == []
        for side in ('BUY', 'SELL'):
            _, result = await server.call_tool('place_order', {'order': {**ORDER, 'transactiontype': side}})
            assert result == {'data': {'orderid': '100', 'uniqueorderid': 'uid-100'}}
        await server.call_tool('modify_order', {'order': {**ORDER, 'orderid': '100'}})
        await server.call_tool('cancel_order', {'order_id': '100', 'variety': 'NORMAL'})

    with httpx.Client(transport=httpx.MockTransport(upstream)) as http:
        asyncio.run(exercise(create_server(http)))
    payload = {**ORDER, 'quantity': '2'}
    base = '/rest/secure/angelbroking/order/v1'
    assert calls == [
        (f'{base}/placeOrder', {**payload, 'transactiontype': 'BUY'}),
        (f'{base}/placeOrder', {**payload, 'transactiontype': 'SELL'}),
        (f'{base}/modifyOrder', {**payload, 'orderid': '100'}),
        (f'{base}/cancelOrder', {'orderid': '100', 'variety': 'NORMAL'}),
    ]


@pytest.mark.parametrize('failure', ['timeout', 'expired', 'malformed'])
def test_order_failure_is_never_replayed_and_reads_can_recover(trading, failure):
    calls = []

    def upstream(request):
        name = request.url.path.rsplit('/', 1)[-1]
        calls.append(name)
        if request.url.path == LOGIN:
            return httpx.Response(200, json={'status': True, 'data': {
                'jwtToken': 'expired-token', 'refreshToken': 'mock-refresh',
            }})
        if request.url.path == REFRESH:
            assert json.loads(request.content) == {'refreshToken': 'mock-refresh'}
            return httpx.Response(200, json={'status': True, 'data': {'jwtToken': 'new-token'}})
        if name == 'placeOrder':
            if failure == 'expired':
                return httpx.Response(401)
            if failure == 'timeout':
                raise httpx.ReadTimeout('upstream detail', request=request)
            return httpx.Response(200, content=b'not json')
        assert name == 'getOrderBook'
        if failure == 'expired':
            assert request.headers['Authorization'] == 'Bearer new-token'
        return httpx.Response(200, json={'status': True, 'data': []})

    async def exercise(server):
        with pytest.raises(ToolError, match='Check broker state before retrying'):
            await server.call_tool('place_order', {'order': {**ORDER, 'transactiontype': 'BUY'}})
        assert calls == ['loginByPassword', 'placeOrder']
        await server.call_tool('account_snapshot', {'view': 'order_book'})

    with httpx.Client(transport=httpx.MockTransport(upstream)) as http:
        asyncio.run(exercise(create_server(http)))
    assert calls[-1] == 'getOrderBook'
    assert calls.count('placeOrder') == 1
    assert ('generateTokens' in calls) == (failure == 'expired')


def test_additional_account_actions(trading):
    received = []

    def upstream(request):
        path = request.url.path.removeprefix('/rest/secure/angelbroking/')
        received.append(path)
        if request.url.path == LOGIN:
            data = {'jwtToken': 'mock-jwt'}
        else:
            data = None
            assert request.headers['Authorization'] == 'Bearer mock-jwt'
            payload = json.loads(request.content)
            if '/gtt/' in request.url.path:
                assert payload['symboltoken'] == '3045'
                if 'cancelRule' not in path:
                    assert payload['qty'] == '2'
            if path == 'order/v1/convertPosition':
                assert payload['quantity'] == 2
            if path == 'user/v1/logout':
                assert payload == {'clientcode': 'mock-client'}
        return httpx.Response(200, json={'status': True, 'data': data})

    async def exercise(server):
        rule = {'symboltoken': '3045', 'exchange': 'NSE', 'price': '195', 'triggerprice': '196', 'qty': 2}
        position = {
            'exchange': 'NSE', 'symboltoken': '3045', 'tradingsymbol': 'SBIN-EQ', 'symbolname': 'SBIN',
            'oldproducttype': 'DELIVERY', 'newproducttype': 'INTRADAY', 'transactiontype': 'BUY', 'quantity': 2,
            'type': 'DAY', 'instrumenttype': '', 'priceden': '1', 'pricenum': '1', 'genden': '1', 'gennum': '1',
            'precision': '2', 'multiplier': '-1', 'boardlotsize': '1', 'buyqty': '2', 'sellqty': '0',
            'buyamount': '390', 'sellamount': '0',
        }
        await server.call_tool('create_gtt_rule', {'rule': dict(rule, tradingsymbol='SBIN-EQ',
                                                              transactiontype='BUY', producttype='DELIVERY')})
        await server.call_tool('modify_gtt_rule', {'rule': dict(rule, id='123')})
        await server.call_tool('cancel_gtt_rule', {'rule_id': '123', 'exchange': 'NSE', 'token': '3045'})
        await server.call_tool('convert_position', {'position': position})
        await server.call_tool('initiate_edis', {'isin': 'INE062A01020', 'quantity': 2})
        await server.call_tool('generate_edis_tpin', {
            'dp_id': '12345', 'request_id': '67890', 'boid': '11223344', 'pan': 'AAAAA0000A',
        })
        await server.call_tool('logout_broker_session', {})
        await server.call_tool('last_traded_price', {'exchange': 'NSE', 'symbol': 'SBIN-EQ', 'token': '3045'})

    with httpx.Client(transport=httpx.MockTransport(upstream)) as http:
        asyncio.run(exercise(create_server(http)))
    assert received == [
        LOGIN, 'gtt/v1/createRule', 'gtt/v1/modifyRule', 'gtt/v1/cancelRule', 'order/v1/convertPosition',
        'edis/v1/verifyDis', 'edis/v1/generateTPIN', 'user/v1/logout', LOGIN, 'order/v1/getLtpData',
    ]
