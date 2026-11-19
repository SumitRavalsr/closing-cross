import asyncio
import json
import os
from contextlib import asynccontextmanager

import httpx
import pytest

from angel_one_mcp.server import create_server
from angel_one_mcp.smartapi.client import LOGIN, SEARCH
from angel_one_mcp.socket_transport import serve_connection


def test_shared_socket_keeps_two_mcp_sessions_and_one_broker_login(tmp_path, monkeypatch):
    path = tmp_path / 'mcp.sock'
    credentials = tmp_path / 'angel.json'
    credentials.write_text(json.dumps({
        'api_key': 'mock-key', 'client_code': 'mock-client', 'pin': '0123',
        'totp_secret': 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP',
    }), encoding='utf-8')
    credentials.chmod(0o600)
    monkeypatch.setenv('ANGEL_CREDENTIALS_FILE', str(credentials))
    requests = []

    def respond(request):
        requests.append(request.url.path)
        if request.url.path == LOGIN:
            data = {'jwtToken': 'mock-token'}
        else:
            assert request.url.path == SEARCH
            assert request.headers['Authorization'] == 'Bearer mock-token'
            data = [{'symboltoken': '2885'}]
        return httpx.Response(200, json={'status': True, 'data': data})

    @asynccontextmanager
    async def client(connect):
        reader, writer = await connect()

        def send(method, params=None, request_id=None):
            message = {'jsonrpc': '2.0', 'method': method, 'params': params or {}}
            if request_id is not None:
                message['id'] = request_id
            writer.write(json.dumps(message).encode() + b'\n')

        async def request(request_id, method, params=None):
            send(method, params, request_id)
            await writer.drain()
            response = json.loads(await reader.readline())
            assert response['id'] == request_id
            return response['result']

        try:
            await request(1, 'initialize', {
                'protocolVersion': '2025-03-26', 'capabilities': {},
                'clientInfo': {'name': 'test', 'version': '1'},
            })
            send('notifications/initialized')
            yield request
        finally:
            writer.close()
            await writer.wait_closed()

    async def check_clients(connect):
        async with client(connect) as first:
            async with client(connect) as second:
                listed = await first(2, 'tools/list')
                assert any(row['name'] == 'market_quote' for row in listed['tools'])
                search = {'name': 'search_instruments', 'arguments': {'exchange': 'NSE', 'query': 'RELIANCE'}}
                results = await asyncio.gather(first(3, 'tools/call', search), second(3, 'tools/call', search))
                assert all(row['structuredContent']['data'] == [{'symboltoken': '2885'}] for row in results)
                assert requests == [LOGIN, SEARCH, SEARCH]
            status = await first(4, 'tools/call', {'name': 'server_status'})
            assert status['structuredContent']['status'] == 'ok'

    async def exercise(server):
        if os.name == 'nt':
            listener = await asyncio.start_server(
                lambda reader, writer: serve_connection(server._mcp_server, reader, writer), '127.0.0.1', 0,
            )
            async with listener:
                address = listener.sockets[0].getsockname()
                await check_clients(lambda: asyncio.open_connection(*address))
            return

        service = asyncio.create_task(server.run_socket(path))
        try:
            while not path.exists():
                if service.done():
                    await service
                await asyncio.sleep(0.01)
            await check_clients(lambda: asyncio.open_unix_connection(path))
        finally:
            service.cancel()
            with pytest.raises(asyncio.CancelledError):
                await service
        assert not path.exists()

    async def run():
        with httpx.Client(transport=httpx.MockTransport(respond)) as http:
            async with asyncio.timeout(15):
                await exercise(create_server(http))

    asyncio.run(run())
