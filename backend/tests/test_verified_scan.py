import csv
import io
import json
import sys
from datetime import date, timedelta
from zipfile import ZipFile

import httpx
import pytest
from fastapi.testclient import TestClient

from closing_cross.adapters.angel import HISTORY, LOGIN, SEARCH
from closing_cross.adapters.database import migrate
from closing_cross.api import app
from closing_cross.scanner import main


@pytest.mark.parametrize('problem', [None, 'price', 'missing_broker', 'missing_both', 'closed'])
def test_verified_cli_to_api(tmp_path, monkeypatch, capsys, problem):
    start = date(2025, 1, 6)
    sessions = [start + timedelta(days=i) for i in range(74)
                if (start + timedelta(days=i)).weekday() < 5][:52]
    selected = sessions[10]
    end = sessions[-1]
    closes = dict(zip(sessions, [100] * 50 + [110, 80], strict=True))
    calls = []

    def handle(request):
        calls.append(request.url.path)
        if request.url.host == 'apiconnect.angelone.in':
            assert request.method == 'POST'
            body = json.loads(request.content)
            assert request.headers['X-PrivateKey'] == 'test-api-key'
            if request.url.path == LOGIN:
                assert body['totp'].isdigit() and len(body['totp']) == 6
                data = {'jwtToken': 'test-token'}
            else:
                assert request.headers['Authorization'] == 'Bearer test-token'
                if request.url.path == SEARCH:
                    assert body == {'exchange': 'NSE', 'searchscrip': 'RELIANCE'}
                    data = [{'exchange': 'NSE', 'tradingsymbol': 'RELIANCE-EQ', 'symboltoken': '2885'}]
                else:
                    assert request.url.path == HISTORY
                    assert (body['interval'], body['symboltoken']) == ('ONE_DAY', '2885')
                    data = [
                        [f'{day}T00:00:00+05:30', 100, 120, 70, close, 1000]
                        for day, close in closes.items()
                        if day != selected or problem not in {'missing_broker', 'missing_both', 'closed'}
                    ]
            return httpx.Response(200, json={'status': True, 'data': data})

        assert request.url.host == 'archives.nseindia.com' and request.method == 'GET'
        assert 'Authorization' not in request.headers and 'X-PrivateKey' not in request.headers
        filename = request.url.path.rsplit('/', 1)[1]
        day = date.fromisoformat(filename.split('_')[6])
        if day not in closes or (day == selected and problem in {'missing_both', 'closed'}):
            return httpx.Response(404)
        close = 101 if day == selected and problem == 'price' else closes[day]
        text = io.StringIO()
        writer = csv.writer(text)
        writer.writerow(['TradDt', 'TckrSymb', 'SctySrs', 'OpnPric', 'HghPric', 'LwPric', 'ClsPric', 'TtlTradgVol'])
        writer.writerow([day, 'RELIANCE', 'EQ', 100, 120, 70, close, 1000])
        content = io.BytesIO()
        with ZipFile(content, 'w') as archive:
            archive.writestr(filename[:-4], text.getvalue())
        return httpx.Response(200, content=content.getvalue())

    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'pilot.sqlite3'))
    monkeypatch.setenv('PILOT_NSE_SYMBOL', 'RELIANCE')
    monkeypatch.setenv('ANGEL_API_KEY', 'test-api-key')
    monkeypatch.setenv('ANGEL_CLIENT_CODE', 'test-client')
    monkeypatch.setenv('ANGEL_PIN', '1234')
    monkeypatch.setenv('ANGEL_TOTP_SECRET', 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP')
    monkeypatch.delenv('ANGEL_TOTP_CODE', raising=False)
    command = ['closing-cross', 'scan-nse', '--start', str(start), '--session', str(end), '--confirm-no-split-bonus']
    if problem == 'closed':
        command += ['--closed-on', str(selected)]
    monkeypatch.setattr(sys, 'argv', command)
    migrate()
    client = httpx.Client
    with TestClient(app) as api:
        assert api.get('/api/pilot/verified-scan').json() is None
        with monkeypatch.context() as mock:
            mock.setattr('closing_cross.scanner.httpx.Client',
                         lambda **options: client(transport=httpx.MockTransport(handle), **options))
            if problem in {'price', 'missing_broker', 'missing_both'}:
                with pytest.raises(SystemExit) as failure:
                    main()
                assert failure.value.code == 1
            else:
                main()
                first_id = json.loads(capsys.readouterr().out)['id']
                main()
        assert calls[:3] == [LOGIN, SEARCH, HISTORY]
        report = api.get('/api/pilot/verified-scan').json()
        captured = capsys.readouterr()
        if problem in {'price', 'missing_broker', 'missing_both'}:
            assert report is None
            assert str(selected) in captured.err
            assert 'test-token' not in captured.err and 'test-api-key' not in captured.err
        else:
            assert report['verified_sessions'] == (51 if problem else 52)
            assert report['candles'][-1]['cross'] == 'down'
            if not problem:
                assert report['candles'][-2]['cross'] == 'up'
            assert first_id == json.loads(captured.out)['id'] == report['id']
