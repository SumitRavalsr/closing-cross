import asyncio
import json

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from angel_one_mcp.server import create_server
from angel_one_mcp.smartapi.client import HISTORY, LOGIN, SEARCH


def test_mcp_fixed_reads_and_session_recovery(tmp_path, monkeypatch):
    credentials = tmp_path / 'angel.json'
    credentials.write_text(json.dumps({
        'api_key': 'mock-api-key', 'client_code': 'mock-client', 'pin': '0123',
        'totp_secret': 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP',
    }), encoding='utf-8')
    credentials.chmod(0o600)
    monkeypatch.setenv('ANGEL_CREDENTIALS_FILE', str(credentials))
    clock = iter(range(100, 1000, 30))
    monkeypatch.setattr('angel_one_mcp.smartapi.reads.monotonic', lambda: next(clock))
    requests = []

    def upstream(request):
        assert request.url.host == 'apiconnect.angelone.in'
        path = request.url.path
        requests.append(path)
        if path == LOGIN:
            assert 'authorization' not in request.headers
            assert request.headers['X-PrivateKey'] == 'mock-api-key'
            assert json.loads(request.content)['password'] == '0123'
            return httpx.Response(200, json={'status': True, 'data': {'jwtToken': 'mock-jwt'}})
        assert request.headers['Authorization'] == 'Bearer mock-jwt'
        if path == SEARCH:
            assert request.method == 'POST'
            assert json.loads(request.content) == {'exchange': 'NSE', 'searchscrip': 'RELIANCE'}
            if requests.count(SEARCH) == 1:
                return httpx.Response(200, json={'status': False, 'errorCode': 'AG8002', 'message': 'upstream text'})
            return httpx.Response(200, json={'status': True, 'data': [{
                'symboltoken': '2885', 'jwtToken': 'mock-jwt', 'private_key': 'mock-api-key',
            }]})
        if path == HISTORY:
            assert request.method == 'POST'
            assert json.loads(request.content) == {
                'exchange': 'NSE', 'symboltoken': '2885', 'interval': 'ONE_DAY',
                'fromdate': '2026-11-18 09:15', 'todate': '2026-11-19 15:30',
            }
            return httpx.Response(200, json={'status': True, 'data': [
                ['2026-11-18T00:00:00+05:30', 100, 104, 99, 103, 1000],
                ['2026-11-19T00:00:00+05:30', 103, 105, 102, 105, 1200],
            ]})
        assert path.endswith('/getHolding') and request.method == 'GET'
        return httpx.Response(302, headers={'Location': 'https://other.invalid/'})

    async def exercise(server):
        tools = {tool.name: tool for tool in await server.list_tools()}
        assert 'saved_report' not in tools
        for name in ('search_instruments', 'historical_data', 'account_snapshot', 'order_details', 'server_status'):
            assert tools[name].annotations.readOnlyHint
        with pytest.raises(ToolError):
            await server.call_tool('order_details', {'unique_order_id': '../../placeOrder'})
        _, result = await server.call_tool('server_status', {})
        assert result['status'] == 'ok'
        assert result['broker_access'] == 'trading_enabled'
        assert not requests
        _, result = await server.call_tool('search_instruments', {'exchange': 'NSE', 'query': 'reliance'})
        assert result == {'data': [{'symboltoken': '2885'}]}
        _, historical = await server.call_tool('historical_data', {
            'exchange': 'NSE', 'token': '2885', 'interval': 'ONE_DAY',
            'start': '2026-11-18T09:15', 'end': '2026-11-19T15:30', 'limit': 1,
        })
        assert historical['data']['total'] == 2
        assert historical['data']['next_offset'] == 1
        with pytest.raises(ToolError, match='302'):
            await server.call_tool('account_snapshot', {'view': 'holdings'})
        assert requests[:4] == [LOGIN, SEARCH, LOGIN, SEARCH]
        assert requests[4] == HISTORY
        assert len(requests) == 6

    with httpx.Client(transport=httpx.MockTransport(upstream), follow_redirects=True) as http:
        asyncio.run(exercise(create_server(http)))
